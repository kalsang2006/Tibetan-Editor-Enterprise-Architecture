"""FastAPI REST endpoint handlers for the TEEA Local Service.

Defines Pydantic request/response schemas and HTTP route handlers that delegate
to the underlying :class:`~teea.engine.TEEAEngine`.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from teea.engine import TEEAEngine
from teea.fusion import SuggestionPriority

router = APIRouter()

# Telemetry counters
_STATS = {
    "requests_total": 0,
    "total_latency_ms": 0.0,
    "start_time": time.time(),
}


# --- Request & Response Schemas ---

class HealthResponse(BaseModel):
    """Schema for health status response."""

    status: str = "ok"
    version: str
    ai_active: bool
    vocabulary_size: int
    plugins_loaded: list[str]


class TextSpanModel(BaseModel):
    """Schema for text character and byte offsets."""

    char_start: int
    char_end: int
    byte_start: int
    byte_end: int


class SuggestionModel(BaseModel):
    """Schema for an individual suggestion."""

    id: str
    source: str
    span: TextSpanModel
    replacement: str | None = None
    score: float
    priority: str
    message: str
    error_type: str = "SPELLING"
    context_before: str = ""
    context_after: str = ""


class AnalysisRequest(BaseModel):
    """Schema for document analysis request."""

    text: str = Field(..., description="Tibetan text to analyze")


class AnalysisResponse(BaseModel):
    """Schema for document analysis response."""

    ok: bool = True
    suggestions: list[SuggestionModel]
    char_count: int
    latency_ms: float


class LegacyIpcRequest(BaseModel):
    """Schema for legacy IPC envelope request."""

    protocol_version: str | None = "1.0"
    method: str = "analysis.run"
    params: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None
    request_id: str = "req-1"
    expects_response: bool | None = True


class LegacyIpcResponse(BaseModel):
    """Schema for legacy IPC envelope response."""

    ok: bool = True
    request_id: str
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class AIRewriteRequest(BaseModel):
    """Schema for AI rewrite request."""

    text: str
    template: str = "formal"


class AIRewriteResponse(BaseModel):
    """Schema for AI rewrite response."""

    ok: bool = True
    output: str
    template: str


class MetricsResponse(BaseModel):
    """Schema for service telemetry metrics."""

    requests_total: int
    avg_latency_ms: float
    uptime_seconds: float


# --- Helper Functions ---

def _get_engine(request: Request) -> TEEAEngine:
    engine: TEEAEngine | None = getattr(request.app.state, "engine", None)
    if engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TEEA Engine is initializing or unavailable.",
        )
    return engine


def _extract_context(full_text: str, start: int, end: int, window: int = 20) -> tuple[str, str]:
    context_before = full_text[max(0, start - window) : start]
    context_after = full_text[end : min(len(full_text), end + window)]
    return context_before, context_after


# --- Route Handlers ---

@router.get("/health", response_model=HealthResponse)
def get_health(request: Request) -> HealthResponse:
    """Return health check and model readiness status."""
    engine = _get_engine(request)
    data = engine.health()
    return HealthResponse(
        status=data["status"],
        version=data["version"],
        ai_active=data["ai_active"],
        vocabulary_size=data["vocabulary_size"],
        plugins_loaded=data["plugins_loaded"],
    )


@router.post("/analyze", response_model=AnalysisResponse)
def analyze_text(payload: AnalysisRequest, request: Request) -> AnalysisResponse:
    """Primary REST endpoint for Tibetan document analysis."""
    start_time = time.perf_counter()
    engine = _get_engine(request)

    text = payload.text
    unified = engine.analyze(text)

    suggestions_list: list[SuggestionModel] = []
    for s in unified.suggestions:
        ctx_before, ctx_after = _extract_context(text, s.span.char_start, s.span.char_end)
        p_str = s.priority.value if isinstance(s.priority, SuggestionPriority) else str(s.priority)
        suggestions_list.append(
            SuggestionModel(
                id=f"{s.source}:{s.span.char_start}:{s.span.char_end}",
                source=s.source,
                span=TextSpanModel(
                    char_start=s.span.char_start,
                    char_end=s.span.char_end,
                    byte_start=s.span.byte_start,
                    byte_end=s.span.byte_end,
                ),
                replacement=s.replacement,
                score=s.score,
                priority=p_str,
                message=s.message,
                error_type=s.error_type,
                context_before=ctx_before,
                context_after=ctx_after,
            )
        )

    latency_ms = (time.perf_counter() - start_time) * 1000.0

    _STATS["requests_total"] += 1
    _STATS["total_latency_ms"] += latency_ms

    return AnalysisResponse(
        ok=True,
        suggestions=suggestions_list,
        char_count=len(text),
        latency_ms=round(latency_ms, 2),
    )


@router.post("/api/analysis/run", response_model=LegacyIpcResponse)
def run_legacy_analysis(payload: LegacyIpcRequest, request: Request) -> LegacyIpcResponse:
    """Backward-compatible IPC JSON envelope endpoint for Word add-in bridge."""
    text = str(payload.params.get("text", ""))
    req_id = payload.request_id

    engine = _get_engine(request)
    unified = engine.analyze(text)

    raw_suggestions = []
    for s in unified.suggestions:
        raw_suggestions.append(
            {
                "source": s.source,
                "span": {
                    "char_start": s.span.char_start,
                    "char_end": s.span.char_end,
                    "byte_start": s.span.byte_start,
                    "byte_end": s.span.byte_end,
                },
                "replacement": s.replacement,
                "score": s.score,
                "priority": (
                    s.priority.value
                    if isinstance(s.priority, SuggestionPriority)
                    else str(s.priority)
                ),
                "error_type": s.error_type,
                "message": s.message,
            }
        )

    return LegacyIpcResponse(
        ok=True,
        request_id=req_id,
        result={"suggestions": raw_suggestions},
    )


@router.post("/api/plagiarism/check")
@router.post("/api/plagiarism/check/")
@router.post("/api/plagiarism")
@router.post("/plagiarism/check")
@router.post("/plagiarism")
def run_legacy_plagiarism(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Flexible JSON endpoint for plagiarism check (supports raw REST & IPC envelope)."""
    raw_params = payload.get("params")
    params = raw_params if isinstance(raw_params, dict) else payload
    text = str(params.get("text") or payload.get("text") or "")
    min_similarity = float(params.get("min_similarity") or payload.get("min_similarity") or 0.05)
    req_id = str(payload.get("request_id") or "req-1")
    is_ipc = "method" in payload or "params" in payload

    engine = _get_engine(request)
    plag_engine = getattr(engine, "plagiarism_engine", None)
    check_fn = getattr(plag_engine, "detect", None) if plag_engine is not None else None
    if check_fn is None and plag_engine is not None:
        check_fn = getattr(plag_engine, "check", None)
    if plag_engine is not None and text.strip() and check_fn is not None:
        match_result = check_fn(text, min_similarity=min_similarity)
        top_sim = getattr(match_result, "max_similarity", 0.0)
        orig_score = max(0.0, round((1.0 - top_sim) * 100.0, 1))
        res_dict = {
            "originality_score": orig_score,
            "matches": [
                {
                    "document_id": m.document_id,
                    "collection": getattr(m, "collection", None),
                    "filename": getattr(m, "filename", None),
                    "similarity": m.similarity,
                    "coverage": m.coverage,
                    "overlap_count": m.overlap_count,
                    "query_fingerprint_count": m.query_fingerprint_count,
                    "doc_fingerprint_count": m.doc_fingerprint_count,
                    "source_span": (
                        {
                            "char_start": m.source_span.char_start,
                            "char_end": m.source_span.char_end,
                            "byte_start": m.source_span.byte_start,
                            "byte_end": m.source_span.byte_end,
                        }
                        if m.source_span
                        else None
                    ),
                }
                for m in match_result.matches
            ],
            "query_fingerprint_count": match_result.query_fingerprint_count,
            "total_corpus_documents": match_result.total_corpus_documents,
            "elapsed_ms": match_result.elapsed_ms,
        }
    else:
        res_dict = {
            "originality_score": 100.0,
            "matches": [],
            "query_fingerprint_count": 0,
            "total_corpus_documents": getattr(plag_engine, "size", 0) if plag_engine else 0,
            "elapsed_ms": 0.0,
        }

    if is_ipc:
        return {
            "ok": True,
            "request_id": req_id,
            "result": res_dict,
            "error": None,
        }
    return res_dict


@router.post("/ai/rewrite", response_model=AIRewriteResponse)
def ai_rewrite(payload: AIRewriteRequest, request: Request) -> AIRewriteResponse:
    """AI text rewriting endpoint."""
    engine = _get_engine(request)
    rewritten = engine.rewrite(payload.text, template=payload.template)
    return AIRewriteResponse(
        ok=True,
        output=rewritten,
        template=payload.template,
    )


@router.get("/metrics", response_model=MetricsResponse)
def get_metrics() -> MetricsResponse:
    """Return performance and usage metrics."""
    total = _STATS["requests_total"]
    avg_lat = (_STATS["total_latency_ms"] / total) if total > 0 else 0.0
    uptime = time.time() - _STATS["start_time"]
    return MetricsResponse(
        requests_total=total,
        avg_latency_ms=round(avg_lat, 2),
        uptime_seconds=round(uptime, 2),
    )
