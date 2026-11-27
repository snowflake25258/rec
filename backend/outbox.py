"""At-least-once delivery: persist intent in MySQL, then retry Kafka safely."""
from __future__ import annotations
from collections.abc import Callable
from threading import Event, Lock, Thread
from typing import Any
import logging
import time

from sqlalchemy import select
from backend.business import BusinessStore, outbox

logger = logging.getLogger(__name__)

class Publisher:
    def __init__(self, business: BusinessStore, deliver: Callable[[dict[str, Any]], None]) -> None:
        self.business = business
        self.deliver = deliver
        self.stop = Event()
        self.lock = Lock()
        self.thread = Thread(target=self.run, name='event-outbox', daemon=True)

    def flush(self, limit: int = 20) -> int:
        # 按创建顺序锁定待投递记录；SKIP LOCKED 避免等待其他持锁事务。
        # 发送确认后才标记 delivered_at。发送成功后事务提交前崩溃仍可能重复发送，
        # 因此保持原 event_id，由 Flink 去重实现业务幂等，不能宣称跨系统恰好一次。
        delivered = 0
        with self.lock:
            for _ in range(limit):
                with self.business.engine.begin() as db:
                    row = db.execute(select(outbox).where(outbox.c.delivered_at.is_(None)).order_by(
                        outbox.c.created_at, outbox.c.event_id).limit(1).with_for_update(skip_locked=True)).mappings().first()
                    if row is None:
                        break
                    try:
                        self.deliver(dict(row['payload']))
                    except Exception:
                        logger.exception('Outbox delivery failed; event remains pending')
                        db.execute(outbox.update().where(outbox.c.event_id == row['event_id']).values(
                            attempts=row['attempts']+1, last_error='delivery failed'))
                        break
                    db.execute(outbox.update().where(outbox.c.event_id == row['event_id']).values(
                        delivered_at=time.time(), attempts=row['attempts']+1, last_error=None))
                    delivered += 1
        return delivered

    def run(self) -> None:
        # 每轮批量投递，失败保留待发记录并等待一秒重试。
        # Event.wait 同时承担轮询间隔与可中断退出，避免关闭时长时间阻塞。
        while not self.stop.is_set():
            try:
                self.flush()
            except Exception:
                logger.exception('Outbox database unavailable; retrying')
            self.stop.wait(1)

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.stop.set()
        if self.thread.is_alive():
            self.thread.join(timeout=20)
