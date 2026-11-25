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
