"""Verify the running image/document -> text-only conversation pipeline."""
import csv
import json
from pathlib import Path
import time
import uuid

import httpx


def main():
    root=Path(__file__).resolve().parents[1]
    reports=[]
    with (root/'data/wheat-v1/manifest.csv').open(encoding='utf-8') as stream: rows=list(csv.DictReader(stream))
    headers={'X-Client-ID':'pipeline-check-'+uuid.uuid4().hex[:16]}
    with httpx.Client(base_url='http://127.0.0.1:8000',headers=headers,timeout=180) as client:
        meta=client.get('/api/meta').json()
        print(json.dumps({'wheat_model':next(model for model in meta['models'] if model['crop']=='wheat'),'deepseek_configured':meta['deepseek_configured']},ensure_ascii=False),flush=True)
        for label in dict.fromkeys(row['label'] for row in rows):
            row=next(row for row in rows if row['label']==label and row['split']=='test')
            path=root/'data/wheat-v1/images'/row['path']
            started=time.perf_counter()
            with path.open('rb') as file:
                response=client.post('/api/cases',data={'crop':'wheat','stage':'拔节孕穗期'},files={'file':('leaf.jpg',file,'image/jpeg')})
            response.raise_for_status();case=response.json()
            report={'check':'image-upload','reference_label':label,'status':case['status'],'top':case['candidates'][0]['id'] if case['candidates'] else None,'experimental':case.get('experimental'),'model_version':case.get('model_version'),'seconds':round(time.perf_counter()-started,3)}
            reports.append(report);print(json.dumps(report,ensure_ascii=False),flush=True)
            if case['status']=='model_error':raise SystemExit('Actual uploaded image failed in the classifier')
        response=client.post('/api/consultations',json={'crop':'wheat','stage':'苗期'});response.raise_for_status();case_id=response.json()['id']
        content='示例田间观察：小麦苗期，叶片零星黄斑，昨天有降雨。尚未记录发生比例、叶背情况与近期施肥信息。'.encode('utf-8')
        response=client.post(f'/api/cases/{case_id}/attachments',files={'file':('field-notes.txt',content,'text/plain')});response.raise_for_status()
        attachment=response.json()['documents'][0]
        response=client.post(f'/api/cases/{case_id}/messages',json={'text':'请根据上传的田间记录，指出还需要补充的两项信息。','model':'deepseek-v4-pro','thinking':True,'attachment_ids':[attachment['id']]});response.raise_for_status();answer=response.json()
        report={'check':'document-conversation','model':'deepseek-v4-pro','thinking':answer.get('thinking'),'provider':answer['provider'],'characters':len(answer['text']),'notice_code':answer.get('notice_code')}
        reports.append(report);print(json.dumps(report),flush=True)
        if answer['provider']!='deepseek':raise SystemExit('Document conversation used fallback')
    (root/'.cache/backend-pipeline-check.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
