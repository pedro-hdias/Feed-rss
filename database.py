from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path

from appinfo import data_dir
from jw_feed import Article
from textutil import format_region

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = 2

SCHEMA = """CREATE TABLE IF NOT EXISTS articles (
    url TEXT PRIMARY KEY, title TEXT NOT NULL, published TEXT, region TEXT,
    summary TEXT, is_read INTEGER NOT NULL DEFAULT 0,
    first_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    body TEXT)"""
META_SCHEMA = "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"

UPSERT = """INSERT INTO articles(url,title,published,region,summary)
    VALUES(?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET title=excluded.title,
    published=excluded.published, region=excluded.region, summary=excluded.summary,
    last_seen=CURRENT_TIMESTAMP"""

LIST_COLUMNS = "url,title,published,region,summary,is_read,first_seen,last_seen"


def default_db() -> Path:
    return data_dir() / "noticias.sqlite3"


def _like(term: str) -> str:
    """Escapa %, _ e \\ para que a busca seja literal."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class NewsDatabase:
    """Acesso SQLite seguro para várias threads.

    Cada thread recebe a própria conexão: compartilhar uma única conexão entre
    a interface e a thread de sincronização misturava transações e causava erros
    de "database is locked". O modo WAL deixa a interface ler enquanto a
    sincronização grava.
    """

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else default_db()
        self._local = threading.local()
        conn = self.conn
        conn.execute(SCHEMA)
        conn.execute(META_SCHEMA)
        self._migrate(conn)
        conn.commit()

    def _migrate(self, conn: sqlite3.Connection) -> None:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        columns = {row[1] for row in conn.execute("PRAGMA table_info(articles)")}
        if "body" not in columns:
            conn.execute("ALTER TABLE articles ADD COLUMN body TEXT")
        if version < 2:
            # Regiões antigas vinham em MAIÚSCULAS; leitores de tela as soletram.
            for (region,) in conn.execute("SELECT DISTINCT region FROM articles WHERE region <> ''").fetchall():
                fixed = format_region(region)
                if fixed != region:
                    conn.execute("UPDATE articles SET region=? WHERE region=?", (fixed, region))
        if version < SCHEMA_VERSION:
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @property
    def conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=30)
            conn.row_factory = sqlite3.Row
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
            except sqlite3.DatabaseError:
                LOGGER.exception("Não foi possível ativar o modo WAL")
            self._local.conn = conn
        return conn

    def close_thread(self) -> None:
        """Fecha a conexão da thread atual (chamar ao fim de threads de trabalho)."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            self._local.conn = None
            try:
                conn.close()
            except sqlite3.Error:
                LOGGER.debug("Falha ao fechar conexão", exc_info=True)

    # -- gravação ----------------------------------------------------------
    def upsert(self, article: Article) -> bool:
        return self.upsert_many([article]) > 0

    def upsert_many(self, articles: list[Article]) -> int:
        """Grava o lote numa única transação e devolve quantos eram novos."""
        conn = self.conn
        new_count = 0
        with conn:  # commit no sucesso, rollback se algo falhar
            for a in articles:
                existing = conn.execute("SELECT 1 FROM articles WHERE url = ?", (a.url,)).fetchone()
                conn.execute(UPSERT, (a.url, a.title, a.published, format_region(a.region), a.summary))
                if existing is None:
                    new_count += 1
        return new_count

    def set_read(self, url, value=True):
        with self.conn:
            self.conn.execute("UPDATE articles SET is_read=? WHERE url=?", (int(value), url))

    def mark_all_read(self):
        with self.conn:
            self.conn.execute("UPDATE articles SET is_read=1")

    def mark_region_read(self, region: str) -> int:
        with self.conn:
            return self.conn.execute("UPDATE articles SET is_read=1 WHERE region=? AND is_read=0", (region,)).rowcount

    def set_body(self, url: str, text: str) -> None:
        with self.conn:
            self.conn.execute("UPDATE articles SET body=? WHERE url=?", (text, url))

    def prune(self, days: int = 365) -> int:
        """Remove notícias lidas que não aparecem no site há muito tempo."""
        with self.conn:
            return self.conn.execute(
                "DELETE FROM articles WHERE is_read=1 AND last_seen < datetime('now', ?)", (f"-{int(days)} days",)).rowcount

    def set_meta(self, key: str, value: str) -> None:
        with self.conn:
            self.conn.execute("INSERT INTO meta(key,value) VALUES(?,?) "
                              "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    # -- leitura -----------------------------------------------------------
    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def get_body(self, url: str) -> str | None:
        row = self.conn.execute("SELECT body FROM articles WHERE url=?", (url,)).fetchone()
        return row[0] if row and row[0] else None

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]

    def unread_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM articles WHERE is_read = 0").fetchone()[0]

    def regions(self):
        return [r[0] for r in self.conn.execute(
            "SELECT DISTINCT region FROM articles WHERE region IS NOT NULL AND region <> '' ORDER BY region")]

    def region_counts(self):
        """[(região, total, não_lidas)] em ordem alfabética."""
        rows = self.conn.execute(
            "SELECT region, COUNT(*), SUM(CASE WHEN is_read=0 THEN 1 ELSE 0 END) FROM articles "
            "WHERE region IS NOT NULL AND region <> '' GROUP BY region ORDER BY region").fetchall()
        return [(r[0], r[1], r[2] or 0) for r in rows]

    def list(self, search="", region="Todas", status="Todas", sort="Mais recentes"):
        clauses, args = [], []
        if search:
            clauses.append("(title LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\')")
            args += [_like(search), _like(search)]
        if region != "Todas":
            clauses.append("region = ?")
            args.append(region)
        if status == "Não lidas":
            clauses.append("is_read = 0")
        if status == "Lidas":
            clauses.append("is_read = 1")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        recent = "CASE WHEN published IS NULL OR published = '' THEN 0 ELSE 1 END DESC, published DESC, first_seen DESC"
        order = {
            "Mais recentes": recent,
            "Mais antigas": "CASE WHEN published IS NULL OR published = '' THEN 1 ELSE 0 END ASC, published ASC, first_seen ASC",
            "Não lidas primeiro": "is_read ASC, CASE WHEN published IS NULL OR published = '' THEN 0 ELSE 1 END DESC, published DESC",
            "Título": "lower(title) ASC",
        }.get(sort, recent)
        return self.conn.execute(f"SELECT {LIST_COLUMNS} FROM articles" + where + " ORDER BY " + order, args).fetchall()
