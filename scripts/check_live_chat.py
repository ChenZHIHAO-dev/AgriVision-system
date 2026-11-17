"""Exercise the running application. Does not open any credential file."""
import json
import time
import uuid
from pathlib import Path
import httpx


def main():
    root=Path(__file__).resolve().parents[1]
    headers={'X-Client-ID':'live-check-'+uuid.uuid4().hex[:16]}
    reports=[]
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=180,headers=headers) as client:
        response=client.post('/api/consultations',json={'crop':'wheat','stage':'拔节孕穗期','location':'河南省南阳市'})
        response.raise_for_status();case_id=response.json()['id']
        for model,thinking in [('deepseek-flash',False),('deepseek-v4-pro',False),('deepseek-flash',True)]:
            started=time.perf_counter()
            response=client.post(f'/api/cases/{case_id}/messages',json={'text':'小麦拔节孕穗期田间巡查时，先记录哪几项信息？请简短说明。','model':model,'thinking':thinking})
            response.raise_for_status();result=response.json()
            report={'model':model,'requested_thinking':thinking,'provider':result.get('provider'),'actual_thinking':result.get('thinking'),'answer_characters':len(result.get('text','')),'notice_code':result.get('notice_code'),'seconds':round(time.perf_counter()-started,2)}
            reports.append(report);print(json.dumps(report,ensure_ascii=False),flush=True)
    output=root/'.cache/live-chat-check.json';output.write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
    if any(report['provider']!='deepseek' for report in reports): raise SystemExit('At least one provider check used fallback; inspect sanitized notice_code')


if __name__=='__main__':main()
