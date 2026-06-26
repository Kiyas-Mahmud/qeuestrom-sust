# QueueStorm Investigator

An AI/API support copilot for the **SUST CSE Carnival 2026 · Codex Community Hackathon**
preliminary round. It reads one fintech support ticket plus a short transaction-history
snippet, **investigates** whether the complaint is supported by the data, classifies and
routes the case, and drafts a **safe** customer reply.

It is a support copilot, **not** a financial authority: it never asks for PIN/OTP/password
and never promises a refund, reversal, or unblock it cannot authorize.

## Live service
- Base URL: **https://queuestorm-investigator-91iq.onrender.com**
- Health: https://queuestorm-investigator-91iq.onrender.com/health
- Analyze: `POST https://queuestorm-investigator-91iq.onrender.com/analyze-ticket`

## Endpoints
| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Readiness probe → `{"status":"ok"}` |
| POST | `/analyze-ticket` | Analyze one ticket → structured JSON |

HTTP codes: `200` valid · `400` malformed/missing required field · `422` empty complaint ·
`500` internal (non-sensitive body, never crashes).

## Tech stack
- Python 3.12, FastAPI, Pydantic v2, Uvicorn.
- No database, no external network calls, no model downloads. Stateless and in-process.

## AI approach
**Deterministic rule-based engine — no LLM.** The pipeline:
1. `signals` — parse the complaint as untrusted data: amounts (incl. Bangla numerals), phone
   numbers, transaction ids, intent/safety keywords (English/Bangla/Banglish), language.
2. `matching` — score each transaction (amount, expected type, counterparty, status, recency)
   and pick the `relevant_transaction_id`, or return `null` when there is no match or the match
   is genuinely ambiguous.
3. `classify` — derive `case_type`, `evidence_verdict`, `severity`, `department`, and
   `human_review_required`.
4. `replies` — build the agent summary, next action, and a templated customer reply in the
   complaint's language (English or Bangla).
5. `safety` — a final sanitizer guaranteeing the safety rules on outgoing text.

### Evidence reasoning
- `consistent` — a matched transaction supports the complaint.
- `inconsistent` — a matched transaction contradicts it (e.g. a "wrong transfer" claim to a
  counterparty that already received several prior transfers — an established recipient).
- `insufficient_data` — no match, an ambiguous match, or a vague complaint. The service asks
  for clarification instead of guessing.

## Safety logic
Enforced both by controlled templates and by a defense-in-depth sanitizer (`app/safety.py`):
1. **Never requests credentials** (PIN/OTP/password/card). Replies actively remind customers not
   to share them.
2. **Never promises financial action.** Uses "any eligible amount will be returned through
   official channels", never "we will refund you".
3. **Directs only to official support channels** — never to a third party.
4. **Ignores prompt injection.** Complaint text is data only; it is never executed and never
   reflected verbatim into the response.

## MODELS
| Model | Where it runs | Why |
|---|---|---|
| _None_ | — | A deterministic rule engine is used instead of any ML/LLM. Chosen for **zero cost**, **sub-second latency** (well within the 30s limit), **no external dependency** during judging, and **provably safe** output. The rubric states an LLM is not required to score well, and safety is the top tie-breaker. |

## Setup & run (local)
```bash
python -m venv .venv
.venv/Scripts/activate         # Windows
# source .venv/bin/activate    # Linux/macOS
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Run with Docker
```bash
docker build -t queuestorm .
docker run -p 8000:8000 queuestorm
# with a custom port: docker run -p 9000:9000 -e PORT=9000 queuestorm
```

## Tests
```bash
pytest -q
```
Covers all 10 public sample cases (functional equivalence on transaction, verdict, case_type,
department, severity, escalation), HTTP status codes, malformed input, empty history, and a
prompt-injection attempt.

## Sample request / response
Request:
```json
{
  "ticket_id": "TKT-001",
  "complaint": "I sent 5000 taka to a wrong number around 2pm today...",
  "transaction_history": [
    {"transaction_id":"TXN-9101","timestamp":"2026-04-14T14:08:22Z","type":"transfer","amount":5000,"counterparty":"+8801719876543","status":"completed"}
  ]
}
```
Response:
```json
{
  "ticket_id": "TKT-001",
  "relevant_transaction_id": "TXN-9101",
  "evidence_verdict": "consistent",
  "case_type": "wrong_transfer",
  "severity": "high",
  "department": "dispute_resolution",
  "agent_summary": "Customer reports sending 5000 BDT via TXN-9101 to +8801719876543, now believed to be the wrong recipient.",
  "recommended_next_action": "Verify TXN-9101 details with the customer and initiate the wrong-transfer dispute workflow per policy.",
  "customer_reply": "We have noted your concern about transaction TXN-9101. Please do not share your PIN or OTP with anyone. Our dispute team will review the case and contact you through official support channels.",
  "human_review_required": true,
  "confidence": 0.9,
  "reason_codes": ["wrong_transfer", "transaction_match", "evidence_consistent", "human_review"]
}
```
More worked examples are in [`sample_output.json`](sample_output.json) (all 10 sample cases).

## Runbook (for judges)
A stranger can bring the service up from a clean checkout:
```bash
# Option A — Python
python -m venv .venv && . .venv/Scripts/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
curl http://localhost:8000/health
curl -X POST http://localhost:8000/analyze-ticket -H "content-type: application/json" \
  -d '{"ticket_id":"T1","complaint":"I sent 5000 to a wrong number","transaction_history":[{"transaction_id":"TXN-1","type":"transfer","amount":5000,"counterparty":"+8801700000000","status":"completed"}]}'

# Option B — Docker
docker build -t queuestorm .
docker run -p 8000:8000 queuestorm
```

## Assumptions
- Only `ticket_id` and `complaint` are required; all other input fields are optional and
  unknown/invalid optional values are tolerated rather than rejected (hidden tests may be
  malformed).
- Timestamps may be unreliable, so matching relies primarily on amount, type, counterparty, and
  status, with recency only as a tie-breaker.
- Agent summary and recommended next action are internal (English); the customer reply follows
  the complaint's language (English or Bangla).

## Known limitations
- Bangla/Banglish coverage is keyword-based; very colloquial phrasing or transliterations outside
  the keyword sets may fall back to `other` / `insufficient_data` (which is the safe default).
- Amount extraction handles Latin and Bangla digits but not spelled-out amounts ("five thousand").
- The engine intentionally returns `insufficient_data` rather than guessing on ambiguous histories.

## Security
No secrets are required or committed. The service emits no stack traces, tokens, or secrets in
responses or logs. See `.env.example` for the only (optional) environment variable, `PORT`.
