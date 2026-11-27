"""Unified MySQL analytics storage; Kafka delivery in streaming mode."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import os
import random
import time
from sqlalchemy import create_engine, select, func
from sqlalchemy.engine import Engine, URL, Connection
from sqlalchemy.dialects.mysql import insert as mysql_insert
from backend.analytics_schema import metadata, events, features, stream_events, stream_features
from backend.algorithms import WEIGHTS
from backend.recommendation_policy import WATCH_ACTIONS

@dataclass(frozen=True)
class Config:
    mode: str = os.getenv('REC_MODE','demo')
    kafka: str = os.getenv('KAFKA_BOOTSTRAP_SERVERS','localhost:9092')
    kafka_topic: str = os.getenv('KAFKA_TOPIC','rec-events')
    flink_rest_url: str = os.getenv('FLINK_REST_URL','http://master:8081')
    flink_job_id: str = os.getenv('FLINK_JOB_ID','')
    auth_token_ttl_days: int = int(os.getenv('AUTH_TOKEN_TTL_DAYS','30'))
    mysql_host: str = os.getenv('MYSQL_HOST','127.0.0.1')
    mysql_port: int = int(os.getenv('MYSQL_PORT','3306'))
    mysql_database: str = os.getenv('MYSQL_DATABASE','yingke')
    mysql_user: str = os.getenv('MYSQL_USER','yingke')
    mysql_password: str = os.getenv('MYSQL_PASSWORD','')
    seed_catalog: bool = os.getenv('SEED_CATALOG','1') == '1'
    seed_analytics: bool = os.getenv('SEED_ANALYTICS','1') == '1'
    model_directory: str = os.getenv('MODEL_DIRECTORY','runtime/models')
    media_directory: str = os.getenv('MEDIA_DIRECTORY',str(Path(__file__).resolve().parent.parent/'runtime/media'))

class Store:
    def __init__(self,config: Config,engine: Engine | None = None) -> None:
        # 按模式选择演示表或 stream_* 实时表，避免直接计算与 Flink 覆盖同一份聚合。
        # 传入 engine 时复用业务连接池，close 不负责释放它。
        if config.mode not in ('demo','production'):
            raise ValueError('REC_MODE must be demo or production')
        self.config=config
        self.event_table=stream_events if config.mode=='production' else events
        self.feature_table=stream_features if config.mode=='production' else features
        self.producer: Any=None
        self.owns_engine=engine is None
        if engine is not None:
            self.engine=engine
        else:
            if not config.mysql_password:
                raise ValueError('MYSQL_PASSWORD is required')
            self.engine=create_engine(URL.create('mysql+pymysql',username=config.mysql_user,password=config.mysql_password,
                host=config.mysql_host,port=config.mysql_port,database=config.mysql_database,query={'charset':'utf8mb4'}),
                pool_pre_ping=True,connect_args={'connect_timeout':5,'read_timeout':10,'write_timeout':10})
        if self.engine.dialect.name != 'mysql':
            raise ValueError('Analytics storage requires a MySQL engine')
        metadata.create_all(self.engine)
        if config.mode=='demo' and config.seed_analytics:
            with self.engine.begin() as db:
                if db.execute(select(events.c.event_id).limit(1)).first() is None:
                    rng=random.Random(42)
                    now=time.time()
                    for i in range(650):
                        user=f'u{rng.randrange(1,31):03d}'
                        topic=int(user[1:])%6
                        video=rng.choice([j+1 for j in range(24) if j%6==topic] if rng.random()<.7 else list(range(1,25)))
                        self._append_sql(db,dict(event_id=f'seed-{i}',user_id=user,item_id=f'v{video:03d}',
                            action=rng.choice(['view','like','complete','favorite']),timestamp=now-65000+i*90))

    def _append_sql(self,db: Connection,event: dict[str,Any]) -> None:
        # 演示链路在同一事务先按 event_id 去重，再写明细并原子累加偏好。
        # 生产模式不走此方法，聚合交给 Flink。
        if db.execute(select(events.c.event_id).where(events.c.event_id==event['event_id'])).first():
            return
        weight=WEIGHTS.get(event['action'],0.)
        ts=int(event['timestamp']*1000)
        db.execute(events.insert().values(**{k:event[k] for k in ('event_id','user_id','item_id','action')},ts_ms=ts,weight=weight))
        values=dict(user_id=event['user_id'],item_id=event['item_id'],preference=weight,interactions=1,last_ts=ts)
        changes=dict(preference=features.c.preference+weight,interactions=features.c.interactions+1,
                     last_ts=func.greatest(features.c.last_ts,ts))
        db.execute(mysql_insert(features).values(**values).on_duplicate_key_update(**changes))

    def events(self) -> list[dict[str,Any]]:
        # 按时间倒序选最近 20000 条，再反转为时间正序供序列算法使用。
        # 该限制适用于分析样本；已看排除另行查询完整历史。
        events=self.event_table
        with self.engine.connect() as db:
            rows=db.execute(select(events).order_by(events.c.ts_ms.desc(),events.c.event_id.desc()).limit(20000)).mappings().all()
            return [dict(event_id=r['event_id'],user_id=r['user_id'],item_id=r['item_id'],action=r['action'],timestamp=r['ts_ms']/1000.) for r in reversed(rows)]

    def watched_ids(self,user: str) -> set[str]:
        # Watch filtering must not be truncated by the feature sampling limit.
        table=self.event_table
        with self.engine.connect() as db:
            return set(db.execute(select(table.c.item_id).where(
                table.c.user_id==user,table.c.action.in_(WATCH_ACTIONS)).distinct()).scalars())

    def append(self,event: dict[str,Any]) -> None:
        # demo 直接落 MySQL；production 使用 Kafka 生产者按用户编号分区。
        # acks=all 并等待 send 结果，投递失败由外层 Outbox 保留并重试。
        if self.config.mode=='demo':
            with self.engine.begin() as db:
                self._append_sql(db,event)
        else:
            if self.producer is None:
                from kafka import KafkaProducer
                self.producer=KafkaProducer(bootstrap_servers=self.config.kafka.split(','),acks='all',retries=2,
                    max_block_ms=5000,request_timeout_ms=5000,api_version_auto_timeout_ms=3000,
                    value_serializer=lambda v:json.dumps(v).encode())
            wire={k:event[k] for k in ('event_id','user_id','item_id','action')}
            wire['ts_ms']=int(event['timestamp']*1000)
            self.producer.send(self.config.kafka_topic,key=event['user_id'].encode(),value=wire).get(timeout=10)

    def features(self) -> list[dict[str,Any]]:
        # 读取最近更新的用户视频聚合值；为累计偏好，不按请求再次累加事件。
        features=self.feature_table
        with self.engine.connect() as db:
            return [dict(r) for r in db.execute(select(features.c.user_id,features.c.item_id,features.c.preference)
                .order_by(features.c.last_ts.desc()).limit(20000)).mappings()]

    def close(self) -> None:
        if self.producer:
            self.producer.close(timeout=5)
        if self.owns_engine:
            self.engine.dispose()
