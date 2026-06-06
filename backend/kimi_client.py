"""
Клиент Kimi (Moonshot AI) через OpenAI SDK.

Kimi полностью реализует протокол OpenAI Chat Completions, включая
tool_calls / tool_choice / function calling. Поэтому используем
официальный openai-клиент, просто подменяя base_url.

Документация: https://platform.moonshot.ai/docs/api/chat
"""
import os
from openai import OpenAI

CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN") or os.getenv("CF_API_TOKEN")
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID") or os.getenv("CF_ACCOUNT_ID")

CLOUDFLARE_EMAIL = os.getenv("CLOUDFLARE_EMAIL") or os.getenv("CF_EMAIL")
# Если пользователь прописал глобальный ключ (начинается на cfk_ или 37-символьный hex)
CLOUDFLARE_GLOBAL_KEY = os.getenv("CLOUDFLARE_API_KEY") or os.getenv("CF_API_KEY") or os.getenv("CF_KEY")

use_cloudflare = False
headers = {}

if CLOUDFLARE_ACCOUNT_ID:
    if CLOUDFLARE_GLOBAL_KEY and CLOUDFLARE_EMAIL:
        # Авторизация по глобальному ключу (X-Auth-Key + X-Auth-Email)
        use_cloudflare = True
        KIMI_API_KEY = "dummy_key_for_openai_sdk"
        KIMI_BASE_URL = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/v1"
        headers = {
            "X-Auth-Key": CLOUDFLARE_GLOBAL_KEY,
            "X-Auth-Email": CLOUDFLARE_EMAIL,
        }
        default_model = os.getenv("CF_MODEL") or "@cf/moonshotai/kimi-k2.5"
    elif CLOUDFLARE_API_TOKEN:
        # Авторизация по API Токену (Bearer)
        use_cloudflare = True
        KIMI_API_KEY = CLOUDFLARE_API_TOKEN
        KIMI_BASE_URL = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/v1"
        default_model = os.getenv("CF_MODEL") or "@cf/moonshotai/kimi-k2.5"

if not use_cloudflare:
    # Прямое использование Moonshot AI (Kimi)
    KIMI_API_KEY = os.getenv("KIMI_API_KEY")
    KIMI_BASE_URL = os.getenv("KIMI_BASE_URL", "https://api.moonshot.ai/v1")
    default_model = "kimi-k2-0905-preview"

KIMI_MODEL = os.getenv("KIMI_MODEL", default_model)

if not KIMI_API_KEY:
    # Важно: не валимся при импорте модуля — это ломает запуск backend.
    # Ошибку поднимем при реальном вызове chat_completion().
    client = None
else:
    # Один глобальный клиент. Тред-сейф, можно дергать из любого хендлера.
    client = OpenAI(
        api_key=KIMI_API_KEY,
        base_url=KIMI_BASE_URL,
        default_headers=headers,
        timeout=60.0,
        max_retries=2,
    )


def chat_completion(messages: list, tools: list | None = None, **kwargs):
    """
    Тонкая обёртка: дергает Kimi и возвращает первый choice.
    Все параметры (temperature, top_p, tool_choice) пробрасываются как есть.
    """
    if client is None:
        raise RuntimeError(
            "KIMI не настроен: отсутствует KIMI_API_KEY (или Cloudflare ключи). "
            "Укажите KIMI_API_KEY в .env или настройте Cloudflare "
            "(CF_API_TOKEN и CF_ACCOUNT_ID или глобальные ключи CF_API_KEY и CF_EMAIL)."
        )

    response = client.chat.completions.create(
        model=KIMI_MODEL,
        messages=messages,
        tools=tools if tools else None,
        tool_choice="auto" if tools else None,
        temperature=kwargs.get("temperature", 0.3),
        **{k: v for k, v in kwargs.items() if k not in {"temperature"}},
    )
    return response.choices[0]
