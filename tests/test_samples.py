"""Run the 10 public sample cases through the analyzer and assert key fields."""
import json
from pathlib import Path

import pytest

from app.analyzer import analyze
from app.schemas import AnalyzeRequest

CASES = json.loads((Path(__file__).parent.parent / "data" / "sample_cases.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_sample_case(case):
    result = analyze(AnalyzeRequest(**case["input"]))
    exp = case["expected"]
    assert result.relevant_transaction_id == exp["relevant_transaction_id"]
    assert result.evidence_verdict.value == exp["evidence_verdict"]
    assert result.case_type.value == exp["case_type"]
    assert result.department.value == exp["department"]
    assert result.severity.value == exp["severity"]
    assert result.human_review_required == exp["human_review_required"]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_reply_is_safe(case):
    result = analyze(AnalyzeRequest(**case["input"]))
    reply = result.customer_reply.lower()
    # Never request credentials.
    assert "share your otp" not in reply and "send your pin" not in reply
    assert "enter your otp" not in reply and "provide your password" not in reply
    # Never promise an unauthorized refund.
    assert "we will refund" not in reply and "we'll refund" not in reply
    assert result.ticket_id == case["input"]["ticket_id"]
