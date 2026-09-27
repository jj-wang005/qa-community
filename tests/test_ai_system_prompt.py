from app.routers.ai import _system_prompt


def test_system_prompt_limits_knowledge_tools_to_technical_domain():
    prompt = _system_prompt()
    assert "社区知识库只覆盖软件开发、AI、后端" in prompt
    assert "非社区技术问题，禁止调用 search_master、search_live_questions 或 get_answers" in prompt
    assert "不得先说资料不足再凭模型常识给出具体建议" in prompt


def test_system_prompt_restricts_get_answers_to_explicit_answer_requests():
    prompt = _system_prompt()
    assert "只有用户明确要求查看某个社区问题下的具体回答" in prompt
    assert "不得为了补充内容、获取更详细方案或弥补检索不足而自动调用它" in prompt


def test_system_prompt_does_not_escalate_normal_questions_to_live_search():
    prompt = _system_prompt()
    assert "普通『是什么、为什么、怎么做』技术问答只调用 search_master" in prompt
    assert "不得自动追加 search_live_questions" in prompt


def test_system_prompt_requires_concise_evidence_bound_answers():
    prompt = _system_prompt()
    assert "默认直接、简洁地回答" in prompt
    assert "不得补充资料未支持的通用方案" in prompt
    assert "资料只支持一种方案时，不要自行扩写成多种方案" in prompt


def test_system_prompt_restricts_dedicated_tools_to_explicit_intent():
    prompt = _system_prompt()
    assert "get_weather、get_time、get_location 分别只能在用户" in prompt
    assert "明确询问天气、时间日期、当前位置时调用" in prompt
