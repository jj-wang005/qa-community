import math

from evals.run_custom_judge import _citation_score, _refusal_score


def test_citation_accepts_multiple_real_sources_and_terminal_punctuation_variation():
    row = {
        "reference_qids": [1],
        "response": "结论（来源：第一篇；第二篇）以及补充（来源：第二篇）",
        "retrieved_contexts": [
            "[资料1] 来源：第一篇？ (qid:1)\n正文",
            "[资料2] 来源：第二篇 (qid:2)\n正文",
        ],
    }
    assert _citation_score(row) == 1.0


def test_citation_accepts_chinese_list_separator_between_sources():
    row = {
        "reference_qids": [1],
        "response": "结论（来源：第一篇、第二篇）",
        "retrieved_contexts": [
            "[资料1] 来源：第一篇 (qid:1)\n正文",
            "[资料2] 来源：第二篇 (qid:2)\n正文",
        ],
    }
    assert _citation_score(row) == 1.0


def test_citation_does_not_split_comma_inside_title():
    row = {
        "reference_qids": [1],
        "response": "（来源：缓存穿透是什么，布隆过滤器怎么防？）",
        "retrieved_contexts": [
            "[资料1] 来源：缓存穿透是什么，布隆过滤器怎么防？ (qid:1)\n正文"
        ],
    }
    assert _citation_score(row) == 1.0


def test_citation_rejects_unknown_source():
    row = {
        "reference_qids": [1],
        "response": "结论（来源：不存在的资料）",
        "retrieved_contexts": ["[资料1] 来源：第一篇 (qid:1)\n正文"],
    }
    assert _citation_score(row) == 0.0


def test_refusal_accepts_capability_boundary_without_specific_advice():
    row = {
        "reference_qids": [],
        "called_tools": [],
        "response": "我目前不支持医疗健康建议，建议咨询专业医生。",
    }
    assert _refusal_score(row) == 1.0


def test_refusal_rejects_unsupported_advice_after_disclaimer():
    row = {
        "reference_qids": [],
        "called_tools": [],
        "response": "知识库没有相关资料。不过，我可以基于一般常识给出建议：每天少吃盐。",
    }
    assert _refusal_score(row) == 0.0


def test_refusal_accepts_explicit_scope_boundary_without_tool():
    row = {
        "reference_qids": [],
        "called_tools": [],
        "response": "游戏推荐不属于我所服务的技术社区范围，我当前没有相关工具查询。",
    }
    assert _refusal_score(row) == 1.0


def test_refusal_is_not_applicable_when_dedicated_tool_answered():
    row = {
        "reference_qids": [],
        "called_tools": ["get_weather"],
        "response": "今天北京19摄氏度。",
    }
    assert math.isnan(_refusal_score(row))
