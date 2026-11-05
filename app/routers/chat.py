from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import chat as chat_service
from .. import models, schemas
from ..db import get_db

router = APIRouter(prefix="/api/chat", tags=["chat"])

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.get("/sessions")
def list_sessions(db: Session = Depends(get_db)):
    return [
        {
            "id": session.id,
            "title": session.title,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
        }
        for session in chat_service.list_sessions(db)
    ]


@router.post("/sessions", status_code=201)
def create_session(data: dict | None = None, db: Session = Depends(get_db)):
    title = ((data or {}).get("title") or "新对话").strip() or "新对话"
    session = chat_service.create_session(db, title=title)
    return {
        "id": session.id,
        "title": session.title,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }


@router.get("/sessions/{session_id}")
def get_session(session_id: int, db: Session = Depends(get_db)):
    session = db.get(models.ChatSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return chat_service.session_detail(db, session)


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: int, db: Session = Depends(get_db)):
    session = db.get(models.ChatSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    chat_service.delete_session(db, session_id)


@router.post("")
def chat(data: schemas.ChatRequest, db: Session = Depends(get_db)):
    try:
        session = chat_service.ensure_session(db, data.session_id, data.message)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return StreamingResponse(
        chat_service.stream_answer(session.id, data.message),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
