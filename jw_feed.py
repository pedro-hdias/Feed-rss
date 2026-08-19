from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from datetime import date
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.jw.org/pt/noticias/"
LOGGER = logging.getLogger(__name__)


@dataclass
class Article:
    title: str
    url: str
    published: str | None = None
    region: str = ""
    summary: str = ""


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _region_from_url(url: str) -> str:
    """Obtém a região do caminho /por-regiao/<região>/ da notícia."""
    parts = [unquote(part).strip().lower() for part in urlparse(url).path.split("/") if part]
    try:
        index = parts.index("por-regiao")
        slug = parts[index + 1]
    except (ValueError, IndexError):
        return ""
    known = {
        "mundial": "NOTÍCIAS MUNDIAIS",
        "russia": "RÚSSIA",
        "ucrania": "UCRÂNIA",
        "coreia-do-sul": "COREIA DO SUL",
        "alemanha": "ALEMANHA",
        "polonia": "POLÔNIA",
        "letonia": "LETÔNIA",
    }
    return known.get(slug, slug.replace("-", " ").upper())


def parse_page(html: str, page_url: str = BASE_URL) -> list[Article]:
    """Extrai os cards sem depender de classes CSS frágeis."""
    soup = BeautifulSoup(html, "html.parser")
    result: list[Article] = []
    seen: set[str] = set()
    for heading in soup.select("h2, h3"):
        link = heading.find("a", href=True) or heading.find_parent("a", href=True)
        title = _clean(heading.get_text(" ", strip=True))
        if not link or not title or len(title) < 5:
            continue
        url = urljoin(page_url, link.get("href", ""))
        if "/pt/noticias/" not in url or url.rstrip("/") == BASE_URL.rstrip("/") or url in seen:
            continue
        container = heading
        for _ in range(4):
            if container.parent:
                container = container.parent
        text = _clean(container.get_text(" ", strip=True))
        iso = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
        published = iso.group(1) if iso else None
        region = _region_from_url(url)
        summary = ""
        if published:
            tail = text[iso.end():].strip()
            summary = tail[:500]
        seen.add(url)
        result.append(Article(title, url, published, region, summary))
    return result


def fetch_page(page: int = 1, timeout: int = 30) -> tuple[list[Article], str | None]:
    # O JW.ORG pagina por deslocamento de 15 itens: ?start=15, ?start=30...
    url = BASE_URL if page == 1 else urljoin(BASE_URL, f"?start={(page - 1) * 15}")
    LOGGER.info("Baixando página %s: %s", page, url)
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "JWNoticiasFeed/0.1"})
    response.raise_for_status()
    articles = parse_page(response.text, response.url)
    LOGGER.info("Página %s retornou %s artigos", page, len(articles))
    return articles, response.url


def fetch_all(max_pages: int = 10, progress=None, on_batch=None) -> list[Article]:
    all_articles: list[Article] = []
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        articles, _ = fetch_page(page)
        for article in articles:
            if article.url not in seen:
                seen.add(article.url)
                all_articles.append(article)
        if on_batch and articles:
            on_batch(articles)
        if progress:
            progress(page, len(all_articles))
        if len(articles) < 10:
            break
    return all_articles
