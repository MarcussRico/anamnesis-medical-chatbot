"""FastAPI server. Stateless: each request carries its conversation, so any instance can answer."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from anamnesis.engine import Session, resources

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Anamnesis")


class ChatIn(BaseModel):
    session: dict | None = None
    text: str


@app.on_event("startup")
def warm() -> None:
    resources()


@app.post("/api/chat")
def chat(body: ChatIn) -> dict:
    session = Session.from_dict(body.session)
    reply = session.handle(body.text)
    return {"session": session.to_dict(), **reply}


@app.get("/api/health")
def health() -> dict:
    model, _ = resources()
    return {"diseases": len(model.diseases), "symptoms": len(model.symptoms)}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
