import re

from .knowledge import CROP_NAMES, query_crop_scope

STAGES = {
    'wheat':['苗期','返青起身期','拔节孕穗期','抽穗扬花期','灌浆成熟期'],
    'maize':['苗期','拔节期','大喇叭口期','抽雄吐丝期','灌浆成熟期'],
    'peanut':['苗期','开花下针期','结荚期','饱果成熟期'],
}


def fill_explicit_context(case, text):
    if not case.get('crop'):
        # 与检索共用作物别名，避免用户回复“麦子 / 苞谷”后仍被重复追问。
        scope = query_crop_scope(text)
        if scope and len(scope) == 1 and next(iter(scope)) in CROP_NAMES:
            crop = next(iter(scope))
            case['crop'] = crop
            case['crop_name'] = CROP_NAMES[crop]
            if not case.get('images'): case['title'] = case['crop_name']+'种植问答'
    if case.get('crop') and case.get('stage') in ('','不清楚','暂不确定'):
        for stage in STAGES[case['crop']]:
            if stage in text:
                case['stage'] = stage
                break


GENERAL_QUESTION = re.compile(
    r"^\s*(?:请问[,，：:\s]*)?什么是.{1,30}[?？。！!]*$|"
    r"^\s*.{1,30}(?:是什么|是什么意思|有什么作用|是做什么的|有何区别|有什么区别)[?？。！!]*$|"
    r"^\s*(?:请问[,，：:\s]*)?(?:怎么(?:看|读|核对)|如何(?:看|读|核对))(?:农药|产品)?标签[?？。！!]*$|"
    r"^\s*(?:怎么|如何)(?:拍清楚症状|拍摄症状照片)|"
    r"^\s*需要拍哪些照片[?？。！!]*$"
)
FIELD_DECISION = re.compile(
    r"我家|我这|我种|这块田|这株|这张|这次|现在|怎么治|如何治|用量|剂量|多少|混配|兑水|喷什么|用什么药"
)


def is_general_question(text):
    return bool(GENERAL_QUESTION.search(text) and not FIELD_DECISION.search(text))
