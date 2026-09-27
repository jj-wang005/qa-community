import json

import pytest

from evals.run_answers import context_blocks, load_checkpoint


def test_context_blocks_include_first_item_inside_guardrail_wrapper():
    wrapped = (
        '<untrusted_tool_data source="search_master">'
        '[资料1] 来源：第一篇 (qid:1)\n正文一\n\n'
        '[资料2] 来源：第二篇 (qid:2)\n正文二'
        '</untrusted_tool_data>'
    )
    assert context_blocks(wrapped) == [
        '[资料1] 来源：第一篇 (qid:1)\n正文一',
        '[资料2] 来源：第二篇 (qid:2)\n正文二',
    ]


def test_non_search_evidence_is_kept_as_one_context():
    payload = '<untrusted_tool_data source="get_answers">[{"id": 1}]</untrusted_tool_data>'
    assert context_blocks(payload) == [payload]


def test_load_checkpoint_returns_completed_rows(tmp_path):
    checkpoint = tmp_path / "answers.json"
    checkpoint.write_text(
        json.dumps({"metadata": {"label_quality": "silver"}, "rows": [{"id": "in_01"}]}),
        encoding="utf-8",
    )

    metadata, rows = load_checkpoint(checkpoint, {"in_01", "in_02"})

    assert metadata == {"label_quality": "silver"}
    assert rows == [{"id": "in_01"}]


def test_load_checkpoint_rejects_unknown_case(tmp_path):
    checkpoint = tmp_path / "answers.json"
    checkpoint.write_text(
        json.dumps({"metadata": {}, "rows": [{"id": "other"}]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown case ids"):
        load_checkpoint(checkpoint, {"in_01"})
