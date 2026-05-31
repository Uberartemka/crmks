"""
Клиент Kimi (Moonshot AI) через OpenAI SDK.

Kimi полностью реализует протокол OpenAI Chat Completions, включая
tool_calls / tool_choice / function calling. Поэтому используем
официальный openai-клиент, просто подменяя base_url.

Документация: https://platform.moonshot.ai/docs/api/chat
"""
import os
from openai import OpenAI

KIMI_API_KEY = os.getenv("KIMI_API_KEY")
KIMI_BASE_URL = os.getenv("KIMI_BASE_URL", "https://api.moonshot.ai/v1")
KIMI_MODEL = os.getenv("KIMI_MODEL", "kimi-k2-0905-preview")

if not KIMI_API_KEY:
    raise RuntimeError(
        "KIMI_API_KEY не задан. Положи ключ в .env: KIMI_API_KEY=sk-..."
    )

# Один глобальный клиент. Тред-сейф, можно дергать из любого хендлера.
client = OpenAI(
    api_key=KIMI_API_KEY,
    base_url=KIMI_BASE_URL,
    timeout=60.0,
    max_retries=2,
)


def chat_completion(messages: list, tools: list | None = None, **kwargs):
    """
    Тонкая обёртка: дергает Kimi и возвращает первый choice.
    Все параметры (temperature, top_p, tool_choice) пробрасываются как есть.
    """
    response = client.chat.completions.create(
        model=KIMI_MODEL,
        messages=messages,
        tools=tools if tools else None,
        tool_choice="auto" if tools else None,
        temperature=kwargs.get("temperature", 0.3),
        **{k: v for k, v in kwargs.items() if k not in {"temperature"}},
    )
    return response.choices[0]
