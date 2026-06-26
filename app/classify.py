"""Classification and routing: case_type, verdict, severity, department, escalation."""
from dataclasses import dataclass
from typing import List, Optional

from app.schemas import (
    CaseType,
    Department,
    EvidenceVerdict,
    Severity,
    TransactionEntry,
)
from app.signals import Signals

HIGH_AMOUNT = 50_000

# Transaction types/statuses each case_type expects, used by the matcher.
EXPECTED_TYPES = {
    CaseType.wrong_transfer: {"transfer"},
    CaseType.payment_failed: {"payment", "transfer"},
    CaseType.duplicate_payment: {"payment"},
    CaseType.refund_request: {"payment"},
    CaseType.agent_cash_in_issue: {"cash_in"},
    CaseType.merchant_settlement_delay: {"settlement"},
}
EXPECTED_STATUS = {
    CaseType.wrong_transfer: {"completed"},
    CaseType.payment_failed: {"failed"},
    CaseType.duplicate_payment: {"completed"},
    CaseType.refund_request: {"completed"},
    CaseType.agent_cash_in_issue: {"pending", "failed"},
    CaseType.merchant_settlement_delay: {"pending"},
}

# Keyword sets (English / Bangla / Banglish).
_CRED = ["otp", "pin", "password", "card number", "cvv", "ওটিপি", "পিন", "পাসওয়ার্ড"]
_ASK = ["asked", "asking", "ask for", "share", "wants", "want my", "wanted", "give me",
        "told me", "send me your", "provide", "request my", "চাইছে", "চেয়েছে", "চায়", "শেয়ার",
        "chaiche", "chacche", "cheyeche", "chailo", "chai", "magche", "share korte"]
_PHISH = ["scam", "phishing", "fraud call", "suspicious call", "fake", "prtarona",
          "protarok", "fishing", "lottery", "you won", "winner", "cash prize", "prize money",
          "claim your", "suspicious link", "click this link", "click the link",
          "প্রতারণা", "প্রতারক", "সন্দেহজনক", "ফিশিং", "প্রতারিত", "লটারি", "পুরস্কার", "জিতেছেন"]
_DUP = ["twice", "two times", "2 times", "double", "duplicate", "double charge",
        "charged again", "charged twice", "debited twice", "deducted twice", "duibar",
        "দুইবার", "দুবার", "দুই বার", "ডাবল"]
_FAILED = ["failed", "unsuccessful", "didn't go through", "did not go through",
           "didnt go through", "did not complete", "didn't complete", "could not complete",
           "transaction failed", "payment failed", "ব্যর্থ", "ফেইল", "ফেল"]
_DEDUCT = ["deducted", "deduct", "cut from", "কাটা", "কেটে"]
_BALANCE = ["balance", "ব্যালেন্স", "ব্যালান্স"]
_CASHIN = ["cash in", "cash-in", "cashin", "cash deposit", "ক্যাশ ইন", "ক্যাশইন"]
_AGENT = ["agent", "এজেন্ট"]
_DEPOSIT = ["deposit", "cash", "জমা", "ক্যাশ", "টাকা দিয়েছি"]
_SETTLE = ["settlement", "settle", "settled", "সেটেলমেন্ট", "নিষ্পত্তি"]
_WRONG = ["wrong number", "wrong person", "wrong recipient", "wrong account", "wrong agent",
          "wrong merchant", "by mistake", "mistakenly", "mistake", "accidentally",
          "typed it wrong", "sent to wrong", "ভুল নম্বর", "ভুল মানুষ", "ভুল করে",
          "ভুল নাম্বার", "ভুল এজেন্ট"]
_NOTRECV = ["didn't get", "didnt get", "did not get", "didn't receive",
            "did not receive", "not received", "hasn't received",
            "haven't received", "never received", "পায়নি", "পাইনি"]
_SENT = ["sent", "transfer", "send", "পাঠিয়েছি", "পাঠালাম", "পাঠিয়েছিলাম"]
_REFUND = ["refund", "money back", "return my", "want my money", "changed my mind",
           "ফেরত", "রিফান্ড", "ফেরত চাই"]
# A contested refund (service failure) routes to disputes, not plain customer support.
_CONTESTED = _NOTRECV + ["defective", "not working", "didn't work", "did not work",
                         "not delivered", "never got", "damaged", "faulty", "broken",
                         "wrong item", "cheated", "scammed"]


def _has(text: str, terms: List[str]) -> bool:
    return any(t in text for t in terms)


def detect_case_type(signals: Signals) -> CaseType:
    """Classify the complaint by intent. Priority order matters (safety first)."""
    t = signals.normalized
    if _has(t, _PHISH) or (_has(t, _CRED) and _has(t, _ASK)):
        return CaseType.phishing_or_social_engineering
    if _has(t, _DUP):
        return CaseType.duplicate_payment
    if _has(t, _CASHIN) or (_has(t, _AGENT) and _has(t, _DEPOSIT)):
        return CaseType.agent_cash_in_issue
    if _has(t, _SETTLE):
        return CaseType.merchant_settlement_delay
    if _has(t, _FAILED) or (_has(t, _DEDUCT) and _has(t, _BALANCE)):
        return CaseType.payment_failed
    if _has(t, _WRONG) or (_has(t, _SENT) and _has(t, _NOTRECV)):
        return CaseType.wrong_transfer
    if _has(t, _REFUND):
        return CaseType.refund_request
    return CaseType.other


@dataclass
class Decision:
    """The evidence-backed outcome for one ticket."""
    evidence_verdict: EvidenceVerdict
    severity: Severity
    department: Department
    human_review_required: bool
    confidence: float
    reason_codes: List[str]


def _established_recipient(matched: TransactionEntry, history: List[TransactionEntry]) -> bool:
    """True if the recipient has received multiple transfers (not a one-off)."""
    cp = matched.counterparty
    if not cp:
        return False
    return sum(1 for x in history if x.type == "transfer" and x.counterparty == cp) >= 2


_DEPARTMENT = {
    CaseType.wrong_transfer: Department.dispute_resolution,
    CaseType.payment_failed: Department.payments_ops,
    CaseType.duplicate_payment: Department.payments_ops,
    CaseType.agent_cash_in_issue: Department.agent_operations,
    CaseType.merchant_settlement_delay: Department.merchant_operations,
    CaseType.phishing_or_social_engineering: Department.fraud_risk,
    CaseType.refund_request: Department.customer_support,
    CaseType.other: Department.customer_support,
}


def evaluate(
    case_type: CaseType,
    matched: Optional[TransactionEntry],
    match_status: str,
    history: List[TransactionEntry],
    signals: Signals,
) -> Decision:
    """Derive verdict, severity, routing, escalation, confidence and reason codes."""
    # Evidence verdict
    if case_type == CaseType.phishing_or_social_engineering or matched is None:
        verdict = EvidenceVerdict.insufficient_data
    elif case_type == CaseType.wrong_transfer and _established_recipient(matched, history):
        verdict = EvidenceVerdict.inconsistent
    else:
        verdict = EvidenceVerdict.consistent

    # A refund is "contested" (a service failure, not a change of mind) when the
    # transaction failed/stalled or the complaint describes a delivery/quality problem.
    contested_refund = case_type == CaseType.refund_request and (
        (matched is not None and matched.status in ("failed", "pending", "reversed"))
        or _has(signals.normalized, _CONTESTED)
    )

    # Amount in scope (for severity / escalation)
    amount = matched.amount if matched and matched.amount else (max(signals.amounts) if signals.amounts else 0)
    high_amount = amount >= HIGH_AMOUNT

    # Severity
    if case_type == CaseType.phishing_or_social_engineering:
        severity = Severity.critical
    elif case_type in (CaseType.payment_failed, CaseType.duplicate_payment, CaseType.agent_cash_in_issue):
        severity = Severity.high
    elif case_type == CaseType.wrong_transfer:
        severity = Severity.high if verdict == EvidenceVerdict.consistent else Severity.medium
    elif case_type == CaseType.merchant_settlement_delay:
        severity = Severity.medium
    elif contested_refund:
        severity = Severity.medium
    else:
        severity = Severity.low
    if high_amount and severity in (Severity.low, Severity.medium):
        severity = Severity.high

    department = Department.dispute_resolution if contested_refund else _DEPARTMENT[case_type]

    # Escalation to a human reviewer
    human_review_required = (
        case_type in (
            CaseType.phishing_or_social_engineering,
            CaseType.duplicate_payment,
            CaseType.agent_cash_in_issue,
        )
        or (case_type == CaseType.wrong_transfer and matched is not None)
        or contested_refund
        or verdict == EvidenceVerdict.inconsistent
        or severity == Severity.critical
        or high_amount
    )

    # Confidence
    if case_type == CaseType.phishing_or_social_engineering:
        confidence = 0.95
    elif verdict == EvidenceVerdict.inconsistent:
        confidence = 0.75
    elif matched is not None:
        confidence = 0.92 if case_type == CaseType.duplicate_payment else 0.9
    elif match_status == "ambiguous":
        confidence = 0.65
    else:
        confidence = 0.6

    # Reason codes
    reason_codes = [case_type.value]
    if matched is not None:
        reason_codes.append("transaction_match")
    elif match_status == "ambiguous":
        reason_codes.append("ambiguous_match")
    else:
        reason_codes.append("no_transaction_match")
    reason_codes.append(f"evidence_{verdict.value}")
    if human_review_required:
        reason_codes.append("human_review")

    return Decision(verdict, severity, department, human_review_required, confidence, reason_codes)
