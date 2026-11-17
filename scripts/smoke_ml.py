"""Exercise the training pipeline with synthetic images, never disease evidence."""
from pathlib import Path
import json
import sys
import argparse
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


if __name__ == '__main__':
    from ml.agrivision_ml.prepare import prepare
    from ml.agrivision_ml.train import parser, train
    from ml.agrivision_ml.inference import Predictor
    from ml.agrivision_ml.model import build_model
    import torch
    torch.set_num_threads(4)
    result = ROOT / '.cache/ml-smoke'
    labels_path = ROOT / 'configs/labels/wheat.json'
    config = json.loads(labels_path.read_text(encoding='utf-8'))
    for category, label in enumerate(config['labels']):
        folder = result / 'raw' / label
        folder.mkdir(parents=True, exist_ok=True)
        for index in range(8):
            array = np.random.default_rng(category * 100 + index).integers(20,235,(180,180,3),dtype=np.uint8)
            Image.fromarray(array).save(folder / f'{index}.png')
    manifest = result / 'manifest.csv'
    prepare(result/'raw', labels_path, manifest)
    args = parser().parse_args(['--data-root',str(result/'raw'),'--manifest',str(manifest),'--labels',str(labels_path),'--output',str(result/'model'),'--architecture','mobilenet_v3_small','--epochs','1','--batch-size','4','--input-size','96','--no-pretrained','--max-batches','1','--development-only'])
    train(args)
    predictor = Predictor(result/'model')
    sample = next((result/'raw').rglob('*.png'))
    candidates = predictor.predict(sample)
    assert len(candidates) == 3
    assert predictor.metadata['validated'] is False and predictor.metadata['development_only'] is True
    with torch.inference_mode():
        baseline=build_model('efficientnet_b0',len(config['labels'])).eval()
        assert baseline(torch.rand(1,3,96,96)).shape == (1,len(config['labels']))
    report = {'pipeline':'passed','architectures_checked':['efficientnet_b0','mobilenet_v3_small'],'torch':torch.__version__,'cuda_available':torch.cuda.is_available(),'device':str(predictor.device),'gpu':torch.cuda.get_device_name() if torch.cuda.is_available() else None,'synthetic_images':32,'disease_accuracy':'not evaluated'}
    (result/'smoke-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
