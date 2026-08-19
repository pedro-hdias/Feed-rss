from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from jw_feed import Article


def default_db() -> Path:
    root = Path(os.environ.get("APPDATA", Path.home())) / "JWNoticiasFeed"
    root.mkdir(parents=True, exist_ok=True)
    return root / "noticias.sqlite3"


class NewsDatabase:
    def __init__(self, path: Path | None = None):
        self.path = path or default_db()
        # A sincronização ocorre em uma thread de trabalho, enquanto a UI
        # consulta a mesma base na thread principal.
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""CREATE TABLE IF NOT EXISTS articles (
            url TEXT PRIMARY KEY, title TEXT NOT NULL, published TEXT, region TEXT,
            summary TEXT, is_read INTEGER NOT NULL DEFAULT 0, first_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        self.conn.commit()

    def upsert(self, article: Article) -> bool:
        existing = self.conn.execute("SELECT 1 FROM articles WHERE url = ?", (article.url,)).fetchone()
        self.conn.execute("""INSERT INTO articles(url,title,published,region,summary)
            VALUES(?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET title=excluded.title,
            published=excluded.published, region=excluded.region, summary=excluded.summary,
            last_seen=CURRENT_TIMESTAMP""", (article.url, article.title, article.published, article.region, article.summary))
        return existing is None

    def upsert_many(self, articles: list[Article]) -> int:
        new_count = 0
        for article in articles:
            new_count += int(self.upsert(article))
        self.conn.commit()
        return new_count

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]

    def unread_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM articles WHERE is_read = 0").fetchone()[0]

    def list(self, search="", region="Todas", status="Todas", sort="Mais recentes"):
        clauses, args = [], []
        if search:
            clauses.append("(title LIKE ? OR summary LIKE ?)"); args += [f"%{search}%", f"%{search}%"]
        if region != "Todas": clauses.append("region = ?"); args.append(region)
        if status == "Não lidas": clauses.append("is_read = 0")
        if status == "Lidas": clauses.append("is_read = 1")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        order = {
            "Mais recentes": "CASE WHEN published IS NULL OR published = '' THEN 0 ELSE 1 END DESC, published DESC, first_seen DESC",
            "Mais antigas": "CASE WHEN published IS NULL OR published = '' THEN 1 ELSE 0 END ASC, published ASC, first_seen ASC",
            "Não lidas primeiro": "is_read ASC, CASE WHEN published IS NULL OR published = '' THEN 0 ELSE 1 END DESC, published DESC",
            "Título": "lower(title) ASC",
        }.get(sort, "CASE WHEN published IS NULL OR published = '' THEN 0 ELSE 1 END DESC, published DESC, first_seen DESC")
        return self.conn.execute("SELECT * FROM articles" + where + " ORDER BY " + order, args).fetchall()

    def set_read(self, url, value=True):
        self.conn.execute("UPDATE articles SET is_read=? WHERE url=?", (int(value), url)); self.conn.commit()

    def mark_all_read(self):
        self.conn.execute("UPDATE articles SET is_read=1"); self.conn.commit()

    def regions(self):
        return [r[0] for r in self.conn.execute("SELECT DISTINCT region FROM articles WHERE region <> '' ORDER BY region")]
