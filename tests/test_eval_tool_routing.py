from evals.run_tool_routing import score_tool_routing


def test_in_domain_requires_master_search():
    passed = score_tool_routing({"id": "in_01", "reference_qids": [1], "called_tools": ["search_master"]})
    failed = score_tool_routing({"id": "in_01", "reference_qids": [1], "called_tools": []})
    assert passed["routing_correct"] == 1.0
    assert failed["missing_tools"] == ["search_master"]


def test_out_of_domain_forbids_knowledge_base_tools():
    result = score_tool_routing({"id": "out_02", "reference_qids": [], "called_tools": ["search_master"]})
    assert result["routing_correct"] == 0.0
    assert result["unexpected_tools"] == ["search_master"]


def test_weather_case_requires_weather_tool_without_knowledge_search():
    passed = score_tool_routing({"id": "out_01", "reference_qids": [], "called_tools": ["get_weather"]})
    failed = score_tool_routing({"id": "out_01", "reference_qids": [], "called_tools": []})
    assert passed["routing_correct"] == 1.0
    assert failed["missing_tools"] == ["get_weather"]


def test_out_of_domain_rejects_unhelpful_non_knowledge_tool():
    result = score_tool_routing({"id": "out_03", "reference_qids": [], "called_tools": ["get_time"]})
    assert result["routing_correct"] == 0.0
    assert result["unexpected_tools"] == ["get_time"]


def test_get_answers_requires_retrieved_qid_and_correct_order():
    valid = score_tool_routing({
        "id": "answers_01",
        "reference_qids": [20029],
        "required_tools": ["search_master", "get_answers"],
        "allowed_tools": ["search_master", "get_answers"],
        "retrieved_context_ids": ["20029"],
        "tool_calls": [
            {"name": "search_master", "args": {"query": "缓存穿透"}},
            {"name": "get_answers", "args": {"question_id": 20029}},
        ],
    })
    invalid = score_tool_routing({
        "id": "answers_01",
        "reference_qids": [20029],
        "required_tools": ["search_master", "get_answers"],
        "allowed_tools": ["search_master", "get_answers"],
        "retrieved_context_ids": ["20029"],
        "tool_calls": [
            {"name": "get_answers", "args": {"question_id": 99999}},
            {"name": "search_master", "args": {"query": "缓存穿透"}},
        ],
    })
    assert valid["routing_correct"] == 1.0
    assert invalid["routing_correct"] == 0.0
    assert len(invalid["parameter_errors"]) == 1


def test_get_answers_accepts_qid_explicitly_supplied_by_user():
    result = score_tool_routing({
        "id": "answers_02",
        "user_input": "请查看 qid=20029 下的回答",
        "reference_qids": [20029],
        "required_tools": ["get_answers"],
        "allowed_tools": ["get_answers"],
        "tool_calls": [
            {"name": "get_answers", "args": {"question_id": 20029}},
        ],
    })
    assert result["routing_correct"] == 1.0


def test_duplicate_tool_calls_are_rejected():
    result = score_tool_routing({
        "id": "in_01",
        "reference_qids": [1],
        "called_tools": ["search_master", "search_master"],
    })
    assert result["routing_correct"] == 0.0
    assert result["duplicate_tool_calls"] == ['search_master:{}']


def test_multiple_get_answers_calls_with_distinct_qids_are_allowed():
    result = score_tool_routing({
        "id": "answers_01",
        "reference_qids": [1, 2],
        "required_tools": ["search_master", "get_answers"],
        "allowed_tools": ["search_master", "get_answers"],
        "retrieved_context_ids": ["1", "2"],
        "tool_calls": [
            {"name": "search_master", "args": {"query": "缓存"}},
            {"name": "get_answers", "args": {"question_id": 1}},
            {"name": "get_answers", "args": {"question_id": 2}},
        ],
    })
    assert result["routing_correct"] == 1.0
    assert result["duplicate_tool_calls"] == []
