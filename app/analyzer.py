"""Orchestrate the analysis pipeline: signals -> match -> classify -> reply -> safety."""
from app import classify, matching, replies, safety, signals
from app.schemas import AnalyzeRequest, AnalyzeResponse


def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """Turn one ticket into a structured, safe, schema-valid response."""
    sig = signals.extract(request.complaint, request.language)
    case_type = classify.detect_case_type(sig)
    matched, match_status = matching.pick_transaction(sig, request.transaction_history, case_type)
    decision = classify.evaluate(case_type, matched, match_status, request.transaction_history or [], sig)

    summary, action, reply = replies.build(case_type, matched, decision, sig)
    reply = safety.sanitize(reply)
    action = safety.sanitize(action)

    return AnalyzeResponse(
        ticket_id=request.ticket_id,
        relevant_transaction_id=matched.transaction_id if matched else None,
        evidence_verdict=decision.evidence_verdict,
        case_type=case_type,
        severity=decision.severity,
        department=decision.department,
        agent_summary=summary,
        recommended_next_action=action,
        customer_reply=reply,
        human_review_required=decision.human_review_required,
        confidence=round(decision.confidence, 2),
        reason_codes=decision.reason_codes,
    )
