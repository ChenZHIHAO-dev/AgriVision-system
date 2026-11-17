import asyncio
from dataclasses import replace
from io import BytesIO
import json
from pathlib import Path
import zipfile

import httpx
from fastapi.testclient import TestClient
import pytest

from app.attachments import extract_document
from app.chat import Chat
from app.config import Settings
from app.knowledge import Knowledge
from app.main import create_app

ROOT=Path(__file__).resolve().parents[1]
OWNER={'X-Client-ID':'document-test-owner'}
OTHER={'X-Client-ID':'another-test-owner'}


def test_local_reply_does_not_repeat_a_known_growth_stage(tmp_path):
    settings=Settings(root=ROOT,runtime=tmp_path,models=tmp_path)
    case={'crop':'wheat','stage':'拔节孕穗期','status':'awaiting_image','is_demo':False,'note':'','location':'南阳','disease_id':None}
    result=asyncio.run(Chat(settings,Knowledge(ROOT)).answer(case,'叶片疑似条锈病，先观察什么？',[]))
    assert result['provider']=='knowledge'
    assert '哪个生育期' not in result['text']


def test_quoted_mock_secret_loads_only_in_runtime_and_repr_hides_it(tmp_path):
    mock=tmp_path/'mock-secret.env'
    mock.write_text('DEEPSEEK_API_KEY="sk-only-a-fake-test-value"\n',encoding='utf-8')
    settings=Settings(root=ROOT,runtime=tmp_path,models=tmp_path,secret_file=mock)
    assert settings.get_deepseek_key()=='sk-only-a-fake-test-value'
    assert 'sk-only' not in repr(replace(settings,deepseek_key='sk-only-a-fake-test-value'))


@pytest.mark.parametrize('model,thinking',[('deepseek-flash',False),('deepseek-v4-pro',True)])
def test_provider_receives_text_context_and_mode_without_any_image(model,thinking,tmp_path,monkeypatch):
    seen={}
    async def respond(self,url,**kwargs):
        seen.update(kwargs)
        return httpx.Response(200,json={'choices':[{'message':{'content':'先记录症状出现时间，观察叶片两面和田间分布。'}}]},request=httpx.Request('POST',url))
    monkeypatch.setattr(httpx.AsyncClient,'post',respond)
    settings=Settings(root=ROOT,runtime=tmp_path,models=tmp_path,deepseek_key='fake-test-credential')
    case={'crop':'wheat','location':'南阳','stage':'拔节孕穗期','note':'零星发生','status':'identified','is_demo':False,'title':'疑似小麦条锈病','disease_id':'wheat_stripe_rust','model_version':'test-cnn','images':[{'url':'data:image/jpeg;base64,NEVER_FORWARD'}],'documents':[{'id':'doc','name':'农事记录.txt','text':'田间发现零星黄斑，前日有降雨。'}]}
    result=asyncio.run(Chat(settings,Knowledge(ROOT)).answer(case,'需要补充什么信息？',[],model,thinking))
    assert result['provider']=='deepseek' and result['model']==model and result['thinking']==thinking
    assert seen['json']['thinking']['type']==('enabled' if thinking else 'disabled')
    assert seen['json']['model']==model
    payload=json.dumps(seen['json'],ensure_ascii=False)
    assert 'test-cnn' in payload and '农事记录.txt' in payload
    assert 'data:image' not in payload and 'NEVER_FORWARD' not in payload
    assert 'fake-test-credential' not in payload and 'fake-test-credential' not in json.dumps(result)


def test_provider_cannot_echo_credential_to_client(tmp_path,monkeypatch):
    async def respond(self,url,**kwargs):
        return httpx.Response(200,json={'choices':[{'message':{'content':'fake-secret-do-not-return'}}]},request=httpx.Request('POST',url))
    monkeypatch.setattr(httpx.AsyncClient,'post',respond)
    settings=Settings(root=ROOT,runtime=tmp_path,models=tmp_path,deepseek_key='fake-secret-do-not-return')
    case={'crop':'wheat','location':'南阳','stage':'苗期','note':'','status':'awaiting_image','is_demo':False,'title':'咨询','disease_id':None}
    result=asyncio.run(Chat(settings,Knowledge(ROOT)).answer(case,'需要拍哪些照片？',[]))
    assert result['provider']=='knowledge' and result['notice_code']=='unverified_response'
    assert 'fake-secret-do-not-return' not in json.dumps(result)


def test_text_consultation_collects_context_with_choice_cards(tmp_path):
    settings=Settings(root=ROOT,runtime=tmp_path/'runtime',models=tmp_path/'models')
    with TestClient(create_app(settings)) as client:
        case=client.post('/api/consultations',headers=OWNER,json={}).json()
        assert case['crop'] is None and case['images']==[]
        path=f'/api/cases/{case["id"]}'
        first=client.post(path+'/messages',headers=OWNER,json={'text':'叶片上有黄斑，应该怎么观察？'}).json()
        assert first['provider']=='clarification' and first['follow_up']['field']=='crop'
        assert client.post(path+'/context',headers=OWNER,json={'crop':'wheat'}).json()['crop_name']=='小麦'
        second=client.post(path+'/messages',headers=OWNER,json={'text':'是小麦。'}).json()
        assert second['follow_up']['field']=='stage'
        client.post(path+'/context',headers=OWNER,json={'stage':'拔节孕穗期'})
        final=client.post(path+'/messages',headers=OWNER,json={'text':'接着说说检查方法。'}).json()
        assert 'follow_up' not in final
        assert client.post(path+'/messages',headers=OWNER,json={'text':'问题','model':'not-allowed'}).status_code==422


def test_document_ownership_extraction_and_removal(tmp_path):
    settings=Settings(root=ROOT,runtime=tmp_path/'runtime',models=tmp_path/'models')
    with TestClient(create_app(settings)) as client:
        case=client.post('/api/consultations',headers=OWNER,json={'crop':'wheat','stage':'苗期'}).json()
        path=f'/api/cases/{case["id"]}'
        result=client.post(path+'/attachments',headers=OWNER,data={'filename':'田间记录.txt'},files={'file':('blob','小麦田间记录：叶片零星黄斑，昨天有降雨。'.encode('utf-8'),'text/plain')})
        assert result.status_code==201
        document=result.json()['documents'][0]
        assert document['characters']>0 and 'text' not in document
        answer=client.post(path+'/messages',headers=OWNER,json={'text':'请根据资料说明','attachment_ids':[document['id']]}).json()
        assert '田间记录.txt' in answer['text']
        assert client.post(path+'/messages',headers=OWNER,json={'text':'问题','attachment_ids':['foreign-id']}).status_code==422
        assert client.delete(path+'/attachments/'+document['id'],headers=OTHER).status_code==404
        assert client.delete(path+'/attachments/'+document['id'],headers=OWNER).status_code==204
        assert client.get(path,headers=OWNER).json()['documents']==[]


def test_document_parser_handles_docx_and_rejects_secrets_or_empty_pdf():
    stream=BytesIO()
    with zipfile.ZipFile(stream,'w') as archive:
        archive.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>田间</w:t></w:r><w:r><w:t>观察记录</w:t></w:r></w:p><w:p><w:r><w:t>小麦苗期</w:t></w:r></w:p></w:body></w:document>')
    assert extract_document('记录.docx',stream.getvalue())['text']=='田间观察记录\n小麦苗期'
    with pytest.raises(ValueError,match='密钥'):
        extract_document('不要上传.txt',b'DEEPSEEK_API_KEY="sk-only-a-fake-test-value"')
    from pypdf import PdfWriter
    output=BytesIO();writer=PdfWriter();writer.add_blank_page(width=100,height=100);writer.write(output)
    with pytest.raises(ValueError,match='OCR'):
        extract_document('scan.pdf',output.getvalue())
