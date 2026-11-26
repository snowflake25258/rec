"""Shared watch exclusion policy for every recommendation path."""
from __future__ import annotations
from collections.abc import Iterable
from typing import Any

WATCH_ACTIONS=('view','complete')


def watched_items(events: Iterable[dict[str,Any]],user: str,excluded: set[str] | None = None) -> set[str]:
    return set(excluded or ()) | {e['item_id'] for e in events
        if e['user_id']==user and e['action'] in WATCH_ACTIONS}
