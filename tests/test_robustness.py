"""Robustness on phrasings beyond the public samples (hidden-test coverage)."""
import pytest

from app.analyzer import analyze
from app.schemas import AnalyzeRequest

PAY = [{"transaction_id": "TXN-1", "type": "payment", "amount": 500, "counterparty": "M", "status": "failed"}]
TRANSFER = [{"transaction_id": "TXN-2", "type": "transfer", "amount": 700, "counterparty": "+8801711111111", "status": "completed"}]
DUP = [
    {"transaction_id": "TXN-3", "timestamp": "2026-01-01T10:00:00Z", "type": "payment", "amount": 200, "counterparty": "B", "status": "completed"},
    {"transaction_id": "TXN-4", "timestamp": "2026-01-01T10:00:09Z", "type": "payment", "amount": 200, "counterparty": "B", "status": "completed"},
]
COMPLETED = [{"transaction_id": "TXN-5", "type": "payment", "amount": 900, "counterparty": "MERCHANT-9", "status": "completed"}]


@pytest.mark.parametrize("complaint,history,case_type,department", [
    ("payment didnt go through but money deducted", PAY, "payment_failed", "payments_ops"),
    ("I accidentally sent 700 to the wrong agent", TRANSFER, "wrong_transfer", "dispute_resolution"),
    ("I was charged again for the same 200 bill", DUP, "duplicate_payment", "payments_ops"),
    ("ekta number theke call dilo, amar OTP chaiche", [], "phishing_or_social_engineering", "fraud_risk"),
    ("I got an sms that I won a lottery prize", [], "phishing_or_social_engineering", "fraud_risk"),
])
def test_case_type_and_routing(complaint, history, case_type, department):
    o = analyze(AnalyzeRequest(ticket_id="X", complaint=complaint, transaction_history=history))
    assert o.case_type.value == case_type
    assert o.department.value == department


def test_contested_refund_routes_to_disputes():
    o = analyze(AnalyzeRequest(ticket_id="X",
        complaint="I paid 900 for a product but never received it, I want a refund",
        transaction_history=COMPLETED))
    assert o.case_type.value == "refund_request"
    assert o.department.value == "dispute_resolution"
    assert o.human_review_required is True


def test_change_of_mind_refund_stays_customer_support():
    o = analyze(AnalyzeRequest(ticket_id="X",
        complaint="I changed my mind, please refund my 500",
        transaction_history=COMPLETED))
    assert o.case_type.value == "refund_request"
    assert o.department.value == "customer_support"
    assert o.human_review_required is False
