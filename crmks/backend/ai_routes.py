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
    Проверка токена делается через Redis token_store (sync API),
    чтобы работало корректно при нескольких workers.
    """
    from token_store import get_token_sync, refresh_token_sync
    from db import db_cursor, q
    import logging

    logger = logging.getLogger("HHB_B2B")

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        logger.warning(f"[_get_current_user_lazy] Missing Bearer prefix. Header: {auth[:30]}")
        raise HTTPException(401, "Missing Bearer token")

    token = auth[7:]
    user_id = get_token_sync(token)
    if not user_id:
        logger.warning(f"[_get_current_user_lazy] Token not found/expired in Redis")
        raise HTTPException(401, "Invalid or expired token")

    # sliding expiry
    refresh_token_sync(token)

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
    id: str | None = None
    role: str = Field(..., description="user | assistant | system | tool")
    content: str
    tool_calls: list | None = None
    tool_call_id: str | None = None
    created_at: str | None = None


class ChatRequest(BaseModel):
    # Старый формат
    message: str | None = Field(default=None, max_length=4000)
    history: list[ChatMessage] | None = Field(
        default=None,
        description="Предыдущие сообщения чата (последние ~10)",
    )
    # Новый формат с фронтенда
    messages: list[ChatMessage] | None = Field(
        default=None,
        description="Полный список сообщений с фронтенда"
    )


class ToolCallLog(BaseModel):
    name: str
    args: dict
    result: dict


class FrontendMessage(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


class ChatResponse(BaseModel):
    reply: str
    message: FrontendMessage | None = None
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
    import uuid
    from datetime import datetime

    # Вытаскиваем сообщение и историю в зависимости от формата
    if body.messages:
        # Формат фронтенда (список всех сообщений)
        user_messages = [m for m in body.messages if m.role == "user"]
        if not user_messages:
            raise HTTPException(400, "No user message found in 'messages'")
        user_message = user_messages[-1].content
        
        # Строим историю из предыдущих сообщений (исключая последний запрос пользователя)
        history = []
        for m in body.messages[:-1]:
            history.append({"role": m.role, "content": m.content})
    else:
        # Классический формат
        if not body.message:
            raise HTTPException(400, "Field 'message' or 'messages' is required")
        user_message = body.message
        history = (
            [{"role": m.role, "content": m.content} for m in body.history]
            if body.history else None
        )

    logger.info(
        f"[ai/chat] user={current_user['name']} ({current_user['role']}) "
        f"msg={user_message[:80]!r}"
    )

    # db_conn в ctx не передаём — tools используют db_cursor() напрямую
    result = run_agent(
        user_message=user_message,
        current_user=current_user,
        db_conn=None,
        history=history,
    )

    reply_text = result.get("reply", "")

    # Формируем ответ, совместимый и с фронтендом, и с тестами
    response_data = {
        "reply": reply_text,
        "message": {
            "id": str(uuid.uuid4()),
            "role": "assistant",
            "content": reply_text,
            "created_at": datetime.now().isoformat()
        },
        "tool_calls": result.get("tool_calls", []),
        "iterations": result.get("iterations", 0)
    }

    logger.info(
        f"[ai/chat] done iters={result['iterations']} "
        f"tools={[tc['name'] for tc in result['tool_calls']]}"
    )

    return ChatResponse(**response_data)
