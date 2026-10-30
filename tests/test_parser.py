import pytest

import jw_feed
from jw_feed import Article, FeedError, article_text_from_html, parse_page

# HTML sintético no formato que o parser espera (data, REGIÃO em maiúsculas, título, resumo).
# Não é uma cópia do site real: se o site mudar, atualize esta fixture com uma página salva.
PAGE = """
<html><body>
<nav><h2><a href="/pt/noticias/">Notícias</a></h2></nav>
<h3><a href="/pt/noticias/por-regiao/brasil/">Filtro: Brasil</a></h3>
<ul>
  <li class="card">
    <span>2026-10-01</span><span>NOTÍCIAS MUNDIAIS</span>
    <h3><a href="/pt/noticias/por-regiao/mundial/primeira-noticia/">Primeira notícia importante</a></h3>
    <p>Resumo da primeira.</p><a href="/pt/noticias/por-regiao/mundial/primeira-noticia/">Ler mais</a>
  </li>
  <li class="card">
    <a href="/pt/noticias/por-regiao/coreia-do-sul/segunda-noticia/">
      <time datetime="2026-09-28">28 de setembro de 2026</time>
      <h3>Segunda notícia sobre a Coreia</h3>
      <p>Resumo da segunda.</p>
    </a>
  </li>
  <li class="card">
    <h2><a href="/pt/noticias/por-regiao/brasil/terceira-sem-data/">Terceira notícia sem data</a></h2>
  </li>
  <li class="card">
    <span>5 de março de 2026</span>
    <h3><a href="/pt/noticias/por-regiao/portugal/quarta-data-por-extenso/">Quarta notícia com data por extenso</a></h3>
  </li>
</ul>
</body></html>
"""


def by_slug(articles):
    return {a.url.rstrip("/").rsplit("/", 1)[1]: a for a in articles}


def test_only_real_articles_are_returned():
    articles = parse_page(PAGE)
    assert len(articles) == 4  # o menu e a listagem por região ficam de fora
    assert all("por-regiao" in a.url for a in articles)


def test_cards_do_not_borrow_data_from_neighbours():
    a = by_slug(parse_page(PAGE))
    assert a["primeira-noticia"].published == "2026-10-01"
    assert a["primeira-noticia"].summary == "Resumo da primeira."  # sem "Ler mais", data ou região
    assert a["segunda-noticia"].published == "2026-09-28"
    assert a["segunda-noticia"].summary == "Resumo da segunda."
    assert a["terceira-sem-data"].published is None  # não herdou a data do vizinho
    assert a["terceira-sem-data"].summary == ""
    assert a["quarta-data-por-extenso"].published == "2026-03-05"


def test_regions_are_readable():
    a = by_slug(parse_page(PAGE))
    assert a["primeira-noticia"].region == "Notícias Mundiais"
    assert a["segunda-noticia"].region == "Coreia do Sul"
    assert a["quarta-data-por-extenso"].region == "Portugal"


def test_absolute_urls_and_language_variant():
    html = '<h3><a href="/pt-pt/noticias/regiao/portugal/uma-noticia/">Uma notícia de Portugal</a></h3>'
    assert parse_page(html, "https://www.jw.org/pt-pt/noticias/")[0].region == "Portugal"
    assert parse_page(html, "https://www.jw.org/pt/noticias/", lang="pt") == []  # outra variante


def test_fetch_all_raises_when_nothing_is_recognized(monkeypatch):
    monkeypatch.setattr(jw_feed, "fetch_page", lambda page, lang="pt": ([], "x"))
    with pytest.raises(FeedError):
        jw_feed.fetch_all(max_pages=3)


def test_fetch_all_stops_on_repeated_page(monkeypatch):
    page = [Article(f"Título número {i}", f"https://www.jw.org/pt/noticias/n{i}/") for i in range(15)]
    calls = []
    monkeypatch.setattr(jw_feed, "fetch_page", lambda p, lang="pt": (calls.append(p) or page, "x"))
    result = jw_feed.fetch_all(max_pages=10)
    assert len(result) == 15 and calls == [1, 2]  # a 2ª página repetiu a 1ª: para


def test_article_text_extraction():
    html = """<html><body><nav><p>Menu</p></nav><div id="article">
      <h1>Título da notícia</h1><p>Primeiro parágrafo com texto suficiente.</p>
      <ul><li>Item da lista com texto</li></ul><script>alert(1)</script>
      <p>Segundo parágrafo.</p></div><footer><p>Rodapé</p></footer></body></html>"""
    text = article_text_from_html(html)
    assert "Menu" not in text and "Rodapé" not in text and "alert" not in text
    assert text.splitlines()[0] == "Título da notícia"
    assert "Segundo parágrafo." in text


def test_fetch_article_text_rejects_other_domains():
    with pytest.raises(FeedError):
        jw_feed.fetch_article_text("https://example.com/noticia")
