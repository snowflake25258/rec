"""Shared watch exclusion policy for every recommendation path."""
from __future__ import annotations
from collections.abc import Iterable
from typing import Any

WATCH_ACTIONS=('view','complete')


def watched_items(events: Iterable[dict[str,Any]],user: str,excluded: set[str] | None = None) -> set[str]:
    # 合并完整持久历史与本轮样本中的观看事件；返回副本，避免修改调用方集合。
    # 按用户隔离，不将其他用户观看的视频排除出当前用户候选。
    return set(excluded or ()) | {e['item_id'] for e in events
        if e['user_id']==user and e['action'] in WATCH_ACTIONS}
