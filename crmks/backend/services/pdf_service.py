from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Optional

import redis
from playwright.sync_api import sync_playwright


REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
PDF_TTL_SECONDS = int(os.getenv("PDF_TTL_SECONDS", "3600"))  # 1h by default


@dataclass(frozen=True)
class PdfPaths:
    output_path: str


_browser = None
_playwright = None
_browser_lock = threading.Lock()


_redis_client = None
_redis_lock = threading.Lock()


def _get_output_path(proposal_id: int) -> str:
    if os.name != "nt":
        return f"/tmp/kp_{proposal_id}.pdf"
    return f"C:/Windows/Temp/kp_{proposal_id}.pdf"


def _get_url(base_url: str, proposal_id: int) -> str:
    base = base_url.rstrip("/")
    return f"{base}/kp/{proposal_id}"


def _get_redis() -> redis.Redis:
    global _redis_client
    with _redis_lock:
        if _redis_client is None:
            # decode_responses=True => store/get strings
            _redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        return _redis_client


def _pdf_result_key(proposal_id: int) -> str:
    return f"pdf:{proposal_id}"


def _pdf_job_key(proposal_id: int) -> str:
    return f"pdf_job:{proposal_id}"


def set_pdf_job_id(proposal_id: int, job_id: int) -> None:
    r = _get_redis()
    r.setex(_pdf_job_key(proposal_id), PDF_TTL_SECONDS, str(job_id))


def get_pdf_job_id(proposal_id: int) -> Optional[int]:
    r = _get_redis()
    raw = r.get(_pdf_job_key(proposal_id))
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def store_pdf_result(proposal_id: int, path: str) -> None:
    r = _get_redis()
    # store only the path; TTL invalidates results after 1h
    r.setex(_pdf_result_key(proposal_id), PDF_TTL_SECONDS, path)


def get_pdf_result_path(proposal_id: int) -> Optional[str]:
    r = _get_redis()
    raw = r.get(_pdf_result_key(proposal_id))
    return raw


def _get_browser():
    global _browser, _playwright
    with _browser_lock:
        if _browser is None:
            _playwright = sync_playwright().start()
            _browser = _playwright.chromium.launch(headless=True)
        return _browser


def ensure_pdf_browser_started() -> None:
    # explicit name for clarity: called by queue worker start
    _get_browser()


def render_pdf(base_url: str, proposal_id: int, output_path: str) -> None:
    browser = _get_browser()

    url = _get_url(base_url=base_url, proposal_id=proposal_id)

    page = browser.new_page()
    try:
        page.goto(url, wait_until="networkidle", timeout=30000)
        page.pdf(
            path=output_path,
            format="A4",
            print_background=True,
            margin={"top": "20px", "right": "20px", "bottom": "20px", "left": "20px"},
        )
    finally:
        page.close()


def generate_pdf_and_store(base_url: str, proposal_id: int) -> str:
    paths = PdfPaths(output_path=_get_output_path(proposal_id))
    render_pdf(base_url=base_url, proposal_id=proposal_id, output_path=paths.output_path)
    store_pdf_result(proposal_id=proposal_id, path=paths.output_path)
    return paths.output_path
