"""Transactional MySQL business data."""
from __future__ import annotations

from typing import Any

from sqlalchemy import (Boolean, Column, Double, ForeignKey, Integer, JSON, MetaData, String,
                        Table, Text, Index, create_engine, select, func)
from sqlalchemy.engine import Connection, URL
from sqlalchemy.dialects.mysql import insert as mysql_insert

from backend.catalog import catalog
from backend.store import Config
from backend.recommendation_policy import WATCH_ACTIONS

metadata = MetaData()
users = Table('users', metadata,
    Column('id', String(64), primary_key=True), Column('name', String(128), nullable=False),
    Column('avatar', String(256), nullable=False, default='Y'))
videos = Table('videos', metadata,
    Column('id', String(64), primary_key=True),
    Column('author_id', String(64), ForeignKey('users.id'), nullable=False),
    Column('title', String(256), nullable=False), Column('category', String(64), nullable=False),
    Column('tags', String(512), nullable=False), Column('description', Text, nullable=False),
    Column('video_url', Text, nullable=False), Column('cover', Text, nullable=False),
    Column('duration', Integer, nullable=False), Column('created_at', Double, nullable=False),
    Column('base_likes', Integer, nullable=False, default=0),
    Column('published', Boolean, nullable=False, default=True))
interactions = Table('video_interactions', metadata,
    Column('user_id', String(64), ForeignKey('users.id'), primary_key=True),
    Column('item_id', String(64), ForeignKey('videos.id'), primary_key=True),
    Column('kind', String(16), primary_key=True), Column('active', Boolean, nullable=False))
follows = Table('follows', metadata,
    Column('user_id', String(64), ForeignKey('users.id'), primary_key=True),
    Column('creator_id', String(64), ForeignKey('users.id'), primary_key=True),
    Column('active', Boolean, nullable=False))
outbox = Table('event_outbox', metadata,
    Column('event_id', String(64), primary_key=True), Column('payload', JSON, nullable=False),
    Column('created_at', Double, nullable=False), Column('delivered_at', Double, nullable=True),
    Column('attempts', Integer, nullable=False, default=0), Column('last_error', Text, nullable=True))
model_versions = Table('model_versions', metadata,
    Column('id', String(64), primary_key=True), Column('algorithm', String(64), nullable=False),
    Column('artifact_path', Text, nullable=False), Column('metrics', JSON, nullable=False),
    Column('created_at', Double, nullable=False), Column('active', Boolean, nullable=False, default=False))
Index('ix_outbox_pending', outbox.c.delivered_at, outbox.c.created_at, outbox.c.event_id)
Index('ix_video_likes', interactions.c.item_id, interactions.c.kind, interactions.c.active)
for table in metadata.tables.values():
    table.dialect_options['mysql']['charset'] = 'utf8mb4'
    table.dialect_options['mysql']['collate'] = 'utf8mb4_bin'
    table.dialect_options['mysql']['engine'] = 'InnoDB'

class EventConflict(ValueError):
    pass

class BusinessStore:
    def __init__(self, config: Config) -> None:
        self.config = config
        if not config.mysql_password:
            raise ValueError('MYSQL_PASSWORD is required for MySQL business storage')
        url = URL.create('mysql+pymysql', username=config.mysql_user, password=config.mysql_password,
                         host=config.mysql_host, port=config.mysql_port, database=config.mysql_database,
                         query={'charset': 'utf8mb4'})
        self.engine = create_engine(url, pool_pre_ping=True, pool_recycle=1800,
                                    connect_args={'connect_timeout': 5, 'read_timeout': 10, 'write_timeout': 10})
        metadata.create_all(self.engine)
        if config.seed_catalog:
            self.seed()

    def upsert(self, db: Connection, table: Table, values: dict[str, Any], changes: dict[str, Any] | None = None) -> None:
        stmt = mysql_insert(table).values(**values)
        db.execute(stmt.on_duplicate_key_update(**(changes or {next(iter(values)): table.c[next(iter(values))]})))

    def seed(self) -> None:
        with self.engine.begin() as db:
            for v in catalog():
                creator = f'creator-{["旅行","生活","运动","美食","科技","音乐"].index(v["category"])+1}'
                self.upsert(db, users, dict(id=creator, name=v['author'], avatar=v['avatar']))
                self.upsert(db, videos, {k: v[k] for k in ('id','title','category','tags','description','video_url','cover','duration','created_at')} |
                            dict(author_id=creator, base_likes=v['likes'], published=True))
        self.repair_duplicate_videos()

    def repair_duplicate_videos(self) -> None:
        """Repair catalogs created before every demo item had a distinct clip.

        Normal restarts keep edited titles and moderation state. Only when two
        catalog rows point at the same local clip do we treat the catalog as
        stale and restore canonical metadata for every known item.
        """
        canonical = {v['id']: v for v in catalog()}
        with self.engine.begin() as db:
            rows = db.execute(select(videos.c.id, videos.c.video_url)).all()
            if len({url for _, url in rows}) == len(rows):
                return
            for item_id, _ in rows:
                v = canonical.get(item_id)
                if v is None:
                    continue
                creator = f'creator-{["旅行","生活","运动","美食","科技","音乐"].index(v["category"])+1}'
                db.execute(videos.update().where(videos.c.id == item_id).values(
                    title=v['title'], category=v['category'], tags=v['tags'], description=v['description'],
                    video_url=v['video_url'], cover=v['cover'], duration=v['duration'], author_id=creator))


    def catalog(self) -> list[dict[str, Any]]:
        counts = select(interactions.c.item_id, func.count().label('likes_count')).where(
            interactions.c.kind == 'like', interactions.c.active.is_(True)).group_by(interactions.c.item_id).subquery()
        stmt = select(videos, users.c.name.label('author'), users.c.avatar,
                      (videos.c.base_likes+func.coalesce(counts.c.likes_count, 0)).label('likes')).select_from(
                      videos.join(users, users.c.id == videos.c.author_id).outerjoin(counts, counts.c.item_id == videos.c.id))
        with self.engine.connect() as db:
            return [dict(row) for row in db.execute(stmt.where(videos.c.published.is_(True)).order_by(videos.c.id)).mappings()]

    def state(self, user: str) -> dict[str, list[str]]:
        with self.engine.connect() as db:
            rows = db.execute(select(interactions.c.item_id, interactions.c.kind).where(
                interactions.c.user_id == user, interactions.c.active.is_(True))).all()
            creators = db.execute(select(follows.c.creator_id).where(
                follows.c.user_id == user, follows.c.active.is_(True))).scalars().all()
        return {'liked': [r.item_id for r in rows if r.kind == 'like'],
                'saved': [r.item_id for r in rows if r.kind == 'favorite'], 'following': list(creators)}

    def watched_ids(self, user: str) -> set[str]:
        # Read committed business events immediately, without waiting for Kafka/Flink.
        item = outbox.c.payload['item_id'].as_string()
        with self.engine.connect() as db:
            return set(db.execute(select(item).where(
                outbox.c.payload['user_id'].as_string()==user,
                outbox.c.payload['action'].as_string().in_(WATCH_ACTIONS)).distinct()).scalars())

    def record(self, event: dict[str, Any]) -> bool:
        """Business mutation + durable outbox in one transaction. Returns whether new."""
        with self.engine.begin() as db:
            # Serialize each user's writes, including first interactions and outbox retries.
            self.upsert(db, users, dict(id=event['user_id'], name=event['user_id'], avatar='Y'))
            db.execute(select(users.c.id).where(users.c.id == event['user_id']).with_for_update()).first()
            existing = db.execute(select(outbox.c.payload).where(outbox.c.event_id == event['event_id'])).scalar_one_or_none()
            if existing is not None:
                if any(existing[k] != event[k] for k in ('user_id','item_id','action')):
                    raise EventConflict('event_id 已被不同的行为使用')
                return False
            video = db.execute(select(videos.c.author_id).where(videos.c.id == event['item_id'], videos.c.published.is_(True))).first()
            if video is None:
                raise LookupError('视频不存在或已下架')
            action = event['action']
            effective = True
            if action in ('like','unlike','favorite','unfavorite'):
                kind = 'favorite' if 'favorite' in action else 'like'
                active = not action.startswith('un')
                key = dict(user_id=event['user_id'], item_id=event['item_id'], kind=kind)
                previous = db.execute(select(interactions.c.active).where(*[interactions.c[k] == v for k,v in key.items()])).scalar_one_or_none()
                effective = bool(previous) != active
                self.upsert(db, interactions, {**key, 'active': active}, {'active': active})
            elif action in ('follow','unfollow'):
                active = action == 'follow'
                key = dict(user_id=event['user_id'], creator_id=video.author_id)
                previous = db.execute(select(follows.c.active).where(*[follows.c[k] == v for k,v in key.items()])).scalar_one_or_none()
                effective = bool(previous) != active
                self.upsert(db, follows, {**key, 'active': active}, {'active': active})
            db.execute(outbox.insert().values(event_id=event['event_id'], payload=event,
                       created_at=event['timestamp'], delivered_at=None if effective else event['timestamp'], attempts=0))
        return True

    def outbox_status(self) -> dict[str, Any]:
        with self.engine.connect() as db:
            pending = db.execute(select(func.count()).select_from(outbox).where(outbox.c.delivered_at.is_(None))).scalar_one()
            failure = db.execute(select(outbox.c.last_error).where(outbox.c.last_error.is_not(None),
                outbox.c.delivered_at.is_(None)).order_by(outbox.c.created_at).limit(1)).scalar_one_or_none()
        return {'backend': self.engine.dialect.name, 'pending_events': pending, 'delivery_error': bool(failure)}

    def close(self) -> None:
        self.engine.dispose()
