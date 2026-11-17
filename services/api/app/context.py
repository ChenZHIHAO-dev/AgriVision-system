import re

from .knowledge import CROP_NAMES

STAGES = {
    'wheat':['苗期','返青起身期','拔节孕穗期','抽穗扬花期','灌浆成熟期'],
    'maize':['苗期','拔节期','大喇叭口期','抽雄吐丝期','灌浆成熟期'],
    'peanut':['苗期','开花下针期','结荚期','饱果成熟期'],
}


def fill_explicit_context(case, text):
    if not case.get('crop'):
        matches = [crop for crop,name in CROP_NAMES.items() if name in text]
        if len(matches)==1:
            case['crop'] = matches[0]
            case['crop_name'] = CROP_NAMES[matches[0]]
            if not case.get('images'): case['title'] = case['crop_name']+'种植咨询'
    if case.get('crop') and case.get('stage') in ('','不清楚'):
        for stage in STAGES[case['crop']]:
            if stage in text:
                case['stage'] = stage
                break


def follow_up(case):
    if not case.get('crop'):
        return {'field':'crop','prompt':'这次主要咨询哪种作物？','options':[{'value':crop,'label':name} for crop,name in CROP_NAMES.items()]}
    if case.get('stage') in ('','不清楚'):
        return {'field':'stage','prompt':'目前处于哪个生育期？','options':[{'value':stage,'label':stage} for stage in STAGES[case['crop']]]+[{'value':'暂不确定','label':'先不填写'}]}
    return None
