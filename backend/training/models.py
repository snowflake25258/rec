from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import numpy as np
from backend.training.data import Dataset, samples

@dataclass
class Model:
    algorithm: str
    users: tuple[str, ...]
    items: tuple[str, ...]
    item_categories: np.ndarray
    params: dict[str, np.ndarray]

    def scores(self, user: str) -> np.ndarray | None:
        # 一次计算已知用户对模型目录的全部视频分数；未知用户返回 None 交由热门回退。
        if user not in self.users:
            return None
        u = self.users.index(user)
        j = np.arange(len(self.items))
        return forward(self.algorithm, self.params, np.full(len(j),u), j,
                       self.item_categories, len(self.users),len(self.items))[0]


def forward(algorithm: str, p: dict[str,np.ndarray], u: np.ndarray, j: np.ndarray,
            cats: np.ndarray, nusers: int, nitems: int) -> tuple[np.ndarray, dict[str,np.ndarray]]:
    # ALS 计算因子点积；FM 用平方和技巧计算二阶交叉；
    # 双塔分别变换用户和视频向量，再按维度缩放点积。返回中间量供反向传播复用。
    if algorithm == 'als':
        return (p['user'][u]*p['item'][j]).sum(axis=1), {}
    if algorithm == 'fm':
        fields = np.column_stack((u, nusers+j, nusers+nitems+cats[j]))
        v = p['factors'][fields]
        total = v.sum(axis=1)
        logits = p['bias'][0]+p['linear'][fields].sum(axis=1)+.5*(total**2-(v**2).sum(axis=1)).sum(axis=1)
        return logits, {'fields':fields,'v':v,'total':total}
    if algorithm == 'two_tower':
        a, b = p['user'][u], p['item'][j]+p['category'][cats[j]]
        h_u = np.tanh(a@p['user_w']+p['user_b'])
        h_i = np.tanh(b@p['item_w']+p['item_b'])
        return (h_u*h_i).sum(axis=1)/np.sqrt(h_u.shape[1])+p['bias'][0], {'a':a,'b':b,'hu':h_u,'hi':h_i}
    raise ValueError('未知训练模型')


def gradient(algorithm: str, p: dict[str,np.ndarray], u: np.ndarray, j: np.ndarray, y: np.ndarray,
             cats: np.ndarray, nusers: int, nitems: int) -> tuple[float, dict[str,np.ndarray]]:
    # FM 与双塔使用数值稳定的二元交叉熵；np.add.at 累加重复特征索引的梯度。
    # ALS 不走此梯度入口，而采用闭式交替求解。
    logits, c = forward(algorithm,p,u,j,cats,nusers,nitems)
    loss = float(np.mean(np.logaddexp(0.,logits)-y*logits))
    g = (1/(1+np.exp(-np.clip(logits,-40,40)))-y)/len(y)
    grads = {k:np.zeros_like(v) for k,v in p.items()}
    grads['bias'][0] = g.sum()
    if algorithm == 'fm':
        np.add.at(grads['linear'],c['fields'], np.broadcast_to(g[:,None], c['fields'].shape))
        np.add.at(grads['factors'],c['fields'],g[:,None,None]*(c['total'][:,None,:]-c['v']))
    elif algorithm == 'two_tower':
        du = g[:,None]*c['hi']*(1-c['hu']**2)/np.sqrt(c['hu'].shape[1])
        di = g[:,None]*c['hu']*(1-c['hi']**2)/np.sqrt(c['hi'].shape[1])
        grads['user_w'], grads['item_w'] = c['a'].T@du, c['b'].T@di
        grads['user_b'], grads['item_b'] = du.sum(axis=0), di.sum(axis=0)
        np.add.at(grads['user'],u,du@p['user_w'].T)
        item_grad = di@p['item_w'].T
        np.add.at(grads['item'],j,item_grad)
        np.add.at(grads['category'],cats[j],item_grad)
    else:
        raise ValueError('梯度仅支持 FM 和双塔网络')
    return loss, grads


def fit(data: Dataset, algorithm: str, factors: int = 12, epochs: int = 20, seed: int = 42) -> tuple[Model,list[float]]:
    # 固定随机种子保证同输入可复现。ALS 交替解用户与视频因子线性系统；
    # FM/双塔按 64 条小批次执行 SGD。训练结束拒绝非有限参数或损失。
    rng = np.random.default_rng(seed)
    nu, ni = data.matrix.shape
    losses: list[float] = []
    if algorithm == 'als':
        p = {'user':rng.normal(0,.1,(nu,factors)), 'item':rng.normal(0,.1,(ni,factors))}
        confidence = 1+20*np.log1p(data.matrix)
        preference = (data.matrix > 0).astype(float)
        regularization = .1*np.eye(factors)
        for _ in range(epochs):
            for left,right,c,r in [('user','item',confidence,preference),('item','user',confidence.T,preference.T)]:
                other = p[right]
                gram = other.T@other
                for i in range(len(p[left])):
                    p[left][i] = np.linalg.solve(gram+(other.T*(c[i]-1))@other+regularization, other.T@(c[i]*r[i]))
            error = p['user']@p['item'].T-preference
            losses.append(float((confidence*error**2).sum()+.1*sum((v*v).sum() for v in p.values())))
    elif algorithm in ('fm','two_tower'):
        if algorithm == 'fm':
            total = nu+ni+len(data.categories)
            p = {'linear':np.zeros(total), 'factors':rng.normal(0,.1,(total,factors)), 'bias':np.zeros(1)}
        else:
            p = {'user':rng.normal(0,.2,(nu,factors)), 'item':rng.normal(0,.2,(ni,factors)),
                 'category':rng.normal(0,.2,(len(data.categories),factors)),
                 'user_w':rng.normal(0,1/np.sqrt(factors),(factors,factors)),
                 'item_w':rng.normal(0,1/np.sqrt(factors),(factors,factors)),
                 'user_b':np.zeros(factors), 'item_b':np.zeros(factors), 'bias':np.zeros(1)}
        u,j,y = samples(data,rng)
        for _ in range(epochs):
            order = rng.permutation(len(y))
            for offset in range(0,len(order),64):
                batch = order[offset:offset+64]
                _, grads = gradient(algorithm,p,u[batch],j[batch],y[batch],data.item_categories,nu,ni)
                for key in p:
                    p[key] -= .2*(grads[key]+.001*p[key])
            logits,_ = forward(algorithm,p,u,j,data.item_categories,nu,ni)
            losses.append(float(np.mean(np.logaddexp(0.,logits)-y*logits)))
    else:
        raise ValueError('未知训练算法')
    if not all(np.all(np.isfinite(v)) for v in p.values()) or not np.all(np.isfinite(losses)):
        raise ValueError('训练数值异常，未保存模型')
    return Model(algorithm,data.users,data.items,data.item_categories,p),losses
