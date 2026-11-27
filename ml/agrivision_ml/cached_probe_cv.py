"""共享冻结特征的分组线性头对照，再用原始 train/val 重新拟合内测候选。

骨干没有学习本项目标签，因此 clean/增强特征可以跨折共享；训练头时必须按
每一折的路径索引取数据，验证和评估只取 clean。最终 test 不进入特征补齐或
交叉验证，架构选择写定之后才读取一次。磁盘仅增加特征和实验结果，不复制图片。
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import random
from types import SimpleNamespace
import warnings

import numpy as np
import sklearn
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
import torch
from torch import nn

from . import linear_probe as probe
from .cross_validation import RECIPES, check_partition
from .experiment_report import save_confusion
from .inference import rejection_indices
from .train import read_manifest, _task_metadata


def identity(args, plan):
    """把数据、实际代码和固定参数绑定；恢复运行不能悄悄混入另一套实验。"""
    code = ('cached_probe_cv.py', 'linear_probe.py', 'model.py', 'augmentation.py', 'train.py', 'inference.py')
    return {'manifest_sha256': probe.digest(args.manifest), 'labels_sha256': probe.digest(args.labels),
            'fold_plan_sha256': probe.digest(args.cv_root / 'folds.json'),
            'fold_plan_identity': plan['identity'], 'architectures': args.architectures,
            'views': args.views, 'augmentation': args.augmentation, 'seed': args.seed,
            'c_values': args.c_values, 'min_test_accuracy': args.min_test_accuracy,
            'libraries': {'torch': torch.__version__, 'torchvision': probe.torchvision.__version__,
                          'pillow': probe.PIL.__version__, 'numpy': np.__version__, 'sklearn': sklearn.__version__},
            'min_test_macro_f1': args.min_test_macro_f1,
            'code': {name: probe.digest(Path(__file__).with_name(name)) for name in code}}


def load_plan(args, labels):
    """使用已经冻结的分组折；检查它与当前原始清单一致，且原 test 没有漏入。"""
    original = read_manifest(args.manifest)
    check_partition(original, labels)
    plan = json.loads((args.cv_root / 'folds.json').read_text(encoding='utf-8'))
    if plan['identity']['manifest_sha256'] != probe.digest(args.manifest):
        raise ValueError('分组折与原始清单不一致')
    original_by_path = {row['path']: row for row in original}
    final_test = {row['path'] for row in original if row['split'] == 'test'}
    final_test_groups = {row['group'] for row in original if row['split'] == 'test'}
    folds, expected_paths, exposure = [], None, Counter()
    for item in plan['folds']:
        path = args.cv_root / item['manifest']
        if probe.digest(path) != item['sha256']:
            raise ValueError('冻结折清单发生变化')
        rows = read_manifest(path)
        check_partition(rows, labels)
        paths = {row['path'] for row in rows}
        if len(paths) != len(rows) or paths & final_test:
            raise ValueError('折清单有重复路径或包含原始最终 test')
        for row in rows:
            source = original_by_path.get(row['path'])
            if source is None or any(row[key] != source[key] for key in ('label', 'sha256', 'group')):
                raise ValueError('折中的图片、标签或采集组与原始清单不一致')
            if row['group'] in final_test_groups:
                raise ValueError('最终 test 的同源组进入了开发折')
        if expected_paths is None:
            expected_paths = paths
        elif expected_paths != paths:
            raise ValueError('各折开发图片范围不一致')
        exposure.update(row['path'] for row in rows if row['split'] == 'test')
        folds.append((item['fold'], rows))
    if not expected_paths or set(exposure) != expected_paths or any(n != 1 for n in exposure.values()):
        raise ValueError('开发图必须且只能贡献一次外层评估预测')
    development = [row for row in original if row['path'] in expected_paths]
    return original, development, folds, plan


def atomic_cache(path, values, sidecar, metadata):
    temporary = path.with_name('.' + path.stem + '.pending.npz')
    np.savez_compressed(temporary, **values)
    metadata = {**metadata, 'cache_sha256': probe.digest(temporary)}
    temporary.replace(path)
    probe.write_json(sidecar, metadata)


def development_cache(args, architecture, model, rows, labels, first_fold, recipe):
    """复用已完成 fold1 的所有 clean 和训练增强特征，只编码缺失的视图。

    数组第一维是图，第二维是视图。view0 固定；view1/2 随机轻增强。
    同一张图在不同折可成为训练图或评估图，但只有训练索引能取 view1/2。
    """
    folder = args.output / architecture
    folder.mkdir(parents=True, exist_ok=True)
    cache, sidecar = folder / 'features.npz', folder / 'features.json'
    backbone_hash = probe.backbone_digest(model)
    expected = {'recipe': recipe, 'architecture': architecture, 'input_size': RECIPES[architecture],
                'backbone_sha256': backbone_hash,
                'entries': [{'path': r['path'], 'sha256': r['sha256'], 'label': r['label']} for r in rows]}
    probe.validate_source_images(args.data_root, rows)
    if cache.exists() and sidecar.exists():
        saved = json.loads(sidecar.read_text(encoding='utf-8'))
        if saved['identity'] != expected or saved['cache_sha256'] != probe.digest(cache):
            raise ValueError('共享特征缓存身份或内容发生变化')
        with np.load(cache) as values:
            return {key: values[key] for key in values.files}

    reused_folder = args.reuse_probes / architecture / 'fold-1'
    if not (reused_folder / 'features.npz').is_file():
        raise ValueError('缺少已有 fold1 特征；本入口不会悄悄重新编码全套骨干')
    # 复用原组件核对骨干、库版本、变换代码、种子、原图及缓存校验值。
    reused_args = SimpleNamespace(**{**vars(args), 'output': reused_folder,
        'manifest': args.cv_root / 'folds/fold-1/manifest.csv', 'architecture': architecture,
        'input_size': RECIPES[architecture]})
    previous = probe.feature_cache(reused_args, model, first_fold, labels)
    by_path = {row['path']: index for index, row in enumerate(rows)}
    dimensions = previous['train_x'].shape[1]
    features = np.empty((len(rows), args.views + 1, dimensions), dtype=np.float32)
    available = np.zeros((len(rows), args.views + 1), dtype=bool)
    provenance = [[None] * (args.views + 1) for _ in rows]
    reused_hash = probe.digest(reused_folder / 'features.json')
    for split in ('train', 'val', 'test'):
        subset = [row for row in first_fold if row['split'] == split]
        indices = np.array([by_path[row['path']] for row in subset])
        expected_y = np.array([labels.index(row['label']) for row in subset])
        count = len(subset)
        views = args.views + 1 if split == 'train' else 1
        if previous[split + '_x'].shape[0] != count * views:
            raise ValueError('旧特征视图数量与行顺序不一致')
        if not np.array_equal(previous[split + '_y'], np.tile(expected_y, views)):
            raise ValueError('旧特征标签顺序与清单不一致')
        for view in range(views):
            features[indices, view] = previous[split + '_x'][view * count:(view + 1) * count]
            available[indices, view] = True
            for index in indices:
                provenance[index][view] = {'view': view, 'origin': 'existing_fold1_cache',
                                          'source_cache_identity_sha256': reused_hash}
    missing_counts = {}
    for view in range(args.views + 1):
        missing = np.flatnonzero(~available[:, view])
        missing_counts[str(view)] = len(missing)
        if not len(missing):
            continue
        subset = [rows[index] for index in missing]
        seed = args.seed + max(0, view - 1)
        torch.manual_seed(seed); random.seed(seed); np.random.seed(seed)
        vectors, targets = probe.encode(model, args.data_root, subset, labels, RECIPES[architecture],
            training=view > 0, augmentation=args.augmentation, batch_size=args.batch_size)
        if not np.array_equal(targets, [labels.index(row['label']) for row in subset]):
            raise ValueError('补充特征的图片顺序变化')
        features[missing, view] = vectors
        available[missing, view] = True
        for index in missing:
            provenance[index][view] = {'view': view, 'origin': 'encoded_missing_view', 'batch_sequence_seed': seed}
    values = {'features': features, 'targets': np.array([labels.index(r['label']) for r in rows])}
    atomic_cache(cache, values, sidecar, {'identity': expected, 'view_provenance': provenance,
        'encoded_missing_views': missing_counts,
        'reused_feature_file': str(reused_folder / 'features.npz'),
        'reused_feature_sha256': probe.digest(reused_folder / 'features.npz')})
    print(json.dumps({'cache': str(cache), 'encoded_missing_views': missing_counts}), flush=True)
    return values


def split_features(values, data_rows, fold_rows, split):
    """train 可使用全部视图；val/test 强制 view0，杜绝增强图混进评估数量。"""
    index = {row['path']: number for number, row in enumerate(data_rows)}
    selected = [row for row in fold_rows if row['split'] == split]
    positions = np.array([index[row['path']] for row in selected])
    features = values['features'][positions]
    targets = values['targets'][positions]
    if split == 'train':
        return np.concatenate([features[:, v] for v in range(features.shape[1])]), np.tile(targets, features.shape[1]), selected
    return features[:, 0], targets, selected


def select_head(training, validation, c_values, classes):
    """仅按当前折的 train 拟合分类权重，当前折的 inner val 选择正则强度。"""
    train_x, train_y, _ = training
    val_x, val_y, _ = validation
    candidates, best, best_score = [], None, -1.
    for strength in c_values:
        classifier = LogisticRegression(C=strength, class_weight='balanced', max_iter=2000, tol=1e-4)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always', ConvergenceWarning)
            classifier.fit(train_x, train_y)
        converged = not any(issubclass(item.category, ConvergenceWarning) for item in caught)
        score = probe.prediction_metrics(val_y, classifier.predict(val_x), classes)
        candidates.append({'C': strength, 'converged': converged, 'iterations': classifier.n_iter_.tolist(), 'validation': score})
        if converged and score['macro_f1'] > best_score:
            best, best_score = classifier, score['macro_f1']
    if best is None:
        raise ValueError('所有线性头候选未收敛，不生成模型包')
    return best, candidates


def logits_for(classifier, features):
    weights, bias = probe.linear_weights(classifier)
    return torch.from_numpy(features @ weights.T + bias)


def fit_calibration(classifier, validation, metadata):
    """和现有校准入口同一温度/门限网格，但直接使用缓存 logits，不再跑骨干。

    调参只能看到内层 val；外层及最终 test 只使用拟合完的固定参数。
    找不到合格网格时明确报告 selection_qualified=False，不伪造98%保证。
    """
    features, targets, _ = validation
    logits = logits_for(classifier, features)
    truth = torch.from_numpy(targets)
    temperatures = np.linspace(.5, 3., 51)
    losses = [float(torch.nn.functional.cross_entropy(logits / float(t), truth)) for t in temperatures]
    temperature = float(temperatures[int(np.argmin(losses))])
    scores = (logits / temperature).softmax(1)
    top, indices = scores.topk(2, dim=1)
    prediction = indices[:, 0].numpy()
    confidence = top[:, 0].numpy(); margins = (top[:, 0] - top[:, 1]).numpy()
    known = ~np.isin(prediction, rejection_indices(metadata))
    choices = []
    for threshold in (.6, .65, .7, .75, .8, .85, .9, .95, .98):
        for gap in (.05, .1, .12, .15, .2, .25):
            accepted = (confidence >= threshold) & (margins >= gap) & known
            count = int(accepted.sum())
            accuracy = float((prediction[accepted] == targets[accepted]).mean()) if count else 0.
            if count >= 30 and accuracy >= .98:
                choices.append((count, accuracy, threshold, gap))
    chosen = max(choices, key=lambda value: tuple(value)) if choices else (0, 0., .98, .25)
    accepted = (confidence >= chosen[2]) & (margins >= chosen[3]) & known
    count = int(accepted.sum())
    return {'temperature': temperature, 'threshold': chosen[2], 'margin': chosen[3],
            'selection_split': 'inner_val', 'selection_qualified': bool(choices), 'images': len(targets),
            'nll_before': float(torch.nn.functional.cross_entropy(logits, truth)), 'nll_after': min(losses),
            'accepted': count, 'coverage': count / len(targets),
            'accepted_accuracy': float((prediction[accepted] == targets[accepted]).mean()) if count else None}


def evaluate_head(classifier, partition, labels, calibration, metadata):
    features, targets, rows = partition
    scores = (logits_for(classifier, features) / calibration['temperature']).softmax(1)
    top, index = scores.topk(2, dim=1)
    predicted = index[:, 0].numpy()
    known = ~np.isin(predicted, rejection_indices(metadata))
    accepted = (top[:, 0].numpy() >= calibration['threshold']) & ((top[:, 0] - top[:, 1]).numpy() >= calibration['margin']) & known
    result = probe.prediction_metrics(targets, predicted, len(labels))
    result.update({'images': len(rows), 'groups': len({r['group'] for r in rows}),
        'selective': {'accepted': int(accepted.sum()), 'coverage': float(accepted.mean()),
                      'accuracy': float((predicted[accepted] == targets[accepted]).mean()) if accepted.any() else None}})
    records = [{'path': row['path'], 'group': row['group'], 'true': labels[int(target)],
        'predicted': labels[int(prediction)], 'confidence': float(top[i, 0]),
        'margin': float(top[i, 0] - top[i, 1]), 'correct': bool(target == prediction), 'accepted': bool(accepted[i])}
        for i, (row, target, prediction) in enumerate(zip(rows, targets, predicted))]
    return result, records


def save_predictions(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def run_folds(args, architecture, values, data_rows, folds, labels, config, recipe):
    results = []
    for number, rows in folds:
        folder = args.output / architecture / f'fold-{number}'
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / 'result.json'
        if path.exists():
            result = json.loads(path.read_text(encoding='utf-8'))
            if result['recipe'] != recipe:
                raise ValueError('已完成线性头折的配置变化')
            results.append(result); continue
        training = split_features(values, data_rows, rows, 'train')
        validation = split_features(values, data_rows, rows, 'val')
        classifier, search = select_head(training, validation, args.c_values, len(labels))
        metadata = {**_task_metadata(config), 'labels': labels}
        calibration = fit_calibration(classifier, validation, metadata)
        outer, predictions = evaluate_head(classifier, split_features(values, data_rows, rows, 'test'), labels, calibration, metadata)
        counts = Counter(r['label'] for r in training[2])
        result = {'recipe': recipe, 'architecture': architecture, 'fold': number, 'selected_C': classifier.C,
            'class_counts_train_only': dict(counts),
            'class_weights_train_only': {label: len(training[2]) / (len(labels) * counts[label]) for label in labels},
            'calibration': calibration, 'outer': outer, 'evaluation_scope': 'development_grouped_outer_fold'}
        weights, bias = probe.linear_weights(classifier)
        np.savez_compressed(folder / 'head.npz', weights=weights, bias=bias)
        probe.write_json(folder / 'search.json', search)
        save_predictions(folder / 'predictions.csv', predictions)
        save_confusion(outer['confusion_matrix'], labels, folder / 'confusion.png')
        probe.write_json(path, result)
        results.append(result)
        print(json.dumps({'architecture': architecture, 'fold': number, 'accuracy': outer['accuracy'], 'macro_f1': outer['macro_f1']}), flush=True)
    scores = [r['outer']['macro_f1'] for r in results]
    return {'architecture': architecture, 'completed_folds': len(results),
            'mean_macro_f1': float(np.mean(scores)), 'std_macro_f1': float(np.std(scores, ddof=1)),
            'mean_accuracy': float(np.mean([r['outer']['accuracy'] for r in results])),
            'out_of_fold': probe.metrics(np.sum([r['outer']['confusion_matrix'] for r in results], axis=0))}


def validate_acceptance_thresholds(args):
    """允许提高验收线，不允许通过降低配置把较弱结果标成通过。

    开发训练和指标记录仍可保留不达标的方法；验收配置仅决定候选是否达标。
    run 和 final_refit 都调用此检查，直接 Python 调用也不能绕过命令行限制。
    """
    if any(not .93 <= score <= 1 for score in (args.min_test_accuracy, args.min_test_macro_f1)):
        raise ValueError("内部验收 accuracy 和 Macro-F1 阈值必须在 .93 到 1 之间")


def final_refit(args, architecture, model, values, development, original, labels, config, recipe):
    """从原始 train/val 重训头，独立 test 只验收一次；不把某个CV折改旗标发布。"""
    validate_acceptance_thresholds(args)
    folder = args.output / 'final-refit'
    folder.mkdir(parents=True, exist_ok=True)
    result_path = folder / 'result.json'
    if result_path.exists():
        previous = json.loads(result_path.read_text(encoding='utf-8'))
        if previous['recipe'] != recipe or previous['architecture'] != architecture:
            raise ValueError('最终测试已经使用，不能更改配置后覆盖同一验收结果')
        print('复用已经完成的最终测试验收；不再次调参或评测', flush=True)
        return previous
    development_paths = {r['path'] for r in development}
    if any(r['path'] not in development_paths for r in original if r['split'] != 'test'):
        raise ValueError('存在与最终测试相关而被开发折排除的图片，不能直接重训原始划分')
    training = split_features(values, development, original, 'train')
    validation = split_features(values, development, original, 'val')
    classifier, search = select_head(training, validation, args.c_values, len(labels))
    task = _task_metadata(config)
    calibration = fit_calibration(classifier, validation, {**task, 'labels': labels})
    calibration['selection_split'] = 'original_val'
    # 把测试前已经固定的参数单独记下。不会用最终测试结果回头选 C、温度或架构。
    fixed = {'architecture': architecture, 'selected_C': classifier.C, 'calibration': calibration,
             'recipe': recipe, 'acceptance_rule': {'accuracy': args.min_test_accuracy, 'macro_f1': args.min_test_macro_f1}}
    fixed_path = folder / 'pre-test-selection.json'
    if fixed_path.exists() and json.loads(fixed_path.read_text(encoding='utf-8')) != fixed:
        raise ValueError('测试前固定的选择已经不同，不允许覆盖验收条件')
    probe.write_json(fixed_path, fixed)
    testing_rows = [r for r in original if r['split'] == 'test']
    test_x, test_y = probe.encode(model, args.data_root, testing_rows, labels, RECIPES[architecture], batch_size=args.batch_size)
    result, predictions = evaluate_head(classifier, (test_x, test_y, testing_rows), labels, calibration, {**task, 'labels': labels})
    accepted = result['accuracy'] >= args.min_test_accuracy and result['macro_f1'] >= args.min_test_macro_f1
    model = probe.install_head(model, architecture, classifier, len(labels))
    bundle = folder / 'bundle'; bundle.mkdir(exist_ok=True)
    torch.save(model.state_dict(), bundle / 'weights.pt')
    metadata = {'schema_version': 1, **task, 'architecture': architecture, 'labels': labels,
        'label_names': config['labels'], 'input_size': RECIPES[architecture], 'normalization': 'imagenet',
        'resize': 'letterbox', 'augmentation': args.augmentation,
        'version': datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S'),
        **{k: calibration[k] for k in ('temperature', 'threshold', 'margin')},
        'validated': False, 'development_only': False, 'development_ready': False,
        'field_verified': False, 'release_stage': 'candidate', 'method': 'frozen_imagenet_grouped_cv_linear_refit',
        'manifest_sha256': probe.digest(args.manifest), 'seed': args.seed, 'pretrained': True,
        'device': 'cpu', 'precision': 'fp32', 'calibration': calibration,
        'internal_acceptance_passed': accepted, 'final_test': result,
        'training_config': {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()}}
    probe.write_json(bundle / 'metadata.json', metadata)
    probe.write_json(folder / 'search.json', search)
    save_predictions(folder / 'predictions-test.csv', predictions)
    save_confusion(result['confusion_matrix'], labels, folder / 'confusion-test.png')
    report = {'recipe': recipe, 'architecture': architecture, 'selected_C': classifier.C,
        'calibration': calibration, 'test': result, 'internal_acceptance_passed': accepted,
        'evaluation_scope': 'original_final_test_after_development_selection',
        'limitation': '仅当前来源的内部验收，非国内田间验证；候选包未自动启用服务。',
        'weights_sha256': probe.digest(bundle / 'weights.pt')}
    probe.write_json(result_path, report)
    print(json.dumps({'final_refit': architecture, 'accuracy': result['accuracy'], 'macro_f1': result['macro_f1'], 'internal_acceptance_passed': accepted}), flush=True)
    return report


def run(args):
    validate_acceptance_thresholds(args)
    torch.set_num_threads(args.threads)
    config = json.loads(args.labels.read_text(encoding='utf-8-sig')); labels = list(config['labels'])
    original, development, folds, plan = load_plan(args, labels)
    recipe = identity(args, plan)
    args.output.mkdir(parents=True, exist_ok=True)
    recipe_path = args.output / 'recipe.json'
    if recipe_path.exists() and json.loads(recipe_path.read_text(encoding='utf-8')) != recipe:
        raise ValueError('共享缓存线性对照的已有配置不同，请核对，不自动覆盖')
    probe.write_json(recipe_path, recipe)
    summaries = []
    for architecture in args.architectures:
        model = probe.build_model(architecture, len(labels), pretrained=True).eval().requires_grad_(False)
        probe.replace_head(model, architecture, nn.Identity())
        values = development_cache(args, architecture, model, development, labels, folds[0][1], recipe)
        summaries.append(run_folds(args, architecture, values, development, folds, labels, config, recipe))
        probe.write_json(args.output / 'summary.json', {'evaluation_scope': 'development_grouped_linear_probe', 'models': summaries})
        del model, values
    chosen = max(summaries, key=lambda result: result['mean_macro_f1'])['architecture']
    selection = {'architecture': chosen, 'rule': 'highest mean outer development macro_f1; original test unused', 'recipe': recipe}
    selection_path = args.output / 'selection.json'
    if selection_path.exists() and json.loads(selection_path.read_text(encoding='utf-8')) != selection:
        raise ValueError('原测试之前的架构选择已固定，不能改写')
    probe.write_json(selection_path, selection)
    model = probe.build_model(chosen, len(labels), pretrained=True).eval().requires_grad_(False)
    probe.replace_head(model, chosen, nn.Identity())
    values = development_cache(args, chosen, model, development, labels, folds[0][1], recipe)
    return final_refit(args, chosen, model, values, development, original, labels, config, recipe)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('data-root', 'manifest', 'labels', 'cv-root', 'reuse-probes', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--architectures', nargs='+', choices=list(RECIPES), default=list(RECIPES))
    parser.add_argument('--views', type=int, default=2)
    parser.add_argument('--augmentation', choices=('light', 'field'), default='light')
    parser.add_argument('--batch-size', type=int, default=16)
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--c-values', type=float, nargs='+', default=[.1, 1., 10.])
    parser.add_argument('--min-test-accuracy', type=float, default=.93)
    parser.add_argument('--min-test-macro-f1', type=float, default=.93)
    args = parser.parse_args()
    if args.views < 0 or args.threads < 1 or args.batch_size < 1 or any(c <= 0 for c in args.c_values):
        parser.error('视图数非负；线程、批量和 C 必须为正数')
    try:
        validate_acceptance_thresholds(args)
    except ValueError as exc:
        parser.error(str(exc))
    run(args)


if __name__ == '__main__':
    main()
