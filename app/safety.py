"""Final safety net over outgoing text.

Templates in replies.py are already safe; this guarantees the safety rules hold
even for unexpected content, and never mangles correctly-phrased safe text.
"""
import re

_SAFE_REFUND = "any eligible amount will be returned through official channels"
_PIN_NOTE_EN = "Please do not share your PIN or OTP with anyone."

_CRED = r"(pin|otp|password|one[\s-]?time\s?password|cvv|card\s*(number|no))"
_ASK_VERB = r"(share|send|provide|enter|give|tell|type|submit|confirm)"
_NEG = r"(do not|don't|dont|never|won't|will not|no need|cannot|can't|do n't)"

# Unauthorized financial promises (the safe phrasing is intentionally excluded).
_REFUND_PROMISES = [
    r"\bwe('ll| will| are going to| can| shall) (refund|reverse|return your money|unblock|credit you back|recover)\b",
    r"\bwe('ve| have| already) (refunded|reversed|unblocked|recovered)\b",
    r"\byour (refund|reversal|account|money) (has been|is being|will be|has) (processed|confirmed|approved|unblocked|recovered)\b",
    r"\byou (will|'ll) (get|receive) (a |your )?(refund|money back|reversal)\b",
    r"\bguarantee(d)? (a |the )?(refund|reversal|recovery)\b",
]
_THIRD_PARTY = r"\b(call|whatsapp|message|text)\s+(\+?\d[\d\s-]{6,})"


def _has_credential_request(sentence: str) -> bool:
    s = sentence.lower()
    if not re.search(_CRED, s) or not re.search(_ASK_VERB, s):
        return False
    return re.search(_NEG, s) is None


def sanitize(text: str) -> str:
    """Strip credential requests, rewrite refund promises, remove third-party redirects."""
    if not text:
        return text

    # Drop any sentence that actively requests credentials.
    sentences = re.split(r"(?<=[.!?।])\s+", text)
    kept = [s for s in sentences if not _has_credential_request(s)]
    cleaned = " ".join(kept).strip()
    if not kept and _PIN_NOTE_EN not in cleaned:
        cleaned = _PIN_NOTE_EN

    # Rewrite unauthorized refund/reversal promises to safe phrasing.
    for pattern in _REFUND_PROMISES:
        cleaned = re.sub(pattern, _SAFE_REFUND, cleaned, flags=re.IGNORECASE)

    # Remove instructions to contact arbitrary third-party numbers.
    cleaned = re.sub(_THIRD_PARTY, "contact our official support channels", cleaned, flags=re.IGNORECASE)
    return cleaned
