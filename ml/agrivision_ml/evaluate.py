import argparse
import hashlib
import json
import torch
from pathlib import Path

from torch.utils.data import DataLoader
from .inference import Predictor
from .train import Images, read_manifest, evaluate_loader


def evaluate(args):
    torch.set_num_threads(4)
    predictor = Predictor(args.bundle, args.device)
    metadata = predictor.metadata
    rows = [r for r in read_manifest(args.manifest) if r["split"] == args.split]
    if not rows:
        raise ValueError("No images in requested split")
    loader = DataLoader(Images(args.data_root, rows, metadata["labels"], metadata["input_size"]), batch_size=8)
    report = evaluate_loader(predictor.model, loader, predictor.device, len(metadata["labels"]))
    report.update({"split": args.split, "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(), "model_version": metadata["version"], "field_verified": args.field_verified})
    total,accepted,correct=0,0,0
    with torch.inference_mode():
        for images,labels in loader:
            probabilities=(predictor.model(images.to(predictor.device))/float(metadata.get('temperature',1))).softmax(1).cpu()
            values,indices=probabilities.topk(2,dim=1)
            keep=(values[:,0]>=metadata['threshold'])&((values[:,0]-values[:,1])>=metadata['margin'])
            if 'wheat_other' in metadata['labels']: keep &= indices[:,0]!=metadata['labels'].index('wheat_other')
            total+=len(labels);accepted+=int(keep.sum());correct+=int(((indices[:,0]==labels)&keep).sum())
    report['selective']={'accepted':accepted,'total':total,'coverage':accepted/max(total,1),'accuracy':correct/max(accepted,1),'threshold':metadata['threshold'],'margin':metadata['margin']}
    path = args.bundle / f"evaluation-{getattr(args,'report_name',None) or args.split}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.activate:
        if metadata.get("development_only") or args.split != "test" or not args.field_verified:
            raise ValueError("Activation requires a real model, test split and operator-confirmed field verification")
        if min(report["counts"]) < 20 or report["macro_f1"] < .8 or min(report["recall"]) < .6:
            raise ValueError("Development release gate requires >=20 test images/class, Macro-F1 >=.8 and each recall >=.6")
        metadata["validated"] = True
        metadata["field_verified"] = True
        metadata["test_report"] = report
        (args.bundle / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    if getattr(args,'activate_experimental',False):
        if metadata.get('development_only') or args.split!='test' or report['manifest_sha256']!=metadata['manifest_sha256']:
            raise ValueError('Experimental activation requires the real held-out training-manifest test split')
        if min(report['counts'])<20 or report['macro_f1']<.8 or min(report['recall'])<.6:
            raise ValueError('Experimental gate requires >=20 test images/class, Macro-F1 >=.8, each recall >=.6')
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
    activation = parser.add_mutually_exclusive_group()
    activation.add_argument("--activate", action="store_true")
    activation.add_argument('--activate-experimental',action='store_true',help='Enable local internal-data testing only; does not claim field validation')
    parser.add_argument('--report-name',choices=['external-jic'],default=None)
    parser.add_argument("--field-verified", action="store_true")
    print(json.dumps(evaluate(parser.parse_args()), indent=2))
