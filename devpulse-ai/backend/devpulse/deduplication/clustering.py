from __future__ import annotations

from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from devpulse.deduplication.normalize import title_tokens
from devpulse.deduplication.similarity import SAME_EVENT_THRESHOLD, title_similarity
from devpulse.models import NewsCluster, NewsItem
from devpulse.timeutil import utcnow

WINDOW_DAYS = 5


def topic_key(title: str) -> str:
    return " ".join(sorted(set(title_tokens(title)))[:12])[:200]


def find_cluster(session: Session, item: NewsItem) -> NewsCluster | None:
    ref = item.published_at or item.discovered_at or utcnow()
    lo, hi = ref - timedelta(days=WINDOW_DAYS), ref + timedelta(days=WINDOW_DAYS)
    candidates = session.scalars(
        select(NewsItem)
        .where(NewsItem.id != item.id, NewsItem.cluster_id.is_not(None))
        .where(
            or_(
                NewsItem.published_at.between(lo, hi),
                NewsItem.published_at.is_(None) & NewsItem.discovered_at.between(lo, hi),
            )
        )
    ).all()
    best, best_score = None, 0.0
    for c in candidates:
        if c.title_fingerprint == item.title_fingerprint:
            return c.cluster
        s = title_similarity(item.title, c.title)
        if s > best_score:
            best, best_score = c, s
    if best is not None and best_score >= SAME_EVENT_THRESHOLD:
        return best.cluster
    return None


def assign_cluster(session: Session, item: NewsItem) -> NewsCluster:
    cluster = find_cluster(session, item)
    if cluster is None:
        cluster = NewsCluster(
            canonical_title=item.title,
            topic_key=topic_key(item.title),
            category=item.category,
            first_published_at=item.published_at,
            last_published_at=item.published_at,
            item_count=1,
        )
        session.add(cluster)
        session.flush()
    else:
        cluster.item_count = (cluster.item_count or 0) + 1
        if item.published_at:
            if not cluster.first_published_at or item.published_at < cluster.first_published_at:
                cluster.first_published_at = item.published_at
            if not cluster.last_published_at or item.published_at > cluster.last_published_at:
                cluster.last_published_at = item.published_at
    item.cluster_id = cluster.id
    return cluster
