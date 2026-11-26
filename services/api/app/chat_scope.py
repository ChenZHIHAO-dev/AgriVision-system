"""农业问答的入口分流，不读取密钥、不调用模型，也不修改会话。

判断当前问题和用户已有农业上下文；不能只靠“这句里是否重复病名”。
明确无关任务仍在付费调用前拦截，进入模型后的系统指令继续限定业务范围。
"""

import re

from .knowledge import CROP_NAMES, query_crop_scope
from .intake import context_reply
from .conversation_policy import case_followup
from .treatment_policy import MEDICATION


SCOPE_GUIDANCE = (
    "你可以问我农作物病虫害、种植管理、农资使用或农业资料。"
    "请描述作物或田间情况，也可以上传症状照片。"
)
AGRICULTURAL = re.compile(
    "|".join(re.escape(name) for name in CROP_NAMES.values())
    + r"|农业|农作物|农产品|农田|农资|农药|植保|种植|庄稼|作物|粮食|田间|农技|农机|土壤|墒情"
    r"|水稻|大豆|棉花|油菜|高粱|谷子|马铃薯|土豆|番茄|辣椒|蔬菜|果树|果园|茶树|烟草|甘蔗"
    r"|叶片|叶子|叶面|叶背|叶尖|叶斑|叶枯|根茎|根系|麦穗|整株|病株|病虫害|虫害|病害"
    r"|白粉病|条锈病|锈病|霜霉病|根腐病|赤霉病|纹枯病|蚜虫|螟虫|粘虫|草地贪夜蛾|地下害虫"
    r"|肥料|化肥|施肥|追肥|基肥|氮肥|磷肥|钾肥|有机肥|水肥|缺素|灌溉|浇水|播种|拌种|种子"
    r"|生育期|苗期|返青|拔节|孕穗|抽穗|扬花|灌浆|大喇叭口|抽雄|吐丝|下针|结荚|亩产|采收|轮作|杂草"
    r"|杀菌剂|杀虫剂|除草剂|调节剂|安全间隔期|登记证号|嘧菌酯|吡虫啉|戊唑醇|苯醚甲环唑|多菌灵|草甘膦|草铵膦"
    r"|\b(?:agricultur\w*|crop\w*|wheat|maize|corn|peanut\w*|pesticide\w*|fungicide\w*|herbicide\w*|fertili[sz]er\w*|irrigation|plant\s+disease\w*)\b",
    re.I,
)
# A prior crop choice must not turn an unrelated new task into a paid request.
UNRELATED_TASK = re.compile(
    r"写(?:一段|个|一个)?(?:代码|程序|爬虫|小说|情书)|编程|算法题|数学题|高数|线性代数|修电脑|电脑蓝屏"
    r"|股票|炒股|比特币|加密货币|基金投资|旅游攻略|酒店预订|机票|电影推荐|推荐.{0,8}电影|电视剧|明星八卦|恋爱|星座|足球|篮球"
    r"|期货|期权|现货交易|套期保值|理财|投资|贷款|信贷|融资|保费|投保|保单|承保|理赔|赔付"
    r"|(?:农业|农作物|种植业|作物|小麦|玉米|花生|水稻|粮食|买|购买|办理|申请)保险"
    r"|保险(?:公司|推荐|(?:怎么|如何)(?:买|赔|办)|在哪里买|买哪)"
    r"|\b(?:futures|options? contracts?|commodity trading|insurance|loans?|lending|finance|financial|investments?)\b"
    r"|感冒|发烧|头痛|人体|患者|皮肤病|阿莫西林|布洛芬"
    r"|(?<![a-z])(?:python|javascript|leetcode|bitcoin|cryptocurrency|football|basketball|horoscope)(?![a-z])",
    re.I,
)
BUSINESS_HELP = re.compile(
    r"拍清楚症状|拍摄症状照片|需要拍哪些照片|(?:怎么|如何)(?:看|读|核对)(?:农药|产品)?标签"
)
DOCUMENT_QUESTION = re.compile(r"资料|附件|文档|文件|这份|这篇|总结|概括|摘要|翻译|提取")
FIELD_SYMPTOM = re.compile(r"黄斑|白斑|发黄|枯萎|腐烂|倒伏|长虫|虫卵|缺水|药害|药斑")
TOPICAL_FOLLOW_UP = re.compile(
    r"^(?:(?:请|麻烦|能不能|可以|应该|那么|那|这个|这种情况|接下来|还|再|先)){0,3}"
    r"(?:怎么(?:办|处理|解决|预防|判断|使用|检查|观察)|如何(?:处理|解决|预防|判断|使用|检查|观察)"
    r"|用什么药|喷什么|怎么用药|能混用|有什么作用|有什么建议|具体(?:方法|建议)"
    r"|(?:用药|施药|喷药)前(?:需要|要)?核对(?:什么|哪些(?:信息|事项)?)"
    r"|说明排查方向|回答(?:刚才|刚刚|之前)的问题"
    r"|需要补充(?:什么|哪些)(?:信息|资料|照片)|还需要(?:什么|哪些)(?:信息|资料|照片)"
    r"|继续(?:说说|回答|说明)?|接着(?:说说|说|回答)(?:检查方法)?|详细(?:讲讲|说明|说说)"
    r"|总结(?:一下)?(?:刚才|之前)?的?(?:建议|内容)|为什么|多久|什么时候|还有呢)"
    r"(?:呢|吗|一下|啊|吧)?$"
    r"|^(?:what next|please continue|how (?:to treat it|should i treat it)|why)[?!.\s]*$",
    re.I,
)


# Exact first-party report requests carry no agriculture keyword. Only an actual
# stored photo may supply their scope; crop defaults or user-written receipts cannot.
PHOTO_REPORT_QUESTION = re.compile(
    r"^(?:这次照片的画质检查没有通过，请说明具体该怎样补拍"
    r"|请分别解释各张照片的初步线索，以及下一步怎样核对，不要把不同照片合成一种病害"
    r"|照片已上传但目前还不能可靠判断，请结合逐张处理回执说明还要观察或补充什么"
    r"|请结合这组照片的逐张识别回执，解释已有线索、未判明的部分和下一步建议"
    r"|(?:请)?(?:解释|说明)(?:刚刚|刚才|这个|这次|本次)的?(?:识别)?结果"
    r"|(?:刚刚|刚才|这次|本次)识别(?:到|出)?了?什么"
    r"|这张照片需要补拍吗)[。！？?]?$"
)


def within_agricultural_scope(case, text, history):
    """先挡明确无关任务；已有记录允许自然追问，不要求重复作物或病名。"""
    if UNRELATED_TASK.search(text):
        return False
    documents = case.get("documents", [])
    if documents and DOCUMENT_QUESTION.search(text):
        # File names and the default crop alone are not evidence of file contents.
        return any(AGRICULTURAL.search(doc.get("text", "")) for doc in documents)
    if PHOTO_REPORT_QUESTION.fullmatch(text.strip()):
        return bool(case.get("images"))
    if AGRICULTURAL.search(text) or BUSINESS_HELP.search(text) or query_crop_scope(text) is not None:
        return True
    context = (
        case.get("crop") in CROP_NAMES
        or bool(case.get("images"))
        or any(
            message.get("role") == "user"
            and AGRICULTURAL.search(message.get("text", ""))
            and not UNRELATED_TASK.search(message.get("text", ""))
            for message in history[-6:]
        )
    )
    if not context:
        return False
    compact = re.sub(r"[\s，,。！!？?：:；;]", "", text)
    return bool(
        TOPICAL_FOLLOW_UP.fullmatch(compact)
        or TOPICAL_FOLLOW_UP.fullmatch(text.strip())
        or case_followup(text)
        or FIELD_SYMPTOM.search(text)
        or MEDICATION.search(text)
        or context_reply(text)
    )
