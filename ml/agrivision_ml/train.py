# 分类训练入口。流程依次是校验数据清单、按划分读图、训练与验证、保存最佳权重。
# 模型结构和增强规则在 model.py，命令行参数在本文件末尾的 parser()。
import argparse
import csv
from datetime import datetime, timezone
import hashlib
from itertools import islice
import json
from pathlib import Path
import random
import time

import numpy as np
from PIL import Image
import torch
from torch.utils.data import DataLoader, Dataset
from tqdm import tqdm

from . import ARCHITECTURES, MOBILENET_V4
from .model import build_model, preprocessing
from .inference import CROP_IDENTIFICATION_TASK, CROP_REJECTION_LABELS, select_device


# 模型包用 crop 标记某一作物的病害分类，用 task 标记识别作物种类。两个任务共用下方的训练流程。
def _task_metadata(config):
    if config.get("task") != CROP_IDENTIFICATION_TASK:
        return {"crop": config["crop"]}

    # 作物分类至少需要两个有效的标签项，并至少包含一个具体作物 ID。保留类别用于表示其他或未知作物。
    labels = config["labels"]
    if (
        not isinstance(labels, dict)
        or len(labels) < 2
        or not set(labels).difference(CROP_REJECTION_LABELS)
        or any(
            not label or label.strip() != label or not isinstance(name, str) or not name.strip()
            for label, name in labels.items()
        )
    ):
        raise ValueError(
            "Crop identification requires at least two named labels with trimmed IDs "
            "and at least one non-reserved crop ID"
        )
    return {"task": CROP_IDENTIFICATION_TASK}


# confusion_matrix 的行是真实类别，列是预测类别。对角线统计分类正确的数量。
def metrics(matrix):
    matrix = np.asarray(matrix)
    tp = np.diag(matrix)
    # 召回率按行计算，精确率按列计算。没有样本或没有预测的类别按 0 处理。Macro-F1 是各类别 F1 的算术平均。
    recall = np.divide(tp, matrix.sum(1), out=np.zeros(len(tp), dtype=float), where=matrix.sum(1) != 0)
    precision = np.divide(tp, matrix.sum(0), out=np.zeros(len(tp), dtype=float), where=matrix.sum(0) != 0)
    f1 = np.divide(2 * precision * recall, precision + recall, out=np.zeros(len(tp), dtype=float), where=precision + recall != 0)
    return {"accuracy":float(tp.sum()/max(1,matrix.sum())),"macro_f1": float(f1.mean()),"balanced_accuracy":float(recall.mean()),"precision":precision.tolist(),"f1":f1.tolist(), "recall": recall.tolist(), "counts": matrix.sum(1).tolist(), "confusion_matrix": matrix.tolist()}


# 每行记录文件相对路径、类别、采集组、图像校验值和数据划分。接受 Excel 写出的 UTF-8 BOM。
def read_manifest(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    # 同一采集组或字节相同的图片只能属于一个划分，否则同源样本可能同时进入训练和评估。
    groups = {}
    for row in rows:
        if row["split"] not in {"train", "val", "test"}:
            raise ValueError("Unknown dataset split")
        for key in (row["group"], row["sha256"]):
            if key in groups and groups[key] != row["split"]:
                raise ValueError("A source group or image appears in multiple splits")
            groups[key] = row["split"]
    return rows


# 按需从清单读图。DataLoader 每请求一个索引，这里返回一个图像张量和对应的类别下标。
class Images(Dataset):
    def __init__(self, root, rows, labels, size, training=False):
        self.root, self.rows, self.labels = root.resolve(), rows, labels
        # 训练传入 training=True，每次读图都会重新抽取增强参数。验证、校准和评估沿用固定的图像变换。
        self.transform = preprocessing(size, training)
        self.verify_each_read = True

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        # 实际文件必须位于图像根目录内。启用校验时，文件内容还必须与清单记录一致。
        path = (self.root / row["path"]).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Image path escapes dataset root")
        if self.verify_each_read and hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("Dataset image changed after manifest creation")
        with Image.open(path) as image:
            tensor = self.transform(image.convert("RGB"))
        # 分类层使用整数下标作为监督目标，所以推理时也要按相同的 labels 顺序解释输出。
        return tensor, self.labels.index(row["label"])


# 将标签平滑和类别权重用于交叉熵。先返回总损失和目标类别权重之和，批内与整轮都按这个权重归一化。
def classification_loss(logits, targets, class_weights):
    # label_smoothing=.03 给每类留一点监督概率，缓和模型把正确类别的分数推到极端的倾向。
    loss_sum = torch.nn.functional.cross_entropy(
        logits, targets, weight=class_weights, label_smoothing=.03, reduction="sum",
    )
    return loss_sum, class_weights[targets].sum()


# 验证只做前向计算，并使用评估模式下的归一化层和随机失活层。测试评估也复用此函数。
@torch.inference_mode()
def evaluate_loader(model, loader, device, classes, *, class_weights=None, progress=None):
    model.eval()
    matrix = np.zeros((classes, classes), dtype=int)
    loss_sum = torch.zeros((), device=device)
    weight_sum = torch.zeros_like(loss_sum)
    batches = loader
    if progress:
        batches = tqdm(loader, desc=progress, unit="batch", disable=None, leave=False, dynamic_ncols=True)
    # 用最大 logit 的类别更新混淆矩阵。权重存在时同时累计验证损失，便于和训练 loss 对照。
    for images, labels in batches:
        logits = model(images.to(device))
        if class_weights is not None:
            batch_loss, batch_weight = classification_loss(logits, labels.to(device), class_weights)
            loss_sum += batch_loss
            weight_sum += batch_weight
        predictions = logits.argmax(1).cpu().numpy()
        for true, predicted in zip(labels.numpy(), predictions):
            matrix[int(true), int(predicted)] += 1
    report = metrics(matrix)
    if class_weights is not None:
        report["val_loss"] = (loss_sum / weight_sum).item()
    return report


def train(args):
    from .training_curves import save_training_curves

    # 设置 CPU 算子线程数和三套随机种子。随后读取标签、选设备，并检查清单与标签文件是否对应。
    torch.set_num_threads(4)
    torch.manual_seed(args.seed)
    random.seed(args.seed)
    np.random.seed(args.seed)
    device = select_device(args.device)
    config = json.loads(args.labels.read_text(encoding="utf-8"))
    task_metadata = _task_metadata(config)
    labels = list(config["labels"])
    rows = read_manifest(args.manifest)
    if set(r["label"] for r in rows) != set(labels):
        raise ValueError("Manifest classes must exactly match the label configuration")
    # 开始训练前一次性校验清单里每张图的路径和 SHA-256，确认内容与生成清单时一致。
    for row in tqdm(rows, desc="Checking dataset", unit="image", disable=None, leave=False, dynamic_ncols=True):
        path = (args.data_root/row['path']).resolve()
        if not path.is_relative_to(args.data_root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:
            raise ValueError('Dataset does not match its manifest')
    # 分别建立训练和验证 DataLoader。训练会随机打乱并增强，验证按固定顺序读图。测试集留给独立评估。
    loaders = {}
    for split in ('train','val'):
        dataset = Images(args.data_root,[row for row in rows if row['split']==split],labels,args.input_size,split=='train')
        # 启动前已经查过文件哈希，训练轮次里直接解码即可。workers 控制读图进程，CUDA 时使用锁页内存。
        dataset.verify_each_read = False
        workers = getattr(args,'workers',0)
        loaders[split] = DataLoader(dataset,batch_size=args.batch_size,shuffle=split=='train',num_workers=workers,pin_memory=device.type=='cuda',persistent_workers=workers>0)
    if any(len(loader.dataset) == 0 for loader in loaders.values()):
        raise ValueError("Both train and val splits require images")
    # 初始化网络和 AdamW。优化器先持有整个网络的参数，后续解冻骨干时可继续使用同一个优化器。
    model = build_model(args.architecture, len(labels), not args.no_pretrained).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=.01)
    # CUDA 可以使用 AMP 混合精度。自动模式下 MobileNetV4 用 FP32，其他 CUDA 架构用 AMP。
    precision = getattr(args, "precision", "auto")
    use_amp = device.type == "cuda" and (
        precision == "amp" or (precision == "auto" and args.architecture != MOBILENET_V4)
    )
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
    updates = 0

    # 只统计实际执行的优化器更新。AMP 遇到无效梯度时可能跳过一步，读过一个批次并不一定更新了参数。
    def count_update(_optimizer, _args, _kwargs):
        nonlocal updates
        updates += 1

    optimizer.register_step_post_hook(count_update)
    # 按训练集中的类别频率设置损失权重。样本少的类权重较高，读图比例仍由 DataLoader 决定。
    counts = np.array([sum(row['label']==label and row['split']=='train' for row in rows) for label in labels])
    if not counts.all(): raise ValueError('Every class needs training images')
    class_weights = torch.tensor(counts.sum()/(len(labels)*counts),dtype=torch.float32,device=device)
    # 用余弦调度降低学习率，目标下限是初始学习率的 5%。后面只在当轮确有参数更新时推进调度。
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,T_max=args.epochs,eta_min=args.lr*.05)
    best, stale, history = -1., 0, []
    args.output.mkdir(parents=True, exist_ok=True)
    # 模型包记录结构、标签顺序、输入尺寸、清单哈希和训练参数。校准、评估和部署都需要按这些信息解释权重。
    metadata = {"schema_version": 1, **task_metadata, "architecture": args.architecture, "labels": labels, "label_names": config["labels"], "input_size": args.input_size, "normalization": "imagenet", "resize": "stretch", "version": datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"), "threshold": .7, "margin": .12, "validated": False, "development_only": args.development_only or bool(args.max_batches), "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(), "seed": args.seed}
    metadata.update({'pretrained':not args.no_pretrained,'temperature':1.0,'release_stage':'training','training_config':{key:str(value) if isinstance(value,Path) else value for key,value in vars(args).items()},'train_counts':counts.tolist(),'torch':torch.__version__,'device':str(device)})
    metadata["precision"] = "amp" if use_amp else "fp32"
    train_loader = loaders["train"]
    # max_batches 可截取少量训练批次做流程检查。这类模型包会标为仅供开发使用。
    train_steps = min(len(train_loader), args.max_batches) if args.max_batches > 0 else len(train_loader)
    for epoch in range(args.epochs):
        epoch_progress = f"Epoch {epoch + 1}/{args.epochs}"
        started = time.perf_counter()
        previous_updates = updates
        # 前 freeze_epochs 轮只训练分类头，骨干保持评估模式并关闭梯度。之后解冻整个网络一起更新。
        train_backbone = epoch >= args.freeze_epochs
        model.train(train_backbone)
        model.requires_grad_(train_backbone)
        model.classifier.train().requires_grad_(True)
        # 为当前轮次单独累计加权损失、权重和 Top-1 正确数。
        loss_sum = torch.zeros((), device=device)
        weight_sum = torch.zeros_like(loss_sum)
        correct = torch.zeros((), dtype=torch.long, device=device)
        samples = 0
        # 逐批读取训练集。进度条的总批次数也会反映 max_batches 的限制。
        with tqdm(
            islice(train_loader, train_steps), total=train_steps, desc=f"{epoch_progress} train",
            unit="batch", disable=None, leave=False, dynamic_ncols=True,
        ) as batches:
            for images, target in batches:
                # 跳过只有一张图的尾批，避免训练态归一化层遇到单样本批次。
                if len(images) < 2:
                    continue
                # 每批清掉上一批梯度。前向得到 logits，计算加权平均损失，再反向传播和更新参数。
                optimizer.zero_grad(set_to_none=True)
                target = target.to(device)
                with torch.autocast(device_type=device.type, enabled=use_amp):
                    logits = model(images.to(device))
                    batch_loss, batch_weight = classification_loss(logits, target, class_weights)
                    loss = batch_loss / batch_weight
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
                # 记录指标时从计算图分离损失和预测，避免把反向传播的数据保留到后续批次。
                loss_sum += batch_loss.detach()
                weight_sum += batch_weight
                correct += (logits.detach().argmax(1) == target).sum()
                samples += target.numel()
        # 训练批次结束后在验证集上跑一遍。报告同时记录训练与验证指标、当轮学习率和实际更新次数。
        report = evaluate_loader(
            model, loaders["val"], device, len(labels), class_weights=class_weights,
            progress=f"{epoch_progress} validation",
        )
        report.update({
            "epoch": epoch + 1,
            "loss": (loss_sum / weight_sum).item() if samples else None,
            "train_accuracy": correct.item() / samples if samples else None,
            "seconds": round(time.perf_counter() - started, 2),
            "lr": optimizer.param_groups[0]["lr"],
        })
        report["optimizer_updates"] = updates - previous_updates
        history.append(report)
        print(json.dumps({
            "epoch": epoch + 1,
            "loss": report["loss"],
            "val_loss": report["val_loss"],
            "train_accuracy": report["train_accuracy"],
            "val_accuracy": report["accuracy"],
            "val_macro_f1": report["macro_f1"],
            "device": str(device),
            "optimizer_updates": report["optimizer_updates"],
        }), flush=True)
        # 有实际更新且验证 Macro-F1 刷新时，保存当前权重与配置，并清零早停计数。少数类与多数类都参与该指标。
        if report["optimizer_updates"] and report["macro_f1"] > best:
            best, stale = report["macro_f1"], 0
            torch.save(model.state_dict(), args.output / "weights.pt")
            metadata["validation"] = report
            (args.output / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            stale += 1
        if report["optimizer_updates"]:
            scheduler.step()
        # 每轮都写逐轮指标和折线图，权重文件对应最佳轮次。连续未刷新最佳成绩达到 patience 时结束。
        (args.output / "training.json").write_text(json.dumps(history, indent=2), encoding="utf-8")
        save_training_curves(history, args.output / "training-curves.png")
        if stale >= args.patience:
            break
    # 整次运行没更新权重时给出错误，避免让一次空跑被当作训练结果。
    if not updates:
        raise RuntimeError("No optimizer updates were applied. Retry with --precision fp32.")
    return metadata


# 改超参数先看这里的默认值。数据清单由预处理生成，网络或增强方案改动则从 model.py 入手。
def parser():
    result = argparse.ArgumentParser(description="Train a crop classifier from a grouped manifest")
    result.add_argument("--data-root", type=Path, required=True)
    result.add_argument("--manifest", type=Path, required=True)
    result.add_argument("--labels", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--architecture", choices=sorted(ARCHITECTURES), default="efficientnet_b0")
    result.add_argument("--epochs", type=int, default=30)
    result.add_argument("--batch-size", type=int, default=8)
    result.add_argument("--input-size", type=int, default=224)
    result.add_argument("--lr", type=float, default=3e-4)
    result.add_argument("--freeze-epochs", type=int, default=2)
    result.add_argument("--patience", type=int, default=5)
    result.add_argument("--seed", type=int, default=42)
    result.add_argument("--device", default="auto")
    result.add_argument(
        "--precision", choices=("auto", "fp32", "amp"), default="auto",
        help="Auto uses FP32 for MobileNetV4 and CPU, AMP for other CUDA models",
    )
    result.add_argument('--workers',type=int,default=2)
    result.add_argument("--no-pretrained", action="store_true")
    result.add_argument("--max-batches", type=int, default=0, help="Limit training batches only, keeping full validation")
    result.add_argument("--development-only", action="store_true")
    return result


if __name__ == "__main__":
    args = parser().parse_args()
    # 进入训练前检查基本输入范围。训练批量至少为 2，模型输入边长至少为 64 像素。
    if args.epochs < 1 or args.batch_size < 2 or args.input_size < 64:
        raise SystemExit("epochs >= 1, batch-size >= 2 and input-size >= 64 are required")
    train(args)
