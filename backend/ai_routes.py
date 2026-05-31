"""
HTTP-роут для AI-чата: POST /api/ai/chat
"""
import logging
from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import BaseModel, Field

from ai_agent import run_agent

# Импортируем уже зарегистрированные tools — это запустит декораторы
import ai_tools_users  # noqa: F401
import ai_tools_leads  # noqa: F401

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _get_current_user_lazy(request: Request):
    """
    Ленивый импорт чтобы избежать циклов при старте.
    active_tokens вынесен в auth_state.py — единый объект
    независимо от double-import main.py (__main__ vs main).
    """
    from auth_state import active_tokens
    from db import db_cursor, q

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing Bearer token")

    token = auth[7:]
    user_id = active_tokens.get(token)
    if not user_id:
        raise HTTPException(401, "Invalid or expired token")

    with db_cursor() as cur:
        cur.execute(
            q("SELECT id, username, name, role FROM users WHERE id = %s"),
            (user_id,),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(401, "User not found")

    return {"id": row[0], "username": row[1], "name": row[2], "role": row[3]}


# === Request/Response models ===
class ChatMessage(BaseModel):
    role: str = Field(..., description="user | assistant")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: list[ChatMessage] | None = Field(
        default=None,
        description="Предыдущие сообщения чата (последние ~10)",
    )


class ToolCallLog(BaseModel):
    name: str
    args: dict
    result: dict


class ChatResponse(BaseModel):
    reply: str
    tool_calls: list[ToolCallLog]
    iterations: int


# === Endpoint ===
@router.post("/chat", response_model=ChatResponse)
def ai_chat(
    body: ChatRequest,
    current_user: dict = Depends(_get_current_user_lazy),
):
    """
    Основной эндпоинт AI-чата.
    Запускает agent loop с tools доступными текущей роли.
    """
    logger.info(
        f"[ai/chat] user={current_user['name']} ({current_user['role']}) "
        f"msg={body.message[:80]!r}"
    )

    history = (
        [{"role": m.role, "content": m.content} for m in body.history]
        if body.history else None
    )

    # db_conn в ctx не передаём — tools используют db_cursor() напрямую
    result = run_agent(
        user_message=body.message,
        current_user=current_user,
        db_conn=None,
        history=history,
    )

    logger.info(
        f"[ai/chat] done iters={result['iterations']} "
        f"tools={[tc['name'] for tc in result['tool_calls']]}"
    )

    return ChatResponse(**result)
