"""Extract structured signals from untrusted complaint text.

Complaint text is treated purely as data: we read facts out of it, we never
execute instructions embedded in it.
"""
import re
from dataclasses import dataclass, field
from typing import List

_BENGALI_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_BENGALI_RANGE = re.compile(r"[ঀ-৿]")
_TXN_ID = re.compile(r"\bTXN-\d+\b", re.IGNORECASE)
_PHONE = re.compile(r"(?:\+?880)?1[3-9]\d{8}")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


@dataclass
class Signals:
    """Facts parsed out of one complaint."""
    raw: str
    normalized: str          # lowercased, Bengali digits -> Latin
    language: str            # en | bn | mixed
    amounts: List[float] = field(default_factory=list)
    phones: List[str] = field(default_factory=list)
    txn_ids: List[str] = field(default_factory=list)


def detect_language(text: str, provided: str | None) -> str:
    """Prefer the provided language; otherwise detect Bengali script."""
    if provided in ("en", "bn", "mixed"):
        return provided
    has_bn = bool(_BENGALI_RANGE.search(text))
    has_latin = bool(re.search(r"[A-Za-z]", text))
    if has_bn and has_latin:
        return "mixed"
    return "bn" if has_bn else "en"


def _digits_only(value: str) -> str:
    return re.sub(r"\D", "", value)


def extract(complaint: str, provided_language: str | None = None) -> Signals:
    """Parse amounts, phone numbers, transaction ids and language."""
    language = detect_language(complaint, provided_language)
    normalized = complaint.translate(_BENGALI_DIGITS).lower()

    txn_ids = [m.group(0).upper() for m in _TXN_ID.finditer(normalized)]

    phones, phone_spans = [], []
    for m in _PHONE.finditer(normalized):
        phones.append(_digits_only(m.group(0)))
        phone_spans.append((m.start(), m.end()))

    # Mask out phone numbers and txn ids before reading monetary amounts.
    masked = list(normalized)
    for start, end in phone_spans:
        for i in range(start, end):
            masked[i] = " "
    masked_text = _TXN_ID.sub(" ", "".join(masked))

    amounts = []
    for m in _NUMBER.finditer(masked_text):
        value = float(m.group(0).replace(",", ""))
        if 0 < value <= 10_000_000 and len(_digits_only(m.group(0))) <= 7:
            amounts.append(value)

    return Signals(
        raw=complaint,
        normalized=normalized,
        language=language,
        amounts=amounts,
        phones=phones,
        txn_ids=txn_ids,
    )
