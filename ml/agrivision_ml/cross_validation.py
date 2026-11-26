"""分组交叉验证：只生成小型清单，复用同一份图片和既有训练/评估入口。

外层折用于比较方法；每个外层训练池再划出内层验证集，用来早停和校准。
原 manifest 的 test 完全不进入交叉验证，避免一边挑模型一边消费最终测试集。
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from importlib.metadata import version
from pathlib import Path
import subprocess
import sys

import numpy as np
from sklearn.model_selection import StratifiedGroupKFold

from .train import metrics, read_manifest
from .preprocessing.groups import _DisjointSets


FIELDS = ('path', 'label', 'group', 'sha256', 'split')
# 先比较既有验证较好的两种方案；尺寸是方案的一部分，不把结果只归因于网络结构。
RECIPES = {'swin_t': 224, 'convnext_tiny': 320}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def grouped_indices(rows, folds, seed):
    """复用 sklearn 的分层分组划分，类别比例尽量接近，同时保留完整采集组。"""
    labels = [row['label'] for row in rows]
    groups = [row['group'] for row in rows]
    counts = defaultdict(set)
    for row in rows:
        counts[row['label']].add(row['group'])
    short = {label: len(ids) for label, ids in counts.items() if len(ids) < folds}
    if short:
        raise ValueError(f'独立组数不足以做 {folds} 折：{short}')
    splitter = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=seed)
    return splitter.split(np.zeros(len(rows)), labels, groups)


def check_partition(rows, labels):
    """每个子集都要覆盖全部类别；组与完全重复的图片均不能横跨子集。"""
    for split in ('train', 'val', 'test'):
        missing = set(labels) - {r['label'] for r in rows if r['split'] == split}
        if missing:
            raise ValueError(f'{split} 缺少类别 {sorted(missing)}，需补数据或减少折数')
    for key in ('group', 'sha256'):
        owner = {}
        for row in rows:
            if key == 'sha256' and not row[key]:
                raise ValueError('缺少图像哈希，不能检查重复图泄漏')
            if row[key] in owner and owner[row[key]] != row['split']:
                raise ValueError(f'{key} 横跨折内子集：{row[key]}')
            owner[row[key]] = row['split']


def read_group_links(path):
    """人工确认表只声明图片之间的同组关系，不根据感知哈希自动决定相似性。"""
    if path is None:
        return []
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if not {'left', 'right'}.issubset(reader.fieldnames or []):
            raise ValueError('人工合组表必须包含 left、right 两列')
        return [(row['left'].strip(), row['right'].strip()) for row in reader]


def merge_confirmed_groups(rows, links=()):
    """复用并查集合并原采集组、相同字节和人工确认边；原划分字段仍保留用于隔离。"""
    sets = _DisjointSets(len(rows))
    paths, named = {}, {}
    for index, row in enumerate(rows):
        paths[row['path'].replace('\\', '/')] = index
        for kind in ('group', 'sha256'):
            value = row[kind]
            if not value:
                raise ValueError(f'缺少 {kind}，不能确认分组边界')
            key = (kind, value)
            sets.union(index, named.setdefault(key, index))
    for left, right in links:
        left, right = left.replace('\\', '/'), right.replace('\\', '/')
        if left not in paths or right not in paths:
            raise ValueError(f'人工合组路径不在清单中：{left} / {right}')
        sets.union(paths[left], paths[right])
    # 取连通组原 ID 的最小值，人工确认边的书写顺序不会改变分组名称。
    names = {}
    for index, row in enumerate(rows):
        root = sets.find(index)
        names[root] = min(names.get(root, row['group']), row['group'])
    return [{**row, 'group': names[sets.find(index)]} for index, row in enumerate(rows)]


def make_folds(rows, folds=5, seed=42, inner_folds=5, *, group_links=()):
    """生成外层 K 折；内层只取固定的一折做早停验证，不执行完整嵌套调参。"""
    rows = merge_confirmed_groups(rows, group_links)
    heldout_groups = {row['group'] for row in rows if row['split'] == 'test'}
    # 人工确认的近重复可能连接到原 test；整组留出，不能把同一株的另一张图放进开发池。
    development = [r for r in rows if r['split'] in {'train', 'val'} and r['group'] not in heldout_groups]
    if not development:
        raise ValueError('隔离原测试组后没有开发样本，请核对人工合组关系')
    labels = {r['label'] for r in development}
    result = []
    for fold, (pool_ids, heldout_ids) in enumerate(grouped_indices(development, folds, seed), 1):
        pool = [development[i] for i in pool_ids]
        # 外层留出图不能参与每轮最佳 checkpoint 的选择。
        train_ids, val_ids = next(grouped_indices(pool, inner_folds, seed + fold))
        parts = [('train', [pool[i] for i in train_ids]),
                 ('val', [pool[i] for i in val_ids]),
                 ('test', [development[i] for i in heldout_ids])]
        fold_rows = [{**row, 'split': split} for split, part in parts for row in part]
        check_partition(fold_rows, labels)
        result.append(fold_rows)
    return result


def prepare(manifest, output, *, folds=5, seed=42, inner_folds=5, group_links=None):
    """清单指向原图片，不落盘增强图；固定输入和划分后可继续执行未完成实验。"""
    rows = read_manifest(manifest)
    identity = {'manifest_sha256': digest(manifest), 'folds': folds,
                'inner_folds': inner_folds, 'seed': seed,
                'group_links_sha256': digest(group_links) if group_links is not None else None}
    plan_path = output / 'folds.json'
    if plan_path.exists():
        plan = json.loads(plan_path.read_text(encoding='utf-8'))
        if plan['identity'] != identity:
            raise ValueError('本实验目录已使用不同数据或分折设置；不要覆盖已有实验')
        for fold in plan['folds']:
            if digest(output / fold['manifest']) != fold['sha256']:
                raise ValueError('保存的折清单已变化，请核对')
        return plan
    links = read_group_links(group_links)
    assignments = make_folds(rows, folds, seed, inner_folds, group_links=links)
    output.mkdir(parents=True, exist_ok=True)
    original_test_count = sum(r['split'] == 'test' for r in rows)
    plan = {'identity': identity, 'excluded_original_test_images': original_test_count,
            'excluded_test_group_development_images': len(rows) - original_test_count - len(assignments[0]),
            'confirmed_group_links': len(links),
            'evaluation_scope': 'outer development folds; NOT original test or external field validation', 'folds': []}
    for number, fold_rows in enumerate(assignments, 1):
        folder = output / 'folds' / f'fold-{number}'
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / 'manifest.csv'
        with path.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows({key: row[key] for key in FIELDS} for row in fold_rows)
        # 仅复制几百 KB 的来源表，既有评估入口依此输出来源指标；图片始终只有一套。
        (folder / 'sources.csv').write_bytes((manifest.parent / 'sources.csv').read_bytes())
        counts = {split: dict(Counter(r['label'] for r in fold_rows if r['split'] == split))
                  for split in ('train', 'val', 'test')}
        plan['folds'].append({'fold': number, 'manifest': path.relative_to(output).as_posix(),
                              'sha256': digest(path), 'counts': counts})
    write_json(plan_path, plan)
    return plan


def summarize(output, architectures, folds):
    """平均值和标准差描述折间变化；汇总混淆矩阵则让每张开发图只贡献一次预测。"""
    summary = {'evaluation_scope': 'development grouped cross-validation', 'models': []}
    for architecture in architectures:
        reports = []
        for fold in range(1, folds + 1):
            path = output / architecture / f'fold-{fold}' / 'result.json'
            if path.exists():
                reports.append(json.loads(path.read_text(encoding='utf-8')))
        if not reports:
            continue
        matrix = np.sum([r['outer']['confusion_matrix'] for r in reports], axis=0)
        scores = [r['outer']['macro_f1'] for r in reports]
        summary['models'].append({'architecture': architecture, 'completed_folds': len(reports),
            'expected_folds': folds, 'mean_macro_f1': float(np.mean(scores)),
            'std_macro_f1': float(np.std(scores, ddof=1)) if len(scores) > 1 else None,
            'mean_accuracy': float(np.mean([r['outer']['accuracy'] for r in reports])),
            'out_of_fold': metrics(matrix)})
    write_json(output / 'summary.json', summary)
    return summary


def training_recipe(args, plan, fold, architecture):
    """把实际命令参数、每折清单和实现版本一起固定，防止恢复时混入不同方案。"""
    manifest = args.output / fold['manifest']
    if digest(manifest) != fold['sha256']:
        raise ValueError(f'折清单已变化：{manifest}')
    options = {
        'architecture': architecture, 'input-size': RECIPES[architecture],
        'resize': 'letterbox', 'augmentation': args.augmentation,
        'class-weight-power': args.class_weight_power, 'batch-size': args.batch_size,
        'lr': 0.0001, 'freeze-epochs': 2, 'epochs': args.epochs,
        'patience': args.patience, 'seed': args.seed, 'device': args.device,
        'precision': args.precision, 'workers': 0,
    }
    # Git 提交号不能描述尚未提交的训练改动，因此记录实际参与运行的源码内容。
    module_root = Path(__file__).parent
    modules = ('__init__.py', 'train.py', 'model.py', 'augmentation.py',
               'calibrate.py', 'experiment_report.py', 'inference.py', 'cross_validation.py',
               'preprocessing/groups.py')
    return {
        'schema_version': 2,
        'data_plan': plan['identity'],
        'fold': {'number': fold['fold'], 'manifest_sha256': fold['sha256'],
                 'sources_sha256': digest(manifest.parent / 'sources.csv')},
        'labels_sha256': digest(args.labels),
        'training': options, 'development_only': True,
        'calibration_split': 'val', 'evaluation_split': 'test',
        'code_sha256': {name: digest(module_root / name) for name in modules},
        'packages': {name: version(name) for name in ('torch', 'torchvision', 'numpy', 'scikit-learn')},
    }


def training_completion(bundle, recipe):
    """只在训练子进程成功退出后生成凭据；单独存在最佳权重并不表示训练已结束。"""
    required = ('weights.pt', 'metadata.json', 'training.json')
    if any(not (bundle / name).is_file() for name in required):
        raise ValueError(f'训练产物不完整：{bundle}')
    metadata = json.loads((bundle / 'metadata.json').read_text(encoding='utf-8'))
    expected = {
        'manifest_sha256': recipe['fold']['manifest_sha256'],
        'architecture': recipe['training']['architecture'],
        'input_size': recipe['training']['input-size'],
    }
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise ValueError(f'训练包与当前折或模型方案不一致：{bundle}')
    return {
        'recipe': recipe,
        'weights_sha256': digest(bundle / 'weights.pt'),
        'history_sha256': digest(bundle / 'training.json'),
    }


def run(args, plan):
    """串行训练；完整折可跳过，完成训练的折可继续校准，未完成训练不伪装成续训。"""
    tasks = []
    # 先检查所有已存在的结果，避免跑完新折以后才发现另一个旧折配置不一致。
    for architecture in args.architectures:
        for fold in plan['folds']:
            folder = args.output / architecture / f"fold-{fold['fold']}"
            recipe = training_recipe(args, plan, fold, architecture)
            result_path = folder / 'result.json'
            marker = folder / 'training-complete.json'
            bundle = folder / 'bundle'
            complete, trained = result_path.exists(), marker.exists()
            if complete:
                previous = json.loads(result_path.read_text(encoding='utf-8'))
                if previous['recipe'] != recipe:
                    raise ValueError(f'已有结果配置不同：{result_path}')
            elif trained:
                previous = json.loads(marker.read_text(encoding='utf-8'))
                if previous != training_completion(bundle, recipe):
                    raise ValueError(f'训练完成标记或产物与当前方案不一致：{folder}')
            elif any((bundle / name).exists() for name in (
                'weights.pt', 'last-weights.pt', 'metadata.json', 'training.json',
            )):
                raise ValueError(f'该折训练中断且没有完成标记；请检查日志后明确重训，不自动覆盖：{folder}')
            tasks.append((architecture, fold, folder, recipe, complete, trained))

    for architecture, fold, folder, recipe, complete, trained in tasks:
        if complete:
            continue
        bundle = folder / 'bundle'
        folder.mkdir(parents=True, exist_ok=True)
        manifest = args.output / fold['manifest']
        common = ['--data-root', str(args.data_root), '--manifest', str(manifest)]
        # 命令从同一 recipe 生成，避免缓存身份与实际传给训练器的参数各写一份。
        options = [item for key, value in recipe['training'].items() for item in ('--' + key, str(value))]
        commands = [
            [sys.executable, '-m', 'ml.agrivision_ml.train', *common, '--labels', str(args.labels),
             '--output', str(bundle), *options, '--development-only'],
            [sys.executable, '-m', 'ml.agrivision_ml.calibrate', *common, '--bundle', str(bundle), '--device', args.device],
            [sys.executable, '-m', 'ml.agrivision_ml.experiment_report', *common, '--bundle', str(bundle), '--device', args.device, '--split', 'test'],
        ]
        write_json(folder / 'commands.json', commands)
        action = '继续校准与评估' if trained else '训练'
        print(f"{action} {architecture} 第 {fold['fold']}/{len(plan['folds'])} 折；日志：{folder / 'run.log'}", flush=True)
        # 恢复只跳过已完成训练；校准和评估都是固定权重上的幂等操作，可直接重新执行。
        # 长实验期间若源码或清单被编辑，后续子进程不能继续拿旧身份执行新方案。
        def execute(command, log):
            if training_recipe(args, plan, fold, architecture) != recipe:
                raise ValueError('实验运行期间代码或数据方案变化，已停止后续步骤，请核对版本')
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)

        with (folder / 'run.log').open('a' if trained else 'w', encoding='utf-8') as log:
            if not trained:
                execute(commands[0], log)
                write_json(folder / 'training-complete.json', training_completion(bundle, recipe))
            for command in commands[1:]:
                execute(command, log)
        result = {'recipe': recipe, 'architecture': architecture, 'fold': fold['fold'],
                  'outer': json.loads((bundle / 'evaluation-test.json').read_text(encoding='utf-8'))}
        write_json(folder / 'result.json', result)
        summarize(args.output, args.architectures, len(plan['folds']))
        print(f"完成 {architecture} 折 {fold['fold']}：外层 Macro-F1={result['outer']['macro_f1']:.4f}", flush=True)
    return summarize(args.output, args.architectures, len(plan['folds']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--labels', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--group-links', type=Path, help='人工确认同组表，CSV 两列 left、right，使用原清单相对图片路径')
    parser.add_argument('--folds', type=int, default=5)
    parser.add_argument('--inner-folds', type=int, default=5)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--architectures', nargs='+', choices=list(RECIPES), default=list(RECIPES))
    parser.add_argument('--epochs', type=int, default=20)
    parser.add_argument('--patience', type=int, default=6)
    parser.add_argument('--batch-size', type=int, default=16)
    parser.add_argument('--augmentation', choices=('light', 'field'), default='light')
    parser.add_argument('--class-weight-power', type=float, default=1.)
    parser.add_argument('--precision', choices=('bf16', 'amp', 'fp32'), default='bf16')
    parser.add_argument('--device', default='cuda')
    parser.add_argument('--run', action='store_true', help='实际运行；不加此参数时只生成折清单')
    args = parser.parse_args()
    if args.folds < 2 or args.inner_folds < 2:
        parser.error('内外折数都必须至少为 2')
    plan = prepare(args.manifest, args.output, folds=args.folds, seed=args.seed,
                   inner_folds=args.inner_folds, group_links=args.group_links)
    print(f"已准备 {len(plan['folds'])} 折；排除原测试集 {plan['excluded_original_test_images']} 张、"
          f"与原测试同组的开发图 {plan['excluded_test_group_development_images']} 张；未复制图片", flush=True)
    if args.run:
        run(args, plan)


if __name__ == '__main__':
    main()
