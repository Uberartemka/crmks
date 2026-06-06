"""
Agent loop для Kimi с function calling.

Цикл:
  1. Шлём в Kimi messages + список доступных tools
  2. Kimi отвечает либо текстом (готов), либо tool_calls (нужно выполнить)
  3. Если tool_calls — выполняем каждый, добавляем результаты в messages, GOTO 1
  4. Если текст — возвращаем пользователю
  5. Защита: max 10 итераций, чтобы не зациклиться
"""
import json
import logging
from kimi_client import chat_completion
from ai_registry import get_tools_for_role, execute_tool
from ai_prompts import build_system_prompt

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 10


def run_agent(
    user_message: str,
    current_user: dict,
    db_conn=None,
    history: list | None = None,
) -> dict:
    """
    Запустить agent loop.

    Args:
        user_message: текст от пользователя
        current_user: {"id": int, "name": str, "role": "admin|manager|employee"}
        db_conn: psycopg2-коннекшн (или аналог), опционально
        history: предыдущие сообщения чата (опционально, для контекста)

    Returns:
        {
            "reply": str,           # финальный ответ юзеру
            "tool_calls": list,     # что было вызвано (для UI/логов)
            "iterations": int,      # сколько раз дёргали Kimi
        }
    """
    role = current_user["role"]
    tools_schema = get_tools_for_role(role)
    ctx = {"current_user": current_user, "db": db_conn}

    # Стартовый набор сообщений
    messages = [
        {"role": "system", "content": build_system_prompt(current_user)},
    ]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    tool_calls_log = []  # для возврата в UI: что именно вызывалось

    for iteration in range(1, MAX_ITERATIONS + 1):
        logger.info(f"[agent] iteration {iteration}, role={role}")
        choice = chat_completion(messages, tools=tools_schema)
        msg = choice.message

        # Kimi решила вызвать tools?
        if msg.tool_calls:
            # Кладём её "запрос" в историю — обязательно для протокола
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })

            # Выполняем каждый tool и кладём результат
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    tool_args = {}
                    logger.warning(
                        f"Kimi вернула невалидный JSON для {tool_name}: "
                        f"{tc.function.arguments!r}"
                    )

                logger.info(f"[agent] → tool {tool_name}({tool_args})")
                result = execute_tool(tool_name, tool_args, ctx)
                logger.info(f"[agent] ← {tool_name} returned {str(result)[:200]}")

                tool_calls_log.append({
                    "name": tool_name,
                    "args": tool_args,
                    "result": result,
                })

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })
            # Следующая итерация — Kimi увидит результаты
            continue

        # Kimi выдала финальный текст
        reply = msg.content or ""
        return {
            "reply": reply,
            "tool_calls": tool_calls_log,
            "iterations": iteration,
        }

    # Достигли лимита
    logger.warning(f"[agent] max iterations ({MAX_ITERATIONS}) reached")
    return {
        "reply": (
            "Я зациклилась, выполняя задачу. "
            "Попробуй переформулировать запрос конкретнее."
        ),
        "tool_calls": tool_calls_log,
        "iterations": MAX_ITERATIONS,
    }
