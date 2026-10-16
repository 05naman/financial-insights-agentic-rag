import json
import logging
import time
from dataclasses import asdict
from datetime import timedelta

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.deps import (
    ChatRepoDep,
    ContainerDep,
    CurrentUser,
    DocumentsRepoDep,
    RateLimitedUser,
)
from app.db.models import User
from app.llm.base import LLMError
from app.schemas.chat import AnswerOut, AskRequest, MessageOut, SessionOut
from app.services import documents as docs_svc
from app.services.qa import AnswerResult

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


def _out(r: AnswerResult) -> AnswerOut:
    return AnswerOut(
        answer=r.answer,
        citations=[asdict(c) for c in r.citations],
        steps=r.steps,
        llm_calls=r.llm_calls,
        mode=r.mode,
    )


async def _owned_session(chat_repo, session_id: int, user: User):
    chat = await chat_repo.get_session(session_id, user.id)
    if not chat:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat session not found")
    return chat


@router.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(user: CurrentUser, repo: ChatRepoDep):
    return await repo.create_session(user.id)


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(user: CurrentUser, repo: ChatRepoDep):
    await repo.purge_empty_sessions(user.id, timedelta(minutes=10))
    return await repo.list_sessions(user.id)


@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
async def get_messages(session_id: int, user: CurrentUser, repo: ChatRepoDep):
    await _owned_session(repo, session_id, user)
    return await repo.messages(session_id)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: int, user: CurrentUser, repo: ChatRepoDep):
    await repo.delete_session(await _owned_session(repo, session_id, user))


async def _prepare(session_id, req, user, chat_repo, docs_repo, container):
    chat = await _owned_session(chat_repo, session_id, user)
    prior = await chat_repo.messages(session_id)
    history = [{"role": m.role, "content": m.content} for m in prior][-6:]
    if not prior:  # first question names the chat
        chat.title = req.question[:60]
    user_msg = await chat_repo.add_message(session_id, "user", req.question)
    qa = container.qa_service(await docs_svc.catalog(docs_repo))
    return qa, history, user_msg.id


@router.post("/sessions/{session_id}/ask", response_model=AnswerOut)
async def ask(
    session_id: int,
    req: AskRequest,
    user: RateLimitedUser,
    chat_repo: ChatRepoDep,
    docs_repo: DocumentsRepoDep,
    container: ContainerDep,
):
    qa, history, user_msg_id = await _prepare(
        session_id, req, user, chat_repo, docs_repo, container
    )
    started = time.perf_counter()
    try:
        result = await qa.answer(req.question, mode=req.mode, history=history)
    except BaseException:
        await chat_repo.delete_message(user_msg_id)  # no dangling question in the history
        raise
    _log_answer(user, session_id, req, result, started)
    await chat_repo.add_message(
        session_id, "assistant", result.answer, [asdict(c) for c in result.citations], result.steps
    )
    return _out(result)


def _log_answer(
    user: User, session_id: int, req: AskRequest, result: AnswerResult, started: float
) -> None:
    """Operational facts only: no question or answer text (it can contain anything the user typed)."""
    logger.info(
        "answered user=%s session=%s mode=%s q_len=%d llm_calls=%d citations=%d in %.1fs",
        user.id,
        session_id,
        req.mode,
        len(req.question),
        result.llm_calls,
        len(result.citations),
        time.perf_counter() - started,
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post("/sessions/{session_id}/stream")
async def stream(
    session_id: int,
    req: AskRequest,
    user: RateLimitedUser,
    chat_repo: ChatRepoDep,
    docs_repo: DocumentsRepoDep,
    container: ContainerDep,
):
    """Server-sent events: `step` per agent node, then `final` with answer and citations."""
    qa, history, user_msg_id = await _prepare(
        session_id, req, user, chat_repo, docs_repo, container
    )

    async def events():
        started = time.perf_counter()
        saved = False
        try:
            result = None
            if req.mode != "agentic":
                result = await qa.answer(req.question, mode=req.mode, history=history)
            else:
                async for ev in qa.stream(req.question, history):
                    if ev["type"] == "step":
                        yield _sse("step", ev["step"])
                    else:
                        result = ev["result"]
            if result is None:
                raise RuntimeError("no answer was produced")
            # save BEFORE sending the final event: a client that disconnects can no longer lose the answer
            await chat_repo.add_message(
                session_id,
                "assistant",
                result.answer,
                [asdict(c) for c in result.citations],
                result.steps,
            )
            saved = True
            _log_answer(user, session_id, req, result, started)
            yield _sse("final", _out(result).model_dump())
        except LLMError:
            yield _sse(
                "error",
                {
                    "detail": "The language model is unavailable or rate-limited. Please try again shortly."
                },
            )
        except Exception:
            logger.exception("stream failed")
            yield _sse(
                "error", {"detail": "Something went wrong while answering. Please try again."}
            )
        finally:
            if not saved:  # no answer: take the question back out so history has no dangling turn
                try:
                    await chat_repo.delete_message(user_msg_id)
                except Exception:
                    logger.exception("could not roll back the unanswered question")

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
