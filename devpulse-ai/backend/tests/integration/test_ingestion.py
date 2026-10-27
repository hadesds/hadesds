import pytest
from sqlalchemy import func, select

from devpulse.models import NewsItem, SourceReference
from devpulse.source_connectors.base import RawItem
from devpulse.news_ingestion.service import persist_item

from .conftest import add_story, make_source

pytestmark = pytest.mark.integration


def test_item_keeps_url_and_original_dates(db):
    src = make_source(db, "oficial")
    status, item = add_story(db, src, "Example 2.0 released with new CLI", "https://oficial.example.com/blog/example-2", hours_ago=30)
    assert status == "new"
    assert item.url.startswith("https://") and item.published_at is not None
    assert item.discovered_at > item.published_at  # descoberta ≠ publicação
    assert item.cluster_id is not None


def test_duplicate_by_url_across_sources_adds_reference(db):
    a, b = make_source(db, "oficial"), make_source(db, "portal", tier=4)
    _, first = add_story(db, a, "Example 2.0 released", "https://oficial.example.com/p?utm_source=x")
    status, second = add_story(db, b, "Example 2.0 is out", "https://www.oficial.example.com/p/")
    assert status == "duplicate" and second.id == first.id
    assert db.scalar(select(func.count(NewsItem.id))) == 1
    refs = db.scalars(select(SourceReference).where(SourceReference.news_item_id == first.id)).all()
    assert {r.source_id for r in refs} == {a.id, b.id}


def test_same_external_id_is_not_duplicated(db):
    src = make_source(db, "oficial")
    add_story(db, src, "Example 2.0 released", "https://oficial.example.com/p")
    raw = RawItem(external_id="https://oficial.example.com/p", url="https://oficial.example.com/other", title="x")
    status, _ = persist_item(db, src, raw)
    assert status == "duplicate"


def test_similar_titles_are_grouped_in_same_cluster(db):
    a, b = make_source(db, "oficial"), make_source(db, "portal", tier=4)
    _, x = add_story(db, a, "GitHub Copilot ganha agentes que abrem pull requests", "https://a.example.com/1")
    _, y = add_story(db, b, "Copilot do GitHub agora tem agentes que abrem pull requests", "https://b.example.com/2")
    _, z = add_story(db, b, "Kubernetes 1.36 traz novo agendador", "https://b.example.com/3")
    assert x.cluster_id == y.cluster_id != z.cluster_id
