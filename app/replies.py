"""Build the agent-facing and customer-facing text.

Agent summary / next action are internal (English). The customer reply is
returned in the complaint's language. Text is templated and only fills in
verified facts (txn id / amount) so untrusted complaint text is never echoed.
"""
from typing import List, Optional, Tuple

from app.classify import Decision
from app.schemas import CaseType, EvidenceVerdict, TransactionEntry
from app.signals import Signals

_PIN_NOTE_EN = "Please do not share your PIN or OTP with anyone."
_PIN_NOTE_BN = "অনুগ্রহ করে কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না।"


def _amount_str(amount: Optional[float]) -> str:
    if amount is None:
        return "the reported amount"
    return f"{int(amount)} BDT" if float(amount).is_integer() else f"{amount} BDT"


def _txn_label(matched: Optional[TransactionEntry]) -> Optional[str]:
    return matched.transaction_id if matched and matched.transaction_id else None


def _agent_summary(case_type, matched, decision, signals) -> str:
    txn = _txn_label(matched)
    amount = _amount_str(matched.amount if matched else (max(signals.amounts) if signals.amounts else None))
    cp = matched.counterparty if matched else None

    if case_type == CaseType.phishing_or_social_engineering:
        return ("Customer reports an unsolicited contact claiming to be from the company and "
                "requesting credentials. Likely social engineering; no credentials shared per the report.")
    if case_type == CaseType.wrong_transfer:
        if decision.evidence_verdict == EvidenceVerdict.inconsistent:
            return (f"Customer claims {txn} ({amount} to {cp}) was a wrong transfer, but history shows "
                    f"repeated transfers to the same counterparty, suggesting an established recipient.")
        if matched is None:
            return ("Customer reports a transfer that the recipient did not receive, but the specific "
                    "transaction cannot be identified from the history without more detail.")
        return f"Customer reports sending {amount} via {txn} to {cp}, now believed to be the wrong recipient."
    if case_type == CaseType.payment_failed:
        return f"Customer attempted a {amount} payment ({txn}) which failed but reports the balance was deducted."
    if case_type == CaseType.duplicate_payment:
        return f"Customer reports a duplicate payment; {txn} appears to be a repeated charge of {amount}."
    if case_type == CaseType.agent_cash_in_issue:
        return f"Customer reports an agent cash-in of {amount} ({txn}) not reflected in balance; status is pending."
    if case_type == CaseType.merchant_settlement_delay:
        return f"Merchant reports settlement {txn} of {amount} is delayed beyond the expected window; status pending."
    if case_type == CaseType.refund_request:
        return f"Customer requests a refund of {amount} for {txn} (completed merchant payment); not a service failure."
    return "Customer raised a vague concern without enough detail to identify a specific transaction."


def _next_action(case_type, matched, decision) -> str:
    txn = _txn_label(matched) or "the reported transaction"
    if case_type == CaseType.phishing_or_social_engineering:
        return ("Escalate to the fraud risk team immediately. Reassure the customer that the company never "
                "asks for OTP, and log the reported contact for fraud pattern analysis.")
    if case_type == CaseType.wrong_transfer:
        if decision.evidence_verdict == EvidenceVerdict.inconsistent:
            return ("Flag for human review. Verify with the customer whether this was genuinely a wrong "
                    "transfer given the established pattern with this recipient.")
        if matched is None:
            return ("Ask the customer for the recipient's number and exact amount to identify the correct "
                    "transaction. Do not initiate a dispute until the transaction is confirmed.")
        return f"Verify {txn} details with the customer and initiate the wrong-transfer dispute workflow per policy."
    if case_type == CaseType.payment_failed:
        return (f"Investigate {txn} ledger status. If the balance was deducted on a failed payment, initiate "
                "the automatic reversal flow within standard SLA.")
    if case_type == CaseType.duplicate_payment:
        return f"Verify the duplicate with payments operations. If the biller confirms a single payment, initiate reversal of {txn} per policy."
    if case_type == CaseType.agent_cash_in_issue:
        return f"Investigate the pending cash-in {txn} with agent operations and confirm the settlement state within the standard SLA."
    if case_type == CaseType.merchant_settlement_delay:
        return "Route to merchant operations to verify the settlement batch status and communicate a revised ETA to the merchant."
    if case_type == CaseType.refund_request:
        return ("Inform the customer that refund eligibility depends on the merchant's policy and guide them to "
                "contact the merchant through official channels.")
    return "Reply to the customer requesting the transaction ID, amount, the issue, and approximate time."


def _customer_reply(case_type, matched, decision, language) -> str:
    txn = _txn_label(matched)
    bn = language == "bn"

    if case_type == CaseType.phishing_or_social_engineering:
        if bn:
            return ("কোনো তথ্য শেয়ার করার আগে যোগাযোগ করার জন্য ধন্যবাদ। আমরা কখনোই আপনার পিন, ওটিপি বা "
                    "পাসওয়ার্ড চাই না। কেউ আমাদের পরিচয় দিলেও এগুলো কারো সাথে শেয়ার করবেন না। আমাদের ফ্রড "
                    "টিমকে এই ঘটনাটি জানানো হয়েছে।")
        return ("Thank you for reaching out before sharing any information. We never ask for your PIN, OTP, or "
                "password under any circumstances. Please do not share these with anyone, even if they claim to "
                "be from us. Our fraud team has been notified of this incident.")

    if case_type == CaseType.wrong_transfer and matched is None:
        if bn:
            return ("যোগাযোগ করার জন্য ধন্যবাদ। আপনার বর্ণনার সাথে মেলে এমন একাধিক লেনদেন রয়েছে। সঠিক "
                    "লেনদেনটি শনাক্ত করতে অনুগ্রহ করে প্রাপকের নম্বর ও সঠিক পরিমাণ জানান। " + _PIN_NOTE_BN)
        return ("Thank you for reaching out. We see multiple transactions that could match your description. "
                "Could you share the recipient's number and the exact amount so we can identify the right "
                "transaction? " + _PIN_NOTE_EN)

    ref = txn or ("উল্লেখিত লেনদেন" if bn else "the reported transaction")

    if case_type == CaseType.wrong_transfer:
        if bn:
            return (f"আপনার লেনদেন {ref} সম্পর্কে আমরা অবগত হয়েছি। {_PIN_NOTE_BN} আমাদের ডিসপিউট টিম বিষয়টি "
                    "পর্যালোচনা করে অফিসিয়াল চ্যানেলে আপনার সাথে যোগাযোগ করবে।")
        return (f"We have noted your concern about transaction {ref}. {_PIN_NOTE_EN} Our dispute team will "
                "review the case and contact you through official support channels.")
    if case_type == CaseType.payment_failed:
        if bn:
            return (f"আপনার লেনদেন {ref} এর কারণে ব্যালেন্স কেটে যেতে পারে বলে আমরা লক্ষ্য করেছি। আমাদের পেমেন্ট "
                    f"টিম বিষয়টি পর্যালোচনা করবে এবং যেকোনো প্রযোজ্য পরিমাণ অফিসিয়াল চ্যানেলের মাধ্যমে ফেরত দেওয়া "
                    f"হবে। {_PIN_NOTE_BN}")
        return (f"We have noted that transaction {ref} may have caused an unexpected balance deduction. Our "
                "payments team will review the case and any eligible amount will be returned through official "
                f"channels. {_PIN_NOTE_EN}")
    if case_type == CaseType.duplicate_payment:
        if bn:
            return (f"লেনদেন {ref} এর সম্ভাব্য ডুপ্লিকেট পেমেন্ট সম্পর্কে আমরা অবগত হয়েছি। আমাদের পেমেন্ট টিম যাচাই "
                    f"করবে এবং যেকোনো প্রযোজ্য পরিমাণ অফিসিয়াল চ্যানেলের মাধ্যমে ফেরত দেওয়া হবে। {_PIN_NOTE_BN}")
        return (f"We have noted the possible duplicate payment for transaction {ref}. Our payments team will "
                "verify with the biller and any eligible amount will be returned through official channels. "
                f"{_PIN_NOTE_EN}")
    if case_type == CaseType.agent_cash_in_issue:
        if bn:
            return (f"আপনার লেনদেন {ref} সম্পর্কে আমরা অবগত হয়েছি। আমাদের এজেন্ট অপারেশনস টিম একটি দ্রুত যাচাই "
                    f"করবে এবং অফিসিয়াল চ্যানেলে আপনাকে জানাবে। {_PIN_NOTE_BN}")
        return (f"We have noted your concern about transaction {ref}. Our agent operations team will investigate "
                f"and update you through official support channels. {_PIN_NOTE_EN}")
    if case_type == CaseType.merchant_settlement_delay:
        if bn:
            return (f"সেটেলমেন্ট {ref} সম্পর্কে আমরা অবগত হয়েছি। আমাদের মার্চেন্ট অপারেশনস টিম ব্যাচের অবস্থা যাচাই "
                    "করে অফিসিয়াল চ্যানেলে প্রত্যাশিত সময় জানাবে।")
        return (f"We have noted your concern about settlement {ref}. Our merchant operations team will check the "
                "batch status and update you on the expected settlement time through official channels.")
    if case_type == CaseType.refund_request:
        if bn:
            return ("যোগাযোগ করার জন্য ধন্যবাদ। সম্পন্ন মার্চেন্ট পেমেন্টের রিফান্ড মার্চেন্টের নিজস্ব নীতির উপর "
                    "নির্ভর করে। আমরা সরাসরি মার্চেন্টের সাথে যোগাযোগ করার পরামর্শ দিচ্ছি। সহায়তা প্রয়োজন হলে "
                    f"অফিসিয়াল সাপোর্ট চ্যানেলে জানান। {_PIN_NOTE_BN}")
        return ("Thank you for reaching out. Refunds for completed merchant payments depend on the merchant's "
                "own policy. We recommend contacting the merchant directly. If you need help, please reply and we "
                f"will guide you through official support channels. {_PIN_NOTE_EN}")
    if bn:
        return (f"যোগাযোগ করার জন্য ধন্যবাদ। দ্রুত সহায়তার জন্য অনুগ্রহ করে লেনদেন আইডি, পরিমাণ এবং কী সমস্যা "
                f"হয়েছে তা সংক্ষেপে জানান। {_PIN_NOTE_BN}")
    return ("Thank you for reaching out. To help you faster, please share the transaction ID, the amount "
            f"involved, and a short description of what went wrong. {_PIN_NOTE_EN}")


def build(
    case_type: CaseType,
    matched: Optional[TransactionEntry],
    decision: Decision,
    signals: Signals,
) -> Tuple[str, str, str]:
    """Return (agent_summary, recommended_next_action, customer_reply)."""
    summary = _agent_summary(case_type, matched, decision, signals)
    action = _next_action(case_type, matched, decision)
    reply = _customer_reply(case_type, matched, decision, signals.language)
    return summary, action, reply
