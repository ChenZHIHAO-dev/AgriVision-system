# 用验证集拟合温度和拒识条件。校准会更新模型包中的参数，网络权重仍来自训练保存的最佳轮次。
"""Select temperature and rejection gates using validation images only."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

from .inference import Predictor, rejection_indices
from .train import Images, read_manifest


def calibrate(bundle, data_root, manifest, device='auto'):
    torch.set_num_threads(4)
    predictor=Predictor(bundle,device)
    metadata=predictor.metadata
    # 核对清单哈希，确保来自这次训练。取 val 划分，用评估变换读图。
    digest=hashlib.sha256(manifest.read_bytes()).hexdigest()
    if metadata['manifest_sha256']!=digest: raise ValueError('Calibration manifest differs from training')
    rows=[row for row in read_manifest(manifest) if row['split']=='val']
    loader=DataLoader(Images(data_root,rows,metadata['labels'],metadata['input_size'],resize=metadata.get('resize','stretch')),batch_size=24)
    # 将所有验证样本的分类 logits 与真实标签收集起来，接下来多次试温度也能复用这份前向结果。
    logits,targets=[],[]
    with torch.inference_mode():
        for images,labels in loader:
            logits.append(predictor.model(images.to(predictor.device)).cpu()); targets.append(labels)
    logits=torch.cat(logits); targets=torch.cat(targets)
    # 在 0.5 到 3 之间试 51 个温度。对 logits 先除以温度再计算交叉熵，选验证损失最低的温度。
    candidates=np.linspace(.5,3,51)
    losses=[float(torch.nn.functional.cross_entropy(logits/float(temp),targets)) for temp in candidates]
    temperature=float(candidates[int(np.argmin(losses))])
    probabilities=(logits/temperature).softmax(1)
    # 保留最高分、最高的两个分数之差和最高分对应的类别，用来判断这个候选是否足够明确。
    values,indices=probabilities.topk(2,dim=1)
    top=values[:,0].numpy();margin=(values[:,0]-values[:,1]).numpy()
    predicted=indices[:,0].numpy(); truth=targets.numpy()
    # 预测落在保留类别时排除在明确结果之外。不同识别任务的保留类别统一由 inference.py 定义。
    known = ~np.isin(predicted, rejection_indices(metadata))
    # 遍历最高分下限和分差下限。要求验证集至少 30 张被接受，并且接受的样本至少有 98% 分类正确。
    choices=[]
    for threshold in (.6,.65,.7,.75,.8,.85,.9,.95,.98):
        for gap in (.05,.1,.12,.15,.2,.25):
            accepted = (top >= threshold) & (margin >= gap) & known
            count=int(accepted.sum())
            accuracy=float((predicted[accepted]==truth[accepted]).mean()) if count else 0
            if count>=30 and accuracy>=.98: choices.append((count,accuracy,threshold,gap))
    # 合格规则优先保留更多样本。同样覆盖数再比正确率和门限。没有合格组合时使用预设的保守门限。
    chosen=max(choices,key=lambda item:(item[0],item[1],item[2],item[3])) if choices else (0,0,.98,.25)
    metadata.update({'temperature':temperature,'threshold':chosen[2],'margin':chosen[3]})
    report={'split':'val','images':len(rows),'manifest_sha256':digest,'temperature':temperature,'nll_before':float(torch.nn.functional.cross_entropy(logits,targets)),'nll_after':min(losses),'threshold':chosen[2],'margin':chosen[3],'accepted_supported':chosen[0],'accepted_accuracy':chosen[1],'coverage':chosen[0]/len(rows),'selection_rule':'maximum validation coverage at >=98% accepted accuracy, at least 30 accepted; other class always rejected'}
    # metadata.json 供后续推理加载。calibration.json 便于对照校准前后的损失、覆盖率和阈值。
    metadata['calibration']=report
    (bundle/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    (bundle/'calibration.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--data-root',type=Path,required=True);parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--device',default='auto')
    args=parser.parse_args();print(json.dumps(calibrate(args.bundle,args.data_root,args.manifest,args.device),indent=2))
