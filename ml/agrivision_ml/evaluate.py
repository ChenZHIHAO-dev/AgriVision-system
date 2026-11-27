# 评估已训练的分类模型。一次输出全量分类指标，以及经过置信分数和拒识条件筛选后的指标。
import argparse
import hashlib
import json
import torch
from pathlib import Path

from torch.utils.data import DataLoader
from .inference import Predictor, rejection_indices
from .train import Images, read_manifest, evaluate_loader


def require_activation_metrics(report):
    """正式与实验启用使用同一底线，统计整个留出集而非拒识后的少量样本。

    整体 accuracy / Macro-F1 均须至少 90%；保留原来的逐类样本数与召回下限。
    逐类下限是最低检查，不能据此声称每类都达到 90% 或已经通过田间验证。
    """
    if not (report["accuracy"] >= .90 and report["macro_f1"] >= .90
            and min(report["counts"]) >= 20 and min(report["recall"]) >= .6):
        raise ValueError("Activation requires overall accuracy >=.90, Macro-F1 >=.90, "
                         ">=20 test images/class and each recall >=.6")


def evaluate(args):
    torch.set_num_threads(4)
    predictor = Predictor(args.bundle, args.device)
    metadata = predictor.metadata
    # 从清单选择要评估的划分。复用训练时的标签顺序和固定变换，并逐张验证文件内容。
    rows = [r for r in read_manifest(args.manifest) if r["split"] == args.split]
    if not rows:
        raise ValueError("No images in requested split")
    loader = DataLoader(Images(args.data_root, rows, metadata["labels"], metadata["input_size"], resize=metadata.get("resize", "stretch")), batch_size=8)
    # 先在整个划分上统计准确率、各类召回、Macro-F1 和混淆矩阵。
    report = evaluate_loader(predictor.model, loader, predictor.device, len(metadata["labels"]))
    report.update({"split": args.split, "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(), "model_version": metadata["version"], "field_verified": args.field_verified})
    # 再按部署侧的温度、最高分阈值、分差阈值和保留类别过滤预测。
    rejected_indices = rejection_indices(metadata)
    total,accepted,correct=0,0,0
    with torch.inference_mode():
        for images,labels in loader:
            probabilities=(predictor.model(images.to(predictor.device))/float(metadata.get('temperature',1))).softmax(1).cpu()
            values,indices=probabilities.topk(2,dim=1)
            keep=(values[:,0]>=metadata['threshold'])&((values[:,0]-values[:,1])>=metadata['margin'])
            for index in rejected_indices:
                keep &= indices[:, 0] != index
            total+=len(labels);accepted+=int(keep.sum());correct+=int(((indices[:,0]==labels)&keep).sum())
    # 覆盖率是得到明确结果的样本比例。这里的 accuracy 只统计这些被接受的样本。
    report['selective']={'accepted':accepted,'total':total,'coverage':accepted/max(total,1),'accuracy':correct/max(accepted,1),'threshold':metadata['threshold'],'margin':metadata['margin']}
    # 先落盘评估报告。启用下方发布选项时，满足相应条件才会更新模型包的状态。
    path = args.bundle / f"evaluation-{getattr(args,'report_name',None) or args.split}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    # 正式启用要求 test 划分和操作者确认田间验证；整体指标与逐类底线共同检查。
    if args.activate:
        if metadata.get("development_only") or args.split != "test" or not args.field_verified:
            raise ValueError("Activation requires a real model, test split and operator-confirmed field verification")
        require_activation_metrics(report)
        metadata["validated"] = True
        metadata["field_verified"] = True
        metadata["test_report"] = report
        (args.bundle / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    # 实验启用要求使用原训练清单的留出测试集，并满足同一组指标门槛。模型包标记为可实验使用。
    if getattr(args,'activate_experimental',False):
        if metadata.get('development_only') or args.split!='test' or report['manifest_sha256']!=metadata['manifest_sha256']:
            raise ValueError('Experimental activation requires the real held-out training-manifest test split')
        require_activation_metrics(report)
        metadata.update({'development_ready':True,'validated':False,'release_stage':'experimental','field_verified':False,'test_report':report})
        (args.bundle/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate a classifier and optionally activate a field-verified bundle")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--split", choices=["val", "test"], default="test")
    parser.add_argument("--device", default="auto")
    # 一次评估可选择正式启用或实验启用中的一种。常规评估只生成报告。
    activation = parser.add_mutually_exclusive_group()
    activation.add_argument("--activate", action="store_true")
    activation.add_argument('--activate-experimental',action='store_true',help='Enable local internal-data testing only; does not claim field validation')
    # 启用模型时可单独保存门槛检查，保留 experiment_report 生成的逐类/来源报告。
    parser.add_argument('--report-name', choices=['external-jic', 'activation'], default=None)
    parser.add_argument("--field-verified", action="store_true")
    print(json.dumps(evaluate(parser.parse_args()), indent=2))
