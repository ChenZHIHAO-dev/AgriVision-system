"""Select temperature and rejection gates using validation images only."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

from .inference import Predictor
from .train import Images, read_manifest


def calibrate(bundle, data_root, manifest, device='auto'):
    torch.set_num_threads(4)
    predictor=Predictor(bundle,device)
    metadata=predictor.metadata
    digest=hashlib.sha256(manifest.read_bytes()).hexdigest()
    if metadata['manifest_sha256']!=digest: raise ValueError('Calibration manifest differs from training')
    rows=[row for row in read_manifest(manifest) if row['split']=='val']
    loader=DataLoader(Images(data_root,rows,metadata['labels'],metadata['input_size']),batch_size=24)
    logits,targets=[],[]
    with torch.inference_mode():
        for images,labels in loader:
            logits.append(predictor.model(images.to(predictor.device)).cpu()); targets.append(labels)
    logits=torch.cat(logits); targets=torch.cat(targets)
    candidates=np.linspace(.5,3,51)
    losses=[float(torch.nn.functional.cross_entropy(logits/float(temp),targets)) for temp in candidates]
    temperature=float(candidates[int(np.argmin(losses))])
    probabilities=(logits/temperature).softmax(1)
    values,indices=probabilities.topk(2,dim=1)
    top=values[:,0].numpy();margin=(values[:,0]-values[:,1]).numpy()
    predicted=indices[:,0].numpy(); truth=targets.numpy()
    other=metadata['labels'].index('wheat_other') if 'wheat_other' in metadata['labels'] else -1
    choices=[]
    for threshold in (.6,.65,.7,.75,.8,.85,.9,.95,.98):
        for gap in (.05,.1,.12,.15,.2,.25):
            accepted=(top>=threshold)&(margin>=gap)&(predicted!=other)
            count=int(accepted.sum())
            accuracy=float((predicted[accepted]==truth[accepted]).mean()) if count else 0
            if count>=30 and accuracy>=.98: choices.append((count,accuracy,threshold,gap))
    chosen=max(choices,key=lambda item:(item[0],item[1],item[2],item[3])) if choices else (0,0,.98,.25)
    metadata.update({'temperature':temperature,'threshold':chosen[2],'margin':chosen[3]})
    report={'split':'val','images':len(rows),'manifest_sha256':digest,'temperature':temperature,'nll_before':float(torch.nn.functional.cross_entropy(logits,targets)),'nll_after':min(losses),'threshold':chosen[2],'margin':chosen[3],'accepted_supported':chosen[0],'accepted_accuracy':chosen[1],'coverage':chosen[0]/len(rows),'selection_rule':'maximum validation coverage at >=98% accepted accuracy, at least 30 accepted; other class always rejected'}
    metadata['calibration']=report
    (bundle/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    (bundle/'calibration.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--data-root',type=Path,required=True);parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--device',default='auto')
    args=parser.parse_args();print(json.dumps(calibrate(args.bundle,args.data_root,args.manifest,args.device),indent=2))
