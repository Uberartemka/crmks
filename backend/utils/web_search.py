from __future__ import annotations

import json
import os
import re
import socket
import urllib.parse
import urllib.request
from typing import List, Optional, Tuple

from db import _use_pg, get_db, q


SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")


def _extract_urls_from_ddg(html: str) -> List[str]:
    """Extract real URLs from DuckDuckGo HTML results."""
    urls: List[str] = []
    # DuckDuckGo wraps links in redirects: //duckduckgo.com/l/?uddg=URL or uddg= in middle
    for match in re.finditer(r"uddg=([^\"'&\s]+)", html):
        try:
            url = urllib.parse.unquote(match.group(1))
            if url.startswith("http") and "duckduckgo.com" not in url:
                urls.append(url)
        except Exception:
            pass

    # Fallback: try standard href links
    if not urls:
        for match in re.finditer(r'href=["\'](https?://[^"\'<>\s]+)', html):
            url = match.group(1)
            if "duckduckgo.com" not in url and "w3.org" not in url and "javascript:" not in url:
                urls.append(url)

    # Deduplicate
    seen = set()
    unique: List[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique[:3]


def _extract_urls_from_ddg_lite(html: str) -> List[str]:
    """Extract real URLs from DuckDuckGo Lite HTML results."""
    urls: List[str] = []

    # DDG Lite uses plain links like <a href="http://example.com" ...>
    for match in re.finditer(
        r'<a[^>]*href=["\'](https?://[^"\'<>\s]+)["\'][^>]*class=["\'][^"\']*result',
        html,
        re.IGNORECASE,
    ):
        url = match.group(1)
        if "duckduckgo.com" not in url and "w3.org" not in url:
            urls.append(url)

    # Fallback: any http link in result rows
    if not urls:
        for match in re.finditer(
            r"<td[^>]*>.*?<a[^>]*href=['\"](https?://[^\"\'<>\s]+)['\"]",
            html,
            re.DOTALL,
        ):
            url = match.group(1)
            if "duckduckgo.com" not in url and "w3.org" not in url and "javascript:" not in url:
                urls.append(url)

    # Fallback 2: any direct link
    if not urls:
        for match in re.finditer(r'href=["\'](https?://[^"\'<>\s]+)', html):
            url = match.group(1)
            if "duckduckgo.com" not in url and "w3.org" not in url and "javascript:" not in url:
                urls.append(url)

    # Deduplicate
    seen = set()
    unique: List[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique[:3]


def _extract_urls_from_bing(html: str) -> List[str]:
    """Extract real URLs from Bing HTML results."""
    urls: List[str] = []

    # Bing uses class="b_algo" with h2 > a href
    for match in re.finditer(r"<h2[^>]*>\s*<a[^>]*href=['\"](https?://[^\"\'<>\s]+)", html):
        url = match.group(1)
        if "bing.com" not in url and "microsoft.com" not in url and "w3.org" not in url:
            urls.append(url)

    # Fallback all links
    if not urls:
        for match in re.finditer(r'href=["\'](https?://[^"\'<>\s]+)', html):
            url = match.group(1)
            if (
                "bing.com" not in url
                and "microsoft.com" not in url
                and "w3.org" not in url
                and "javascript:" not in url
            ):
                urls.append(url)

    # Deduplicate
    seen = set()
    unique: List[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique[:3]


def _scrape_emails_from_page(url: str) -> Optional[str]:
    """Fetch a page and extract the first valid email. Fast, ~3s timeout."""
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(3)

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            html = response.read().decode("utf-8", errors="ignore")
            emails = re.findall(
                r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", html
            )

            for email in emails:
                email_lower = email.lower()
                if any(
                    x in email_lower
                    for x in [
                        "noreply",
                        "no-reply",
                        "support@",
                        "info@",
                        "admin@",
                        "help@",
                        "marketing@",
                        "sales@",
                        "abuse@",
                        "postmaster@",
                        "webmaster@",
                        "example.com",
                        "test.com",
                        "domain.com",
                        "yourcompany.com",
                    ]
                ):
                    continue
                if email_lower.endswith(
                    (".png", ".jpg", ".gif", ".svg", ".webp", ".css", ".js")
                ):
                    continue
                return email
    except Exception:
        return None
    finally:
        socket.setdefaulttimeout(old_timeout)


def _search_serpapi_email(query: str) -> Optional[str]:
    """Search via SerpApi Google, scrape top results for email."""
    if not SERPAPI_KEY:
        return None

    term = f"{query} email контакты"
    try:
        params = urllib.parse.urlencode(
            {
                "engine": "google",
                "q": term,
                "api_key": SERPAPI_KEY,
                "gl": "ru",
                "hl": "ru",
                "num": "5",
            }
        )
        req = urllib.request.Request(
            f"https://serpapi.com/search?{params}",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))
            organic = data.get("organic_results", [])
            for result in organic[:2]:
                url = result.get("link")
                if url:
                    email = _scrape_emails_from_page(url)
                    if email:
                        return email
    except Exception:
        return None

    return None


def _search_web_email(query: str) -> Optional[str]:
    """Fast web search: SerpApi -> DDG Lite -> Bing. Max ~10s total."""
    term = f"{query} email контакты"

    # 1) SerpApi (Google via API)
    try:
        email = _search_serpapi_email(query)
        if email:
            return email
    except Exception:
        pass

    # 2) DuckDuckGo Lite (simpler HTML, no JS)
    try:
        data = urllib.parse.urlencode({"q": term, "kl": "ru-ru"}).encode("utf-8")
        req = urllib.request.Request(
            "https://lite.duckduckgo.com/lite/",
            data=data,
            method="POST",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        with urllib.request.urlopen(req, timeout=4) as response:
            html = response.read().decode("utf-8", errors="ignore")
            urls = _extract_urls_from_ddg_lite(html)[:2]
            for url in urls:
                email = _scrape_emails_from_page(url)
                if email:
                    return email
    except Exception:
        pass

    # 3) Bing
    try:
        search_query = urllib.parse.quote(term)
        req = urllib.request.Request(
            f"https://www.bing.com/search?q={search_query}&setmkt=ru-RU",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=4) as response:
            html = response.read().decode("utf-8", errors="ignore")
            urls = _extract_urls_from_bing(html)[:2]
            for url in urls:
                email = _scrape_emails_from_page(url)
                if email:
                    return email
    except Exception:
        pass

    return None


def _search_email_from_db(company_query: str) -> Tuple[Optional[str], Optional[str]]:
    """Search email by company name across clients and leads."""
    conn = get_db()
    cursor = conn.cursor()

    email: Optional[str] = None
    source: Optional[str] = None

    # 1) Search existing clients
    if _use_pg:
        cursor.execute(
            "SELECT email, name FROM clients WHERE name ILIKE %s LIMIT 1",
            ("%" + company_query + "%",),
        )
    else:
        cursor.execute(
            "SELECT email, name FROM clients WHERE name LIKE ? LIMIT 1",
            ("%" + company_query + "%",),
        )

    row = cursor.fetchone()
    if row and row[0]:
        email = row[0]
        source = "client"

    # 2) Search leads (contacts field may contain email)
    if not email:
        if _use_pg:
            cursor.execute(
                "SELECT contacts, name FROM parsed_leads WHERE name ILIKE %s LIMIT 1",
                ("%" + company_query + "%",),
            )
        else:
            cursor.execute(
                "SELECT contacts, name FROM parsed_leads WHERE name LIKE ? LIMIT 1",
                ("%" + company_query + "%",),
            )

        row = cursor.fetchone()
        if row and row[0]:
            found = re.search(
                r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
                row[0],
            )
            if found:
                email = found.group(0)
                source = "lead"

    conn.close()
    return email, source
