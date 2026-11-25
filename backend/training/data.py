from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import math
import numpy as np
from backend.algorithms import WEIGHTS

TRAINABLE = [
    ('als', 'Implicit ALS', '矩阵分解', '置信度加权交替最小二乘，离线训练在线加载'),
    ('fm', 'FM', '特征交叉', '用户、视频、类别的二阶因子分解机'),
    ('two_tower', '双塔神经网络', '深度召回', '独立用户塔与物品塔，Embedding + tanh 全连接'),
]

@dataclass(frozen=True)
class Dataset:
    users: tuple[str, ...]
    items: tuple[str, ...]
    categories: tuple[str, ...]
    item_categories: np.ndarray
    matrix: np.ndarray
    validation: dict[int, set[int]]
    cutoff: float
    train_events: int
    validation_events: int
    excluded_validation_users: int


def prepare(items: list[dict[str, Any]], events: list[dict[str, Any]]) -> Dataset:
    ids = {v['id']: i for i, v in enumerate(items)}
    rows = sorted((e for e in events if e['item_id'] in ids and e['action'] in WEIGHTS
                   and math.isfinite(float(e['timestamp']))), key=lambda e: (float(e['timestamp']), e['event_id']))
    if len(rows) < 10 or len(items) < 2:
        raise ValueError('至少需要 10 条行为和 2 个视频才能训练与时间切分评估')
    cutoff = float(rows[min(len(rows)-1, int(len(rows)*.8))]['timestamp'])
    train = [e for e in rows if float(e['timestamp']) < cutoff]
    valid = [e for e in rows if float(e['timestamp']) >= cutoff]
    users = tuple(sorted({e['user_id'] for e in train}))
    if not train or not valid:
        raise ValueError('时间戳无法切分，请提供至少两个不同时段的行为数据')
    if len(users) > 1000 or len(items) > 500:
        raise ValueError('当前训练基线最多支持 1000 用户、500 视频，请拆分训练样本')
    uids = {u: i for i, u in enumerate(users)}
    matrix = np.zeros((len(users), len(items)))
    for e in train:
        matrix[uids[e['user_id']], ids[e['item_id']]] += WEIGHTS[e['action']]
    matrix = np.maximum(matrix, 0.)
    if np.count_nonzero(matrix) < 2:
        raise ValueError('有效正反馈不足，至少需要两个用户视频正反馈组合')
    validation: dict[int, set[int]] = {}
    excluded = set()
    for e in valid:
        if WEIGHTS[e['action']] <= 0:
            continue
        if e['user_id'] not in uids:
            excluded.add(e['user_id'])
            continue
        u, j = uids[e['user_id']], ids[e['item_id']]
        if matrix[u, j] == 0 and matrix[u].sum() > 0:
            validation.setdefault(u, set()).add(j)
    categories = tuple(sorted({v['category'] for v in items}))
    return Dataset(users, tuple(ids), categories,
                   np.array([categories.index(v['category']) for v in items]), matrix,
                   validation, cutoff, len(train), len(valid), len(excluded))


def samples(data: Dataset, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    positive = np.argwhere(data.matrix > 0)
    pairs = [(int(u), int(j), 1.) for u,j in positive]
    for u,j in positive:
        candidates = np.flatnonzero(data.matrix[u] == 0)
        if len(candidates):
            pairs.extend((int(u), int(n), 0.) for n in rng.choice(candidates, size=min(3,len(candidates)), replace=False))
    rng.shuffle(pairs)
    arr = np.asarray(pairs)
    return arr[:,0].astype(int), arr[:,1].astype(int), arr[:,2]


def ranking_metrics(predictions: dict[int, np.ndarray], data: Dataset, k: int = 5) -> dict[str, Any]:
    recalls, ndcgs, covered = [], [], set()
    for u, relevant in data.validation.items():
        scores = predictions[u].copy()
        scores[data.matrix[u] > 0] = -np.inf
        candidates = np.flatnonzero(np.isfinite(scores))
        ranked = candidates[np.argsort(-scores[candidates], kind='stable')[:k]]
        hits = np.array([j in relevant for j in ranked], dtype=float)
        recalls.append(float(hits.sum()/len(relevant)))
        ideal = sum(1/math.log2(i+2) for i in range(min(k,len(relevant))))
        ndcgs.append(float(sum(hit/math.log2(i+2) for i,hit in enumerate(hits))/ideal))
        covered.update(ranked.tolist())
    return {'recall_at_5': float(np.mean(recalls)) if recalls else None,
            'ndcg_at_5': float(np.mean(ndcgs)) if ndcgs else None,
            'coverage_at_5': len(covered)/len(data.items) if recalls else None,
            'evaluated_users':len(recalls), 'excluded_cold_users': data.excluded_validation_users,
            'cutoff':data.cutoff, 'train_events':data.train_events, 'validation_events':data.validation_events,
            'evaluation': 'global_time_80_20_novel_positive_full_catalog',
            'note': '无可评估用户时指标为 null；未交互样本不代表真实负反馈，目录元数据为当前快照。'}
