from __future__ import annotations
"""Executable classical recommendation baselines with deterministic training."""
from dataclasses import dataclass
from collections.abc import Callable
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
    # 对当前候选分数作 Min-Max 缩放；常数向量通过微小分母得到零向量。
    return (x-x.min()) / (np.ptp(x)+1e-9)


@dataclass(frozen=True)
class RecommendationContext:
    matrix: np.ndarray
    uid: int
    features: np.ndarray
    trending: np.ndarray
    history: dict[str, list[int]]
    user: str


def score_popular(context: RecommendationContext) -> np.ndarray:
    return context.matrix.sum(axis=0)


def score_trending(context: RecommendationContext) -> np.ndarray:
    return context.trending


def score_content(context: RecommendationContext) -> np.ndarray:
    return context.features @ (context.matrix[context.uid] @ context.features)


def score_usercf(context: RecommendationContext) -> np.ndarray:
    matrix, uid = context.matrix, context.uid
    # UserCF：当前用户与所有用户做余弦相似度，再加权汇总邻居的视频偏好。
    # 自相似度必须置零；此基线使用全部邻居，未实现 Top-K 相似用户截断。
    norms = np.linalg.norm(matrix, axis=1)
    sim = (matrix @ matrix[uid])/(norms*max(norms[uid], 1e-9)+1e-9)
    sim[uid] = 0
    usercf = sim @ matrix
    return usercf


def score_itemcf(context: RecommendationContext) -> np.ndarray:
    matrix, uid = context.matrix, context.uid
    target = matrix[uid]
    # ItemCF：对视频列向量做余弦相似度，屏蔽自关联后由当前用户偏好加权。
    itemnorm = np.linalg.norm(matrix, axis=0)
    item_sim = matrix.T @ matrix / (np.outer(itemnorm, itemnorm)+1e-9)
    np.fill_diagonal(item_sim, 0)
    itemcf = target @ item_sim
    return itemcf


def score_svd(context: RecommendationContext) -> np.ndarray:
    matrix, uid = context.matrix, context.uid
    # 截断奇异值分解重建偏好；这是请求内小样本计算，不是离线模型版本。
    u, s, vt = np.linalg.svd(matrix, full_matrices=False)
    k = min(6, max(1, len(s)//2))
    reconstructed = (u[:, :k]*s[:k]) @ vt[:k]
    return reconstructed[uid]


def score_bpr(context: RecommendationContext) -> np.ndarray:
    matrix, uid = context.matrix, context.uid
    # BPR 每次采样用户、正例、未交互负例，优化正负视频点积分数差。
    # 固定随机种子便于复现；仅选择同时有正例和负例的用户以避免空集合采样。
    rng = np.random.default_rng(42)
    p = rng.normal(0, .1, (matrix.shape[0], 12))
    q = rng.normal(0, .1, (matrix.shape[1], 12))
    eligible = [i for i in range(matrix.shape[0]) if 0 < np.count_nonzero(matrix[i]) < matrix.shape[1]]
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
    return p[uid] @ q.T


def score_slopeone(context: RecommendationContext) -> np.ndarray:
    matrix, uid = context.matrix, context.uid
    target = matrix[uid]
    # 按共同交互用户估计物品评分差，使用共同人数对各项预测加权。
    predicted = np.zeros(matrix.shape[1])
    counts = np.zeros(matrix.shape[1])
    for j in np.flatnonzero(target):
        for k in range(matrix.shape[1]):
            both = (matrix[:, j] > 0) & (matrix[:, k] > 0)
            n = both.sum()
            if n:
                predicted[k] += n*(target[j]+(matrix[both, k]-matrix[both, j]).mean())
                counts[k] += n
    return predicted/(counts+1e-9)


def score_association(context: RecommendationContext) -> np.ndarray:
    matrix, uid = context.matrix, context.uid
    target = matrix[uid]
    # 正偏好二值化后计算 P(目标视频|已交互视频)，排除视频自身关联。
    binary = (matrix > 0).astype(float)
    confidence = (binary.T @ binary)/(binary.sum(axis=0)[:, None]+1e-9)
    np.fill_diagonal(confidence, 0)
    return (target > 0) @ confidence


def score_session(context: RecommendationContext) -> np.ndarray:
    matrix = context.matrix
    history, user = context.history, context.user
    popular = score_popular(context)
    # 从用户正反馈序列累计一阶转移概率；没有显式按时间间隔切分会话。
    transitions = np.zeros((matrix.shape[1], matrix.shape[1]))
    for sequence in history.values():
        for a, b in zip(sequence, sequence[1:]):
            transitions[a, b] += 1
    transitions /= transitions.sum(axis=1, keepdims=True)+1e-9
    return transitions[history[user][-1]] if history[user] else popular


def score_hybrid(context: RecommendationContext) -> np.ndarray:
    # Hybrid 融合 ItemCF、类别内容、衰减热度及热门。
    return (.35*normalize(score_itemcf(context))
            + .30*normalize(score_content(context))
            + .25*normalize(score_trending(context))
            + .1*normalize(score_popular(context)))


def score_mmr(context: RecommendationContext) -> np.ndarray:
    return score_hybrid(context)


def rerank_mmr(scores: np.ndarray, features: np.ndarray,
               candidates: list[int], limit: int) -> list[int]:
    candidates = candidates.copy()
    selected: list[int] = []
    while candidates and len(selected) < limit:
        def rank(j: int) -> float:
            # 同类已入榜视频会降低新候选得分。
            redundancy = max((float(features[j] @ features[k]) for k in selected), default=0)
            return float(scores[j])-.3*redundancy
        best = max(candidates, key=rank)
        selected.append(best)
        candidates.remove(best)
    return selected


SCORERS: dict[str, Callable[[RecommendationContext], np.ndarray]] = {
    'hybrid': score_hybrid,
    'popular': score_popular,
    'trending': score_trending,
    'content': score_content,
    'usercf': score_usercf,
    'itemcf': score_itemcf,
    'slopeone': score_slopeone,
    'svd': score_svd,
    'bpr': score_bpr,
    'association': score_association,
    'session': score_session,
    'mmr': score_mmr,
}


def recommend(items: list[dict[str, Any]], events: list[dict[str, Any]], user: str,
              algorithm: str, limit: int = 10,
              materialized: list[dict[str, Any]] | None = None,
              excluded: set[str] | None = None) -> list[dict[str, Any]]:
    # 统一传统算法入口，输入视频目录、行为样本、用户及可选的聚合偏好。
    # 存在 materialized 时直接构建偏好矩阵，不再累加原始事件，避免双重计数。
    # 所有路径共享硬性已看排除；历史正偏好仅额外施加轻微重复惩罚。
    if algorithm not in {a[0] for a in ALGORITHMS}:
        raise ValueError('未知算法')
    if not items:
        return []
    # 固定视频与用户索引，将稀疏行为映射为本基线使用的稠密用户×视频矩阵。
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
    context = RecommendationContext(matrix, uid, features, trending, history, user)
    result_scores = SCORERS[algorithm](context)
    if not np.any(target) and algorithm not in ('popular', 'trending'):
        result_scores = normalize(popular)
    # Watch history is a hard exclusion; other interactions retain a mild repeat penalty.
    result_scores = normalize(result_scores)-.15*(target > 0)
    watched = watched_items(events,user,excluded)
    candidates = [j for j,v in enumerate(items) if v['id'] not in watched]
    if algorithm == 'mmr':
        selected = rerank_mmr(result_scores, features, candidates, limit)
    else:
        selected = sorted(candidates, key=lambda j: float(result_scores[j]), reverse=True)[:max(0, limit)]
    label = next(a[1] for a in ALGORITHMS if a[0] == algorithm)
    return [{**items[j], 'score': round(float(result_scores[j]), 4), 'reason': f'{label} · {items[j]["category"]}兴趣匹配'} for j in selected]
