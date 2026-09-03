from __future__ import annotations

from lorex.domain import ArticleHeader
from lorex.repository import JobRepository


def test_completed_articles_are_not_returned_as_pending() -> None:
    repository = JobRepository()
    articles = [
        ArticleHeader("<a1>", "one", 100),
        ArticleHeader("<a2>", "two", 200),
    ]
    repository.ensure_articles("job-1", articles)
    repository.mark_article_started("job-1", "<a1>", "primary")
    repository.mark_article_completed("job-1", "<a1>", "primary", 100)

    pending = repository.pending_articles("job-1", articles)

    assert [article.message_id for article in pending] == ["<a2>"]
