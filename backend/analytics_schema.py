"""MySQL tables used by Flink JDBC sinks and online feature reads."""
from sqlalchemy import MetaData, Table, Column, String, BigInteger, Double, DateTime, Index
from sqlalchemy.dialects.mysql import DATETIME
from backend.schema_comments import apply_comments

metadata = MetaData()
events = Table('events', metadata,
    Column('event_id', String(64), primary_key=True), Column('user_id', String(64), nullable=False),
    Column('item_id', String(64), nullable=False), Column('action', String(16), nullable=False),
    Column('ts_ms', BigInteger, nullable=False), Column('weight', Double, nullable=False))
features = Table('user_item_features', metadata,
    Column('user_id', String(64), primary_key=True), Column('item_id', String(64), primary_key=True),
    Column('preference', Double, nullable=False), Column('interactions', BigInteger, nullable=False),
    Column('last_ts', BigInteger, nullable=False))
hotness = Table('item_hotness', metadata,
    Column('item_id', String(64), primary_key=True),
    Column('window_start', DateTime().with_variant(DATETIME(fsp=3),'mysql'), primary_key=True),
    Column('window_end', DateTime().with_variant(DATETIME(fsp=3),'mysql'), nullable=False),
    Column('score', Double, nullable=False), Column('interactions', BigInteger, nullable=False))
Index('ix_events_time', events.c.ts_ms, events.c.event_id)
Index('ix_features_updated', features.c.last_ts)
for table in metadata.tables.values():
    table.dialect_options['mysql'].update(charset='utf8mb4',collate='utf8mb4_bin',engine='InnoDB')

# Keep the existing demo history intact while the streaming job builds its own state.
stream_events = events.to_metadata(metadata, name='stream_events')
stream_features = features.to_metadata(metadata, name='stream_user_item_features')
stream_hotness = hotness.to_metadata(metadata, name='stream_item_hotness')
for table in (stream_events,stream_features,stream_hotness):
    for index in table.indexes:
        index.name='ix_stream_'+index.name.removeprefix('ix_')

# 克隆完成后重新赋予语义，区分演示表与 Flink 生产输出表的表级注释。
apply_comments(metadata)
