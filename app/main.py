"""FastAPI app: endpoints, error handling, and HTTP status mapping."""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.analyzer import analyze
from app.schemas import AnalyzeRequest, AnalyzeResponse

logger = logging.getLogger("queuestorm")

app = FastAPI(title="QueueStorm Investigator", version="1.0")


@app.get("/")
def root():
    """Service info so the root path is friendly instead of a bare 404."""
    return {
        "service": "QueueStorm Investigator",
        "status": "ok",
        "endpoints": {
            "health": "GET /health",
            "analyze": "POST /analyze-ticket",
            "docs": "GET /docs",
        },
    }


@app.get("/health")
def health():
    """Liveness probe for the judge harness."""
    return {"status": "ok"}


@app.post("/analyze-ticket", response_model=AnalyzeResponse)
def analyze_ticket(request: AnalyzeRequest):
    """Analyze one ticket and return the structured, safe response."""
    if not request.complaint or not request.complaint.strip():
        return JSONResponse(status_code=422, content={"error": "complaint must not be empty"})
    return analyze(request)


@app.exception_handler(RequestValidationError)
def validation_error_handler(request: Request, exc: RequestValidationError):
    """Malformed JSON or missing required fields -> 400 (not the default 422)."""
    return JSONResponse(status_code=400, content={"error": "invalid request body"})


@app.exception_handler(Exception)
def internal_error_handler(request: Request, exc: Exception):
    """Catch-all: never leak stack traces or secrets; never crash the process."""
    logger.exception("unhandled error")
    return JSONResponse(status_code=500, content={"error": "internal error"})
