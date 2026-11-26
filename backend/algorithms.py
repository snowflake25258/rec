from __future__ import annotations
"""Executable classical recommendation baselines with deterministic training."""
from typing import Any
import numpy as np
from backend.recommendation_policy import watched_items

ALGORITHMS = [
    ('hybrid', '混合推荐', '融合', '融合协同、内容、热度与探索'),
    ('popular', '热门推荐', '统计', '累计行为加权热度'),
    ('trending', '时效热门', '统计', '按时间指数衰减的行为热度'),
    ('content', '内容推荐', '内容', '用户类别偏好与物品特征余弦相似度'),
    ('usercf', 'UserCF', '协同过滤', '用户余弦相似度加权召回'),
    ('itemcf', 'ItemCF', '协同过滤', '物品共现余弦相似度'),
    ('slopeone', 'Slope One', '协同过滤', '物品评分差分预测'),
    ('svd', 'SVD', '矩阵分解', '截断奇异值分解重建偏好矩阵'),
    ('bpr', 'BPR-MF', '矩阵分解', '隐反馈成对排序随机梯度训练'),
    ('association', '关联规则', '关联', '用户购物篮物品关联置信度'),
    ('session', '会话推荐', '序列', '最近交互驱动的物品转移概率'),
    ('mmr', 'MMR 多样性', '重排', '最大边际相关性贪心重排'),
]
WEIGHTS = {'view': 0.2, 'complete': 1.0, 'like': 3.0, 'favorite': 4.0, 'follow': 2.0,
           'unlike': -3.0, 'unfavorite': -4.0, 'unfollow': -2.0, 'skip': -0.5}

def normalize(x: np.ndarray) -> np.ndarray:
    return (x-x.min()) / (np.ptp(x)+1e-9)


def recommend(items: list[dict[str, Any]], events: list[dict[str, Any]], user: str,
              algorithm: str, limit: int = 10,
              materialized: list[dict[str, Any]] | None = None,
              excluded: set[str] | None = None) -> list[dict[str, Any]]:
    if algorithm not in {a[0] for a in ALGORITHMS}:
        raise ValueError('未知算法')
    if not items:
        return []
    ids = {v['id']: i for i, v in enumerate(items)}
    users = sorted({e['user_id'] for e in events} | {f['user_id'] for f in (materialized or [])} | {user})
    user_ids = {u: i for i, u in enumerate(users)}
    uid = users.index(user)
    matrix = np.zeros((len(users), len(items)))
    if materialized is not None:
        for feature in materialized:
            if feature['item_id'] in ids:
                matrix[user_ids[feature['user_id']], ids[feature['item_id']]] = float(feature['preference'])
    trending = np.zeros(len(items))
    latest = max((e['timestamp'] for e in events), default=0)
    history: dict[str, list[int]] = {u: [] for u in users}
    for e in events:
        if e['item_id'] not in ids:
            continue
        j = ids[e['item_id']]
        weight = WEIGHTS.get(e['action'], 0)
        if materialized is None:
            matrix[user_ids[e['user_id']], j] += weight
        trending[j] += max(weight, 0)*np.exp(-max(0, latest-e['timestamp'])/86400)
        if weight > 0:
            history[e['user_id']].append(j)
    matrix = np.maximum(matrix, 0)
    target = matrix[uid]
    popular = matrix.sum(axis=0)
    categories = sorted({v['category'] for v in items})
    features = np.array([[float(v['category'] == c) for c in categories] for v in items])
    content = features @ (target @ features)
    norms = np.linalg.norm(matrix, axis=1)
    sim = (matrix @ matrix[uid])/(norms*max(norms[uid], 1e-9)+1e-9)
    sim[uid] = 0
    usercf = sim @ matrix
    itemnorm = np.linalg.norm(matrix, axis=0)
    item_sim = matrix.T @ matrix / (np.outer(itemnorm, itemnorm)+1e-9)
    np.fill_diagonal(item_sim, 0)
    itemcf = target @ item_sim
    scores = {'popular': popular, 'trending': trending, 'content': content,
              'usercf': usercf, 'itemcf': itemcf}
    if algorithm == 'svd':
        u, s, vt = np.linalg.svd(matrix, full_matrices=False)
        k = min(6, max(1, len(s)//2))
        scores['svd'] = (u[:, :k]*s[:k]) @ vt[:k]
        scores['svd'] = scores['svd'][uid]
    elif algorithm == 'bpr':
        rng = np.random.default_rng(42)
        p = rng.normal(0, .1, (len(users), 12))
        q = rng.normal(0, .1, (len(items), 12))
        eligible = [i for i in range(len(users)) if 0 < np.count_nonzero(matrix[i]) < len(items)]
        for _ in range(800):
            if not eligible:
                break
            a = int(rng.choice(eligible))
            pos = int(rng.choice(np.flatnonzero(matrix[a] > 0)))
            neg = int(rng.choice(np.flatnonzero(matrix[a] == 0)))
            diff = q[pos]-q[neg]
            grad = 1/(1+np.exp(np.clip(p[a] @ diff, -30, 30)))
            old = p[a].copy()
            p[a] += .04*(grad*diff-.02*p[a])
            q[pos] += .04*(grad*old-.02*q[pos])
            q[neg] += .04*(-grad*old-.02*q[neg])
        scores['bpr'] = p[uid] @ q.T
    elif algorithm == 'slopeone':
        predicted = np.zeros(len(items))
        counts = np.zeros(len(items))
        for j in np.flatnonzero(target):
            for k in range(len(items)):
                both = (matrix[:, j] > 0) & (matrix[:, k] > 0)
                n = both.sum()
                if n:
                    predicted[k] += n*(target[j]+(matrix[both, k]-matrix[both, j]).mean())
                    counts[k] += n
        scores['slopeone'] = predicted/(counts+1e-9)
    elif algorithm == 'association':
        binary = (matrix > 0).astype(float)
        confidence = (binary.T @ binary)/(binary.sum(axis=0)[:, None]+1e-9)
        np.fill_diagonal(confidence, 0)
        scores['association'] = (target > 0) @ confidence
    elif algorithm == 'session':
        transitions = np.zeros((len(items), len(items)))
        for sequence in history.values():
            for a, b in zip(sequence, sequence[1:]):
                transitions[a, b] += 1
        transitions /= transitions.sum(axis=1, keepdims=True)+1e-9
        scores['session'] = transitions[history[user][-1]] if history[user] else popular
    hybrid = .35*normalize(itemcf)+.30*normalize(content)+.25*normalize(trending)+.1*normalize(popular)
    scores['hybrid'] = hybrid
    scores['mmr'] = hybrid
    result_scores = scores[algorithm]
    if not np.any(target) and algorithm not in ('popular', 'trending'):
        result_scores = normalize(popular)
    # Watch history is a hard exclusion; other interactions retain a mild repeat penalty.
    result_scores = normalize(result_scores)-.15*(target > 0)
    watched = watched_items(events,user,excluded)
    candidates = [j for j,v in enumerate(items) if v['id'] not in watched]
    selected: list[int] = []
    while candidates and len(selected) < limit:
        def rank(j: int) -> float:
            redundancy = max((float(features[j] @ features[k]) for k in selected), default=0)
            return float(result_scores[j])-(.3*redundancy if algorithm == 'mmr' else 0)
        best = max(candidates, key=rank)
        selected.append(best)
        candidates.remove(best)
    label = next(a[1] for a in ALGORITHMS if a[0] == algorithm)
    return [{**items[j], 'score': round(float(result_scores[j]), 4), 'reason': f'{label} · {items[j]["category"]}兴趣匹配'} for j in selected]
