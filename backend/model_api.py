from __future__ import annotations
from typing import Literal
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from backend.training.data import TRAINABLE
from backend.training.registry import Registry

router = APIRouter(prefix='/api/models',tags=['models'])

class TrainingRequest(BaseModel):
    # 限制模型类别、向量维度、轮数和随机种子，防止无边界的同步资源消耗。
    algorithm: Literal['als','fm','two_tower']
    factors: int = Field(default=12,ge=4,le=32)
    epochs: int = Field(default=20,ge=1,le=50)
    seed: int = Field(default=42,ge=0,le=2147483647)

@router.get('')
def versions(request: Request):
    registry: Registry = request.app.state.registry
    return {'items':registry.versions(),
            'trainable':[dict(id=a,name=b,family=c,description=d) for a,b,c,d in TRAINABLE]}

@router.post('/train',status_code=202)
def train(payload: TrainingRequest,request: Request):
    # 提交快照训练任务并返回 202，计算由单线程管理器异步完成。
    # 样本不足返回 422，已有训练任务运行返回 409。
    registry: Registry = request.app.state.registry
    try:
        events = request.app.state.analytics.events()
    except Exception as exc:
        raise HTTPException(503,'无法读取训练行为，请检查分析数据库') from exc
    try:
        version = registry.submit(registry.business.catalog(),events,**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409,str(exc)) from exc
    return {'id':version,'status':'queued','status_url':f'/api/models/{version}'}

@router.get('/{version}')
def version_details(version: str,request: Request):
    try:
        return request.app.state.registry.version(version)
    except LookupError as exc:
        raise HTTPException(404,str(exc)) from exc

@router.post('/{version}/activate')
def activate(version: str,request: Request):
    # 启用前校验模型状态、路径和内容摘要；异常制品不能进入在线推荐。
    try:
        return request.app.state.registry.activate(version)
    except LookupError as exc:
        raise HTTPException(404,str(exc)) from exc
    except (ValueError,OSError) as exc:
        raise HTTPException(409,str(exc)) from exc

@router.post('/{version}/deactivate')
def deactivate(version: str,request: Request):
    try:
        request.app.state.registry.deactivate(version)
    except LookupError as exc:
        raise HTTPException(404,str(exc)) from exc
    return {'id':version,'active':False}
