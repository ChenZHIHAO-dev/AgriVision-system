"""Extract local document text. Images are handled only by the vision pipeline."""
from io import BytesIO
from pathlib import Path
import re
import zipfile
from xml.etree import ElementTree

from .knowledge import tokens

ALLOWED = {'.txt', '.md', '.pdf', '.docx'}
KEY_PATTERN = re.compile(r'(?i)DEEPSEEK_API_KEY\s*=\s*\S+|\bsk-[a-zA-Z0-9_-]{16,}')


def extract_document(filename, content):
    name = Path(filename.replace('\\', '/')).name[:160]
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED:
        raise ValueError('资料文件支持 TXT、Markdown、可复制文字的 PDF 和 DOCX')
    if len(content) > 8 * 1024 * 1024:
        raise ValueError('资料文件不能超过 8MB')
    if suffix in {'.txt', '.md'}:
        text = None
        for encoding in ('utf-8-sig', 'gb18030'):
            try: text = content.decode(encoding); break
            except UnicodeError: continue
        if text is None or '\x00' in text:
            raise ValueError('文件不是可读取的文本，请保存为 UTF-8 格式后上传')
    elif suffix == '.pdf':
        from pypdf import PdfReader
        try:
            reader = PdfReader(BytesIO(content), strict=True)
            if reader.is_encrypted:
                raise ValueError('请先解密 PDF 后再上传')
            if len(reader.pages) > 80:
                raise ValueError('请上传不超过 80 页的资料，或先拆分文件')
            text = '\n'.join(page.extract_text() or '' for page in reader.pages)
        except ValueError: raise
        except Exception as exc:
            raise ValueError('PDF 无法解析，请换用可复制文字的 PDF 或 TXT') from exc
    else:
        try:
            with zipfile.ZipFile(BytesIO(content)) as archive:
                info = archive.getinfo('word/document.xml')
                if info.file_size > 12_000_000 or sum(entry.file_size for entry in archive.infolist()) > 40_000_000:
                    raise ValueError('DOCX 解压后过大，请拆分文件')
                xml = archive.read(info)
                if b'<!DOCTYPE' in xml or b'<!ENTITY' in xml:
                    raise ValueError('不支持包含外部实体的文档')
                root = ElementTree.fromstring(xml)
                namespace = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                text = '\n'.join(
                    ''.join(node.text or '' for node in paragraph.findall('.//w:t', namespace))
                    for paragraph in root.findall('.//w:p', namespace)
                )
        except ValueError: raise
        except Exception as exc:
            raise ValueError('DOCX 无法解析，请换用标准 DOCX 或 TXT') from exc
    text = text.strip()
    if not text:
        raise ValueError('未提取到文字。扫描图片 PDF 暂不支持 OCR，请上传含可复制文字的资料')
    if KEY_PATTERN.search(text):
        raise ValueError('文件疑似包含访问密钥，请移除密钥后再上传资料')
    return {'name': name, 'text': text[:30000], 'characters': len(text), 'truncated': len(text)>30000, 'size':len(content), 'kind':'document', 'extraction':'ready'}


def document_context(documents, query, limit=4):
    query_tokens = tokens(query)
    chunks = []
    for document in documents[-6:]:
        text = document.get('text', '')
        for start in range(0, len(text), 800):
            chunk = text[start:start+1000]
            score = len(query_tokens & tokens(chunk))
            chunks.append((score, {'name':document['name'], 'text':chunk}))
    return [chunk for _, chunk in sorted(chunks, key=lambda item: item[0], reverse=True)[:limit]]
