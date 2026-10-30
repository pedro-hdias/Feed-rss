import sqlite3
import threading

import pytest

from database import NewsDatabase
from jw_feed import Article


@pytest.fixture
def db(tmp_path):
    return NewsDatabase(tmp_path / "t.sqlite3")


def art(i, region="Brasil", published="2026-10-01", title=None):
    return Article(title or f"Título {i}", f"https://www.jw.org/pt/noticias/por-regiao/x/n{i}/", published, region, f"resumo {i}")


def test_upsert_counts_new_only(db):
    assert db.upsert_many([art(1), art(2)]) == 2
    assert db.upsert_many([art(1), art(2), art(3)]) == 1
    assert db.count() == 3 and db.unread_count() == 3


def test_read_state_and_filters(db):
    db.upsert_many([art(1), art(2, region="Portugal")])
    db.set_read(art(1).url, True)
    assert [r["title"] for r in db.list(status="Lidas")] == ["Título 1"]
    assert [r["title"] for r in db.list(status="Não lidas")] == ["Título 2"]
    assert [r["title"] for r in db.list(region="Portugal")] == ["Título 2"]
    assert db.mark_region_read("Portugal") == 1 and db.unread_count() == 0


def test_region_counts(db):
    db.upsert_many([art(1), art(2), art(3, region="Portugal")])
    db.set_read(art(1).url)
    assert db.region_counts() == [("Brasil", 2, 1), ("Portugal", 1, 1)]


def test_search_is_literal(db):
    db.upsert_many([art(1, title="Alta de 100% no mês"), art(2, title="Alta de 1000 no mês")])
    assert len(db.list(search="100%")) == 1
    assert len(db.list(search="_")) == 0


def test_regions_are_normalized_on_save(db):
    db.upsert_many([art(1, region="NOTÍCIAS MUNDIAIS")])
    assert db.regions() == ["Notícias Mundiais"]


def test_body_and_meta(db):
    db.upsert_many([art(1)])
    assert db.get_body(art(1).url) is None
    db.set_body(art(1).url, "texto completo")
    assert db.get_body(art(1).url) == "texto completo"
    assert db.get_meta("last_sync") is None
    db.set_meta("last_sync", "2026-10-30 10:00:00")
    db.set_meta("last_sync", "2026-10-30 11:00:00")
    assert db.get_meta("last_sync") == "2026-10-30 11:00:00"
    assert "body" not in db.list()[0].keys()  # a lista não carrega o texto completo


def test_prune_removes_only_old_read_articles(db):
    db.upsert_many([art(1), art(2), art(3)])
    db.set_read(art(1).url)
    db.set_read(art(2).url)
    with db.conn:
        db.conn.execute("UPDATE articles SET last_seen = datetime('now','-400 days') WHERE url IN (?,?)",
                        (art(1).url, art(3).url))
    assert db.prune(365) == 1  # só a nº 1: antiga E lida
    assert db.count() == 2


def test_migration_from_v1_database(tmp_path):
    path = tmp_path / "old.sqlite3"
    con = sqlite3.connect(path)
    con.execute("""CREATE TABLE articles (url TEXT PRIMARY KEY, title TEXT NOT NULL, published TEXT, region TEXT,
        summary TEXT, is_read INTEGER NOT NULL DEFAULT 0, first_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    con.execute("INSERT INTO articles(url,title,region) VALUES('u','Antiga','COREIA DO SUL')")
    con.commit()
    con.close()
    db = NewsDatabase(path)
    assert db.regions() == ["Coreia do Sul"]
    assert db.get_body("u") is None  # coluna body adicionada


def test_concurrent_reader_and_writer(db):
    articles = [art(i) for i in range(300)]
    result = {}

    def worker():
        try:
            result["new"] = db.upsert_many(articles)
        finally:
            db.close_thread()

    t = threading.Thread(target=worker)
    t.start()
    for _ in range(50):
        db.list()
        db.unread_count()
    t.join()
    assert result["new"] == 300 and db.count() == 300
