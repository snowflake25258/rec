from __future__ import annotations
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4
import logging
import time

import numpy as np
from sqlalchemy import select
from backend.business import BusinessStore, model_versions
from backend.algorithms import recommend, normalize, WEIGHTS
from backend.recommendation_policy import watched_items
from backend.training.data import prepare, ranking_metrics, TRAINABLE
from backend.training.models import fit, Model
from backend.training import artifacts

logger = logging.getLogger(__name__)

class Registry:
    def __init__(self,business: BusinessStore,root: str) -> None:
        # 当前管理器限定单进程单任务；重启后未完成任务标记失败，不伪装成可恢复。
        # 模型版本元数据在 MySQL，参数文件在持久化模型目录。
        self.business = business
        self.root = Path(root).resolve()
        # This development trainer is single-process; interrupted jobs are not resumable.
        with business.engine.begin() as db:
            rows = db.execute(select(model_versions)).mappings().all()
            for row in rows:
                if row['metrics'].get('status') in ('queued','running'):
                    db.execute(model_versions.update().where(model_versions.c.id==row['id']).values(
                        metrics={**row['metrics'],'status':'failed','error':'服务已重启，训练被中断，请重新提交'},active=False))
        self.executor = ThreadPoolExecutor(max_workers=1,thread_name_prefix='model-training')
        self.future: Future | None = None
        self.current: str | None = None
        self.lock = RLock()
        self.cache: OrderedDict[str,Model] = OrderedDict()

    def versions(self) -> list[dict[str,Any]]:
        with self.business.engine.connect() as db:
            rows = db.execute(select(model_versions).order_by(model_versions.c.created_at.desc()).limit(100)).mappings()
            return [dict(id=r['id'],algorithm=r['algorithm'],created_at=r['created_at'],active=r['active'],**r['metrics']) for r in rows]

    def active(self,algorithm: str) -> dict[str,Any] | None:
        with self.business.engine.connect() as db:
            row = db.execute(select(model_versions).where(model_versions.c.algorithm==algorithm,
                model_versions.c.active.is_(True)).order_by(model_versions.c.created_at.desc()).limit(1)).mappings().first()
            return dict(row) if row else None

    def version(self,version: str) -> dict[str,Any]:
        with self.business.engine.connect() as db:
            row = db.execute(select(model_versions).where(model_versions.c.id==version)).mappings().first()
            if row is None:
                raise LookupError('模型版本不存在')
            return dict(id=row['id'],algorithm=row['algorithm'],created_at=row['created_at'],active=row['active'],**row['metrics'])

    def submit(self,items: list[dict[str,Any]],events: list[dict[str,Any]],algorithm: str,
               factors: int,epochs: int,seed: int) -> str:
        # 验证并冻结数据快照后才预占训练槽位。锁与单线程执行器防止本进程并发训练。
        if algorithm not in {a[0] for a in TRAINABLE}:
            raise ValueError('未知训练算法')
        # Validate and freeze the sample before reserving a job.
        data = prepare(items,events)
        with self.lock:
            if self.future is not None and not self.future.done():
                raise RuntimeError('已有训练任务运行中，请等待当前任务完成')
            version = uuid4().hex
            config = {'factors':factors,'epochs':epochs,'seed':seed}
            with self.business.engine.begin() as db:
                db.execute(model_versions.insert().values(id=version,algorithm=algorithm,artifact_path='',
                    metrics={'status':'queued','config':config},created_at=time.time(),active=False))
            self.current = version
            self.future = self.executor.submit(self._train,version,algorithm,data,config)
            return version

    def update(self,version: str,metrics: dict[str,Any],**fields: Any) -> None:
        with self.business.engine.begin() as db:
            db.execute(model_versions.update().where(model_versions.c.id==version).values(metrics=metrics,**fields))

    def _train(self,version: str,algorithm: str,data,config: dict[str,Any]) -> None:
        # 后台训练、时间切分评估并计算热门基线，最后保存制品及校验和。
        # 训练异常写入 failed 状态，避免任务永久停留在 running。
        started = time.time()
        try:
            self.update(version,{'status':'running','config':config,'started_at':started})
            model,loss = fit(data,algorithm,**config)
            predictions = {u:model.scores(data.users[u]) for u in data.validation}
            metrics = ranking_metrics(predictions,data)
            baseline = ranking_metrics({u:data.matrix.sum(axis=0) for u in data.validation},data)
            path,digest = artifacts.save(self.root,version,model,data,config)
            result = {'status':'ready','config':config,'evaluation':metrics,
                'baseline':{'recall_at_5':baseline['recall_at_5'],'ndcg_at_5':baseline['ndcg_at_5']},
                'loss_history':loss,'loss_type':'confidence_weighted_squared_error' if algorithm=='als' else 'sampled_binary_cross_entropy',
                'users':len(data.users),'items':len(data.items), 'sha256':digest,
                'parameter_count':int(sum(v.size for v in model.params.values())),
                'duration_seconds':round(time.time()-started,3),'finished_at':time.time()}
            self.update(version,result,artifact_path=str(path))
        except Exception as exc:
            logger.exception('Training failed for %s',version)
            self.update(version,{'status':'failed','config':config,'error':str(exc) if isinstance(exc,ValueError) else type(exc).__name__,
                                 'finished_at':time.time()})

    def _load(self,row: dict[str,Any]) -> Model:
        version = row['id']
        path = Path(row['artifact_path']).resolve()
        if path != self.root/f'{version}.npz':
            raise ValueError('模型路径不属于配置的模型目录')
        # Always verify integrity before activation; inference reuses immutable cached weights.
        model = artifacts.load(path,row['metrics']['sha256'])
        if model.algorithm != row['algorithm']:
            raise ValueError('模型算法与版本记录不匹配')
        return model

    def activate(self,version: str) -> dict[str,Any]:
        # 持锁校验制品，并在同一数据库事务内停用该算法旧版本、启用新版本。
        # 提交后缓存已校验模型，随后推理可复用不可变权重。
        with self.lock:
            with self.business.engine.begin() as db:
                row = db.execute(select(model_versions).where(model_versions.c.id==version)).mappings().first()
                if row is None:
                    raise LookupError('模型版本不存在')
                if row['metrics'].get('status') != 'ready':
                    raise ValueError('仅已完成训练的模型可以启用')
                model = self._load(dict(row))
                db.execute(select(model_versions.c.id).where(model_versions.c.algorithm==row['algorithm']).order_by(
                    model_versions.c.id).with_for_update()).all()
                db.execute(model_versions.update().where(model_versions.c.algorithm==row['algorithm']).values(active=False))
                db.execute(model_versions.update().where(model_versions.c.id==version).values(active=True))
            self.cache[version] = model
            self._trim_cache()
        return {'id':version,'algorithm':row['algorithm'],'active':True}

    def deactivate(self,version: str) -> None:
        with self.business.engine.begin() as db:
            row = db.execute(select(model_versions.c.id).where(model_versions.c.id==version)).first()
            if row is None:
                raise LookupError('模型版本不存在')
            db.execute(model_versions.update().where(model_versions.c.id==version).values(active=False))

    def _trim_cache(self) -> None:
        while len(self.cache)>8:
            self.cache.popitem(last=False)

    def recommendations(self,algorithm: str,user: str,items: list[dict[str,Any]],events: list[dict[str,Any]],
                        limit: int,features=None,excluded: set[str] | None = None) -> dict[str,Any]:
        # 只使用已启用版本；缓存最多保留八个版本，首次载入检查摘要。
        # 未知用户热门回退，新视频热门补齐；两种路径都必须复用已看排除集合。
        row = self.active(algorithm)
        if row is None:
            raise LookupError('该算法尚未启用模型，请先在推荐控制台训练并启用版本')
        with self.lock:
            model = self.cache.get(row['id'])
            if model is None:
                model = self._load(row)
                self.cache[row['id']] = model
                self._trim_cache()
            else:
                self.cache.move_to_end(row['id'])
        scores = model.scores(user)
        watched = watched_items(events,user,excluded)
        fallback = recommend(items,events,user,'popular',len(items),features,excluded=watched)
        if scores is None:
            return {'items':[{**v,'reason':'模型未见过该用户 · 热门回退'} for v in fallback[:limit]],
                    'model_version':row['id'],'fallback':'unknown_user'}
        lookup = dict(zip(model.items,normalize(scores)))
        seen = {e['item_id'] for e in events if e['user_id']==user and WEIGHTS.get(e['action'],0)>0}
        known = [{**v,'score':round(float(lookup[v['id']])-(.15 if v['id'] in seen else 0),4),
                  'reason':f'{algorithm} · 模型 {row["id"][:8]}'} for v in items if v['id'] in lookup and v['id'] not in watched]
        known.sort(key=lambda v:(-v['score'],v['id']))
        extra = [{**v,'reason':'模型未见过该视频 · 热门补齐'} for v in fallback if v['id'] not in lookup]
        return {'items':(known+extra)[:limit],'model_version':row['id'],'fallback':None if not extra else 'new_items_backfill'}

    def close(self) -> None:
        self.executor.shutdown(wait=True,cancel_futures=True)
