"""Select the transaction a complaint refers to, or report none/ambiguous."""
import re
from typing import List, Optional, Tuple

from app.classify import EXPECTED_STATUS, EXPECTED_TYPES
from app.schemas import CaseType, TransactionEntry
from app.signals import Signals


def _digits(value: Optional[str]) -> str:
    return re.sub(r"\D", "", value or "")


def _core_score(txn: TransactionEntry, signals: Signals, case_type: CaseType) -> float:
    """Evidence-only score (no recency), used to detect ambiguity."""
    score = 0.0
    if txn.amount is not None and any(abs(txn.amount - a) < 0.5 for a in signals.amounts):
        score += 5
    if txn.type and txn.type in EXPECTED_TYPES.get(case_type, set()):
        score += 2
    if txn.status and txn.status in EXPECTED_STATUS.get(case_type, set()):
        score += 2
    cp = _digits(txn.counterparty)
    if cp and any(cp == p or cp.endswith(p) or p.endswith(cp) for p in signals.phones):
        score += 4
    return score


def pick_transaction(
    signals: Signals,
    history: Optional[List[TransactionEntry]],
    case_type: CaseType,
) -> Tuple[Optional[TransactionEntry], str]:
    """Return (transaction, status) where status is matched | ambiguous | no_match."""
    history = history or []
    if not history:
        return None, "no_match"

    # An explicitly cited transaction id wins outright.
    if signals.txn_ids:
        for txn in history:
            if txn.transaction_id and txn.transaction_id.upper() in signals.txn_ids:
                return txn, "matched"

    scores = [(_core_score(txn, signals, case_type), idx, txn) for idx, txn in enumerate(history)]
    best = max(s for s, _, _ in scores)
    if best <= 0:
        return None, "no_match"

    top = [(idx, txn) for s, idx, txn in scores if s == best]
    if len(top) == 1:
        return top[0][1], "matched"

    # Duplicate payments: the later transaction is the suspected duplicate.
    if case_type == CaseType.duplicate_payment:
        return _latest(top), "matched"

    # Several equally-strong candidates with different recipients -> ambiguous.
    counterparties = {_digits(txn.counterparty) for _, txn in top}
    if len(counterparties) > 1:
        return None, "ambiguous"
    return _latest(top), "matched"


def _latest(candidates: List[Tuple[int, TransactionEntry]]) -> TransactionEntry:
    """Pick the most recent by timestamp, falling back to input order."""
    def key(item):
        _, txn = item
        return (txn.timestamp or "", item[0])
    return max(candidates, key=key)[1]
