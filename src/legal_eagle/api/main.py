"""FastAPI app for Legal Eagle AI.

Endpoints:
  POST /research     body: {"query": "..."}  -> {"session_id": "..."}
  GET  /report/{id}                          -> full structured report
  GET  /healthz                             -> liveness
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..db import DB
from ..pipeline import ResearchPipeline
from ..schemas.reports import ResearchReport

logger = logging.getLogger(__name__)

app = FastAPI(title="Legal Eagle AI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_pipeline: Optional[ResearchPipeline] = None
_db: Optional[DB] = None


def get_pipeline() -> ResearchPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = ResearchPipeline()
    return _pipeline


def get_db() -> DB:
    global _db
    if _db is None:
        _db = DB()
    return _db


class ResearchRequest(BaseModel):
    query: str


class ResearchAck(BaseModel):
    session_id: str


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/research", response_model=ResearchAck)
async def start_research(req: ResearchRequest) -> ResearchAck:
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")
    pipeline = get_pipeline()
    report = await pipeline.run(req.query)
    return ResearchAck(session_id=report.session_id)


@app.get("/report/{session_id}", response_model=ResearchReport)
async def get_report(session_id: str) -> ResearchReport:
    db = get_db()
    report = db.get_report(session_id)
    if report is None:
        raise HTTPException(status_code=404, detail="session not found")
    return report
