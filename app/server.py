"""FastAPI server: one in-memory Session per browser tab."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from anamnesis.engine import Session, resources

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Anamnesis")
SESSIONS: dict[str, Session] = {}


class ChatIn(BaseModel):
    session_id: str | None = None
    text: str


@app.on_event("startup")
def warm() -> None:
    resources()


@app.post("/api/chat")
def chat(body: ChatIn) -> dict:
    sid = body.session_id if body.session_id in SESSIONS else uuid.uuid4().hex
    session = SESSIONS.setdefault(sid, Session())
    return {"session_id": sid, **session.handle(body.text)}


@app.get("/api/health")
def health() -> dict:
    model, _ = resources()
    return {"diseases": len(model.diseases), "symptoms": len(model.symptoms)}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
