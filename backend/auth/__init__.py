import os
import logging

from fastapi import HTTPException, Request

logger = logging.getLogger("HHB_B2B")

B2B_ADMIN_TOKEN = os.getenv("B2B_ADMIN_TOKEN", "hhb_b2b_secret_token_2026")

# Optional allowlist. Comma-separated, e.g. "203.0.113.10,203.0.113.11"
B2B_ALLOWED_IPS = os.getenv("B2B_ALLOWED_IPS", "").strip()


def _extract_client_ip(request: Request) -> str:
    """
    Prefer proxy headers if present.
    Note: correctness depends on trusted proxy configuration.
    """
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()

    x_real_ip = request.headers.get("X-Real-IP")
    if x_real_ip:
        return x_real_ip.strip()

    return request.client.host if request.client else "unknown"


def verify_b2b_token(request: Request):
    auth_header = request.headers.get("Authorization") or request.headers.get("X-API-Key")

    token = None
    if auth_header:
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
        else:
            token = auth_header

    if token != B2B_ADMIN_TOKEN:
        logger.warning(
            f"[Auth Failed] Неавторизованный запрос к {request.url.path} "
            f"с IP {_extract_client_ip(request)}"
        )
        raise HTTPException(
            status_code=401,
            detail="Unauthorized. Неверный или отсутствующий API-токен авторизации B2B.",
        )

    if B2B_ALLOWED_IPS:
        allowed = {ip.strip() for ip in B2B_ALLOWED_IPS.split(",") if ip.strip()}
        client_ip = _extract_client_ip(request)
        if client_ip not in allowed:
            logger.warning(
                f"[Auth Failed] B2B token OK, но IP не в allowlist. path={request.url.path} ip={client_ip}"
            )
            raise HTTPException(
                status_code=401,
                detail="Unauthorized. Доступ запрещен по IP.",
            )

    return token
