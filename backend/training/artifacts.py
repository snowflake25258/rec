from __future__ import annotations
from pathlib import Path
from typing import Any
from uuid import uuid4
import hashlib
import json
import os
import numpy as np
from backend.training.models import Model
from backend.training.data import Dataset


def checksum(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.sha256(stream.read()).hexdigest()


def save(root: Path, version: str, model: Model, data: Dataset, config: dict[str,Any]) -> tuple[Path,str]:
    # 模型参数、编号映射、训练矩阵与验证快照一起压缩保存。
    # 先写同目录临时文件，再原子替换目标文件，避免读取到半个模型。
    root.mkdir(parents=True,exist_ok=True)
    destination = root/f'{version}.npz'
    temporary = root/f'.{uuid4().hex}.npz'
    meta = {'format':1,'algorithm':model.algorithm,'users':model.users,'items':model.items,
            'categories':data.categories,'config':config,'cutoff':data.cutoff,
            'validation':{str(u):sorted(v) for u,v in data.validation.items()}}
    try:
        np.savez_compressed(temporary,metadata=np.array(json.dumps(meta,ensure_ascii=False)),
            item_categories=model.item_categories,training_matrix=data.matrix,**model.params)
        os.replace(temporary,destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination,checksum(destination)


def load(path: Path, expected_hash: str) -> Model:
    # 先检查文件大小和 SHA-256，再以 allow_pickle=False 读取数组。
    # 验证格式版本、参数有限性与输出维度，不直接信任磁盘内容。
    if not path.is_file() or path.stat().st_size > 64*1024*1024:
        raise ValueError('模型文件不存在或超过大小限制')
    if checksum(path) != expected_hash:
        raise ValueError('模型校验失败，请重新训练或恢复模型文件')
    with np.load(path,allow_pickle=False) as archive:
        meta = json.loads(str(archive['metadata']))
        if meta.get('format') != 1:
            raise ValueError('模型文件版本不兼容')
        p = {k:archive[k].copy() for k in archive.files if k not in ('metadata','item_categories','training_matrix')}
        if any(not np.all(np.isfinite(v)) for v in p.values()):
            raise ValueError('模型参数存在非有限数值')
        model = Model(meta['algorithm'],tuple(meta['users']),tuple(meta['items']),archive['item_categories'].copy(),p)
    if model.users:
        scores = model.scores(model.users[0])
        if scores is None or scores.shape != (len(model.items),) or not np.all(np.isfinite(scores)):
            raise ValueError('模型输出格式错误')
    return model
