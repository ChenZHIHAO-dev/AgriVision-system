"""番茄来源审计不能把待筛图当人工保留，也不能保留跨标签同像素图。"""
import json
from pathlib import Path

from PIL import Image

from ml.agrivision_ml.preprocessing import tomato_source as module
from ml.agrivision_ml.preprocessing.tables import read_rows, write_rows


def test_pixel_label_conflict_holds_every_copy():
    rows = [{'path':'a.jpg','label':'a','pixel_sha256':'same','review':'review'},
            {'path':'b.jpg','label':'b','pixel_sha256':'same','review':'review'},
            {'path':'c.jpg','label':'a','pixel_sha256':'other','review':'review'}]
    conflicts = module.exclude_pixel_conflicts(rows)
    assert conflicts == [{'pixel_sha256':'same','paths':['a.jpg','b.jpg']}]
    assert [row['review'] for row in rows] == ['hold','hold','review']


def test_identical_same_label_is_not_changed_to_conflict():
    rows = [{'path':f'{i}.jpg','label':'a','pixel_sha256':'same','review':'review'} for i in range(2)]
    assert module.exclude_pixel_conflicts(rows) == []
    assert all(row['review']=='review' for row in rows)


def test_review_requires_explicit_author_label_acceptance_and_keeps_manual_drop(tmp_path):
    source={'id':'pv','crop':'tomato','label_map':{'OriginalA':'a','OriginalB':'b'},
            'default_review':'review','url':'https://example.test/source','license':'CC BY-SA 3.0'}
    labels={'a':'甲','b':'乙'}
    review=tmp_path/'data/tomato/review'; review.mkdir(parents=True)
    audit=[]
    for index,label in enumerate(['OriginalA','OriginalB']):
        relative=Path('data/tomato/sources/pv/raw')/label/f'{index}.jpg'
        target=tmp_path/relative; target.parent.mkdir(parents=True,exist_ok=True)
        Image.new('RGB',(80,80),(30,80,index)).save(target)
        audit.append({'path':relative.as_posix(),'source':'pv','source_label':label,
                      'review':'review','group':'unknown' if index==0 else 'leaf-2',
                      'group_status':'unknown' if index==0 else 'author_leaf_id'})
    write_rows(review/'source-audit.csv',list(audit[0]),audit)
    selection=module.sync_review(source,labels,root=tmp_path)
    assert not selection.photos and selection.decisions['pending']==2
    selection=module.sync_review(source,labels,root=tmp_path,accept_source_labels=True)
    assert len(selection.photos)==2
    rows=read_rows(review/'disease-review.csv')
    assert all(row['review_basis']=='source_labels_internal_experiment' for row in rows)
    assert rows[0]['group']=='' and rows[1]['group']=='pv:leaf-2'
    rows[0]['decision']='drop'
    write_rows(review/'disease-review.csv',list(rows[0]),rows)
    selection=module.sync_review(source,labels,root=tmp_path,accept_source_labels=True)
    assert len(selection.photos)==1 and selection.photos[0].label=='b'
    assert read_rows(review/'disease-review.csv')[0]['decision']=='drop'


def test_catalog_contains_only_actual_ten_source_labels():
    source,labels=module.load_config()
    assert len(source['label_map'])==len(labels)==10
    assert set(source['label_map'].values())==set(labels)
    assert source['label_map']['Tomato___Spider_mites Two-spotted_spider_mite']=='tomato_spider_mites'
    assert '叶螨危害' in labels['tomato_spider_mites']
    assert 'tomato_gray_mold' not in labels
