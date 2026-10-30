from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from textutil import format_region
from version import __version__

HOST = "https://www.jw.org"
DEFAULT_LANG = "pt"
# Variantes do português no site. As rotas de pt-pt e pt-ao seguem o mesmo
# padrão de /pt/ pelo que se vê nas páginas públicas, mas não foram testadas.
SITE_LANGS = {"pt": "Português (Brasil)", "pt-pt": "Português (Portugal)", "pt-ao": "Português (Angola)"}
BASE_URL = f"{HOST}/{DEFAULT_LANG}/noticias/"
LOGGER = logging.getLogger(__name__)

REGION_SEGMENTS = {"por-regiao", "regiao", "area"}
IGNORED_SEGMENTS = {"pesquisa", "busca"}
NOISE_TEXTS = {"ler mais", "leia mais", "saiba mais", "ver mais"}

KNOWN_REGIONS = {
    "mundial": "Notícias Mundiais", "global": "Notícias Mundiais",
    "russia": "Rússia", "ucrania": "Ucrânia", "coreia-do-sul": "Coreia do Sul",
    "alemanha": "Alemanha", "polonia": "Polônia", "letonia": "Letônia",
    "brasil": "Brasil", "portugal": "Portugal", "angola": "Angola", "mocambique": "Moçambique",
    "estados-unidos": "Estados Unidos", "canada": "Canadá", "mexico": "México", "argentina": "Argentina",
    "colombia": "Colômbia", "chile": "Chile", "peru": "Peru", "franca": "França", "italia": "Itália",
    "espanha": "Espanha", "reino-unido": "Reino Unido", "japao": "Japão", "india": "Índia",
    "africa-do-sul": "África do Sul", "paraguai": "Paraguai", "uruguai": "Uruguai",
}

MONTHS = {"janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4, "maio": 5, "junho": 6,
          "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}
ISO_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
PT_DATE_RE = re.compile(r"\b(\d{1,2})\s+de\s+([A-Za-zçÇãÃ]+)\s+de\s+(20\d{2})\b", re.IGNORECASE)

_session: requests.Session | None = None
_session_lock = threading.Lock()


class FeedError(Exception):
    """Falha esperada de coleta (site mudou, página vazia, resposta inválida)."""


@dataclass
class Article:
    title: str
    url: str
    published: str | None = None
    region: str = ""
    summary: str = ""


def base_url(lang: str = DEFAULT_LANG) -> str:
    return f"{HOST}/{lang}/noticias/"


def _get_session() -> requests.Session:
    """Sessão reutilizável, com novas tentativas para falhas temporárias de rede."""
    global _session
    with _session_lock:
        if _session is None:
            session = requests.Session()
            retry = Retry(total=3, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504),
                          allowed_methods=("GET",), respect_retry_after_header=True)
            session.mount("https://", HTTPAdapter(max_retries=retry))
            session.mount("http://", HTTPAdapter(max_retries=retry))
            session.headers.update({"User-Agent": f"JWNoticiasFeed/{__version__}", "Accept-Language": "pt-BR,pt;q=0.9"})
            _session = session
        return _session


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _parse_date(text: str) -> str | None:
    m = ISO_RE.search(text or "")
    if m:
        return m.group(1)
    m = PT_DATE_RE.search(text or "")
    if m:
        month = MONTHS.get(m.group(2).lower())
        if month:
            return f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(1)):02d}"
    return None


def _path_parts(url: str) -> list[str]:
    return [unquote(part).strip().lower() for part in urlparse(url).path.split("/") if part]


def _classify(url: str, lang: str) -> tuple[bool, str]:
    """(é_notícia, slug_da_região). Páginas de listagem e de busca não são notícias."""
    parts = _path_parts(url)
    if len(parts) < 3 or parts[0] != lang or parts[1] != "noticias":
        return False, ""
    rest = parts[2:]
    if rest[0] in REGION_SEGMENTS:
        # /por-regiao/<região>/ é listagem; a notícia vem depois: /por-regiao/<região>/<artigo>/
        return (True, rest[1]) if len(rest) >= 3 else (False, "")
    if rest[0] in IGNORED_SEGMENTS:
        return False, ""
    return True, ""


def _region_from_url(url: str, lang: str = DEFAULT_LANG) -> str:
    """Obtém a região do caminho /por-regiao/<região>/ da notícia."""
    parts = _path_parts(url)
    for index, part in enumerate(parts):
        if part in REGION_SEGMENTS and index + 1 < len(parts):
            slug = parts[index + 1]
            return KNOWN_REGIONS.get(slug) or format_region(slug.replace("-", " "))
    return ""


def _lang_of(page_url: str, fallback: str) -> str:
    parts = _path_parts(page_url)
    return parts[0] if parts and parts[0] in SITE_LANGS else fallback


def _looks_like_region_label(text: str) -> bool:
    return text.isupper() and len(text) <= 40 and any(ch.isalpha() for ch in text)


def parse_page(html: str, page_url: str | None = None, lang: str = DEFAULT_LANG) -> list[Article]:
    """Extrai os cards sem depender de classes CSS frágeis.

    Para cada título que aponta para uma notícia, sobe na árvore até o maior
    elemento que ainda contém apenas esse link de notícia: esse é o card.
    Assim a data e o resumo nunca vêm emprestados de um card vizinho.
    """
    page_url = page_url or base_url(lang)
    lang = _lang_of(page_url, lang)
    soup = BeautifulSoup(html, "html.parser")

    def links_in(node) -> set[str]:
        found = set()
        for a in node.find_all("a", href=True):
            href = urljoin(page_url, a["href"]).split("#")[0]
            if _classify(href, lang)[0]:
                found.add(href)
        return found

    result: list[Article] = []
    seen: set[str] = set()
    for heading in soup.select("h2, h3"):
        link = heading.find("a", href=True) or heading.find_parent("a", href=True)
        title = _clean(heading.get_text(" ", strip=True))
        if not link or len(title) < 5:
            continue
        url = urljoin(page_url, link["href"]).split("#")[0]
        is_article, slug = _classify(url, lang)
        if not is_article or url in seen:
            continue

        container = heading
        while container.parent is not None and container.parent.name not in ("body", "html", "[document]"):
            parent = container.parent
            if links_in(parent) - {url} or len(parent.get_text(" ", strip=True)) > 2000:
                break
            container = parent

        strings = [s for s in (_clean(t) for t in container.stripped_strings) if s]
        published = None
        time_tag = container.find("time")
        if time_tag is not None:
            published = _parse_date(time_tag.get("datetime", "")) or _parse_date(time_tag.get_text(" "))
        if not published:
            published = _parse_date(" ".join(strings))

        region = _region_from_url(url, lang)
        label = next((s for s in strings if _looks_like_region_label(s)), "")
        if not region and label:
            region = format_region(label)

        summary_parts = [
            s for s in strings
            if s != title and s != label and s.lower() not in NOISE_TEXTS
            and not (len(s) <= 30 and _parse_date(s))
        ]
        summary = " ".join(summary_parts)[:500]
        seen.add(url)
        result.append(Article(title, url, published, region, summary))
    return result


def fetch_page(page: int = 1, lang: str = DEFAULT_LANG, timeout: tuple[int, int] = (10, 30)) -> tuple[list[Article], str]:
    # O JW.ORG pagina por deslocamento de 15 itens: ?start=15, ?start=30...
    root = base_url(lang)
    url = root if page == 1 else urljoin(root, f"?start={(page - 1) * 15}")
    LOGGER.info("Baixando página %s: %s", page, url)
    response = _get_session().get(url, timeout=timeout)
    response.raise_for_status()
    articles = parse_page(response.text, response.url, lang)
    LOGGER.info("Página %s retornou %s artigos", page, len(articles))
    return articles, response.url


def fetch_all(max_pages: int = 10, progress=None, on_batch=None, lang: str = DEFAULT_LANG) -> list[Article]:
    all_articles: list[Article] = []
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        articles, _ = fetch_page(page, lang)
        if page == 1 and not articles:
            raise FeedError("Nenhuma notícia foi reconhecida na página. O site pode ter mudado de formato.")
        fresh = [a for a in articles if a.url not in seen]
        if not fresh:
            break  # página repetida ou vazia: não adianta continuar
        for article in fresh:
            seen.add(article.url)
            all_articles.append(article)
        if on_batch:
            on_batch(articles)
        if progress:
            progress(page, len(all_articles))
        if len(articles) < 10:
            break
    return all_articles


_DROP_TAGS = ("script", "style", "nav", "header", "footer", "form", "aside", "noscript", "button", "svg")
_BLOCK_TAGS = ["h1", "h2", "h3", "h4", "p", "li", "blockquote"]


def article_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(_DROP_TAGS):
        tag.decompose()
    node = soup.select_one("#article") or soup.select_one("article") or soup.select_one("main") or soup.body or soup
    blocks: list[str] = []
    for el in node.find_all(_BLOCK_TAGS):
        if el.find(_BLOCK_TAGS):  # só os blocos "folha": evita texto duplicado
            continue
        text = _clean(el.get_text(" ", strip=True))
        if text and (not blocks or blocks[-1] != text):
            blocks.append(text)
    return "\n\n".join(blocks)


def fetch_article_text(url: str, timeout: tuple[int, int] = (10, 30)) -> str:
    """Baixa e limpa o texto completo de uma notícia (apenas jw.org)."""
    host = urlparse(url).netloc.lower()
    if not (host == "jw.org" or host.endswith(".jw.org")):
        raise FeedError("Só é possível baixar o texto de páginas do jw.org.")
    response = _get_session().get(url, timeout=timeout)
    response.raise_for_status()
    text = article_text_from_html(response.text)
    if len(text) < 40:
        raise FeedError("Não foi possível extrair o texto desta página.")
    return text
