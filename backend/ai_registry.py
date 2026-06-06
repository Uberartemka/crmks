"""
Реестр AI-tools с фильтрацией по ролям.

Использование:
    @tool(
        name="find_user",
        description="Найти сотрудника по имени или username",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Имя или часть имени"}
            },
            "required": ["query"]
        },
        roles=["admin", "manager", "employee"],
    )
    def find_user(ctx: dict, query: str) -> dict:
        # ctx содержит current_user (id, name, role) и db-коннекшн
        ...

В agent loop:
    tools_schema = get_tools_for_role("manager")  # → JSON-схема для Kimi
    result = execute_tool("find_user", {"query": "Иван"}, ctx)
"""
from typing import Callable, Any
import json
import logging

logger = logging.getLogger(__name__)

# Глобальный реестр: name → {fn, schema, roles}
_REGISTRY: dict[str, dict] = {}


def tool(
    name: str,
    description: str,
    parameters: dict,
    roles: list[str],
):
    """
    Декоратор регистрации tool'а.
    Функция получит дополнительный позиционный аргумент `ctx` —
    словарь с current_user, db-коннекшеном, request_id.
    """
    def decorator(fn: Callable):
        if name in _REGISTRY:
            logger.warning(f"Tool '{name}' уже зарегистрирован, пропускаю")
            return fn
        _REGISTRY[name] = {
            "fn": fn,
            "roles": set(roles),
            "schema": {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                },
            },
        }
        logger.info(f"Tool registered: {name} (roles: {roles})")
        return fn
    return decorator


def get_tools_for_role(role: str) -> list[dict]:
    """JSON-схема всех tools доступных этой роли — для передачи в Kimi."""
    return [
        entry["schema"]
        for entry in _REGISTRY.values()
        if role in entry["roles"]
    ]


def execute_tool(name: str, args: dict, ctx: dict) -> dict:
    """
    Выполнить tool с проверкой:
      1) существует ли
      2) разрешён ли текущей роли
      3) аргументы — dict
    Возвращает результат в виде dict (будет сериализован в JSON для Kimi).
    """
    if name not in _REGISTRY:
        return {"error": f"Unknown tool: {name}"}

    entry = _REGISTRY[name]
    user_role = ctx["current_user"]["role"]
    if user_role not in entry["roles"]:
        return {
            "error": f"Forbidden: role '{user_role}' cannot call '{name}'"
        }

    try:
        result = entry["fn"](ctx=ctx, **args)
        return result if isinstance(result, dict) else {"result": result}
    except TypeError as e:
        # Несовпадение аргументов — Kimi прислала лишнее/неполное
        return {"error": f"Invalid arguments for {name}: {e}"}
    except Exception as e:
        logger.exception(f"Tool {name} raised")
        return {"error": f"Tool execution failed: {type(e).__name__}: {e}"}


def list_all_tools() -> list[str]:
    """Для дебага: имена всех зарегистрированных tools."""
    return list(_REGISTRY.keys())
