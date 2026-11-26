from __future__ import annotations
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional
import logging
import time
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Header, Depends, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from backend.algorithms import ALGORITHMS, recommend
from backend.store import Config, Store
from backend.business import BusinessStore, EventConflict
from backend.auth import (AuthService, InvalidCredentials, UsernameTaken)
from backend.outbox import Publisher
from backend.training.data import TRAINABLE
from backend.training.registry import Registry
from backend.model_api import router as models_router
from backend.pipeline import pipeline_status
from backend.media import NAME as VIDEO_FILENAME

logger = logging.getLogger(__name__)
config = Config()
store: Optional[Store] = None
business: Optional[BusinessStore] = None
auth: Optional[AuthService] = None
publisher: Optional[Publisher] = None
registry: Optional[Registry] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global store, business, auth, publisher, registry
    business = BusinessStore(config)
    try:
        auth = AuthService(business.engine, config.auth_token_ttl_days)
        store = Store(config, business.engine)
        registry = Registry(business, config.model_directory)
        app.state.registry = registry
        app.state.analytics = store
        publisher = Publisher(business, store.append)
        if config.mode == 'production':
            publisher.start()
        try:
            yield
        finally:
            registry.close()
            publisher.close()
            store.close()
    finally:
        business.close()
        business = None
        auth = None
        publisher = None
        store = None
        registry = None

app = FastAPI(title='映刻 · 实时短视频推荐', version='0.1.0', lifespan=lifespan)

@app.exception_handler(SQLAlchemyError)
async def business_database_error(request, exc: SQLAlchemyError):
    logger.error('Business database request failed: %s', type(exc).__name__)
    return JSONResponse(status_code=503, content={'detail': '业务数据库暂不可用，请稍后重试'})

def bearer_token(authorization: str = Header(default='')) -> str:
    scheme, _, token = authorization.partition(' ')
    if scheme.lower() != 'bearer' or not token.strip():
        raise HTTPException(401, '请先登录', headers={'WWW-Authenticate': 'Bearer'})
    return token.strip()

def current_user(token: str = Depends(bearer_token)) -> dict:
    if auth is None:
        raise HTTPException(503, '登录服务正在启动')
    user = auth.authenticate(token)
    if user is None:
        raise HTTPException(401, '登录已失效，请重新登录', headers={'WWW-Authenticate': 'Bearer'})
    return user

def require_identity(user: dict, user_id: str) -> None:
    if user['id'] != user_id:
        raise HTTPException(403, '无权访问其他用户的数据')

app.include_router(models_router, dependencies=[Depends(current_user)])

def database() -> Store:
    if store is None:
        raise HTTPException(503, '服务正在启动')
    return store

def business_database() -> BusinessStore:
    if business is None:
        raise HTTPException(503, '业务数据库正在启动')
    return business

class Event(BaseModel):
    user_id: Optional[str] = Field(default=None, min_length=1, max_length=64, pattern=r'^[a-zA-Z0-9_-]+$')
    item_id: str = Field(min_length=1, max_length=64)
    action: Literal['view', 'complete', 'like', 'unlike', 'favorite', 'unfavorite', 'follow', 'unfollow', 'skip']
    event_id: str = Field(default_factory=lambda: str(uuid4()), max_length=64, min_length=1)

class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r'^[a-zA-Z0-9_]+$')
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(default='', max_length=32)

class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r'^[a-zA-Z0-9_]+$')
    password: str = Field(min_length=1, max_length=128)

@app.get('/api/health')
def health():
    return {'status': 'ok', 'mode': config.mode, 'business_backend': 'mysql'}

@app.post('/api/auth/register', status_code=201)
def register(payload: RegisterRequest, request: Request):
    if auth is None:
        raise HTTPException(503, '登录服务正在启动')
    try:
        return auth.register(payload.username, payload.password, payload.name,
                             request.headers.get('user-agent', ''))
    except UsernameTaken as exc:
        raise HTTPException(409, str(exc)) from exc

@app.post('/api/auth/login')
def login(payload: LoginRequest, request: Request):
    if auth is None:
        raise HTTPException(503, '登录服务正在启动')
    try:
        return auth.login(payload.username, payload.password, request.headers.get('user-agent', ''))
    except InvalidCredentials as exc:
        raise HTTPException(401, str(exc)) from exc

@app.get('/api/auth/me')
def me(user: dict = Depends(current_user)):
    return {'user': user}

@app.post('/api/auth/logout', status_code=204)
def logout(token: str = Depends(bearer_token), user: dict = Depends(current_user)):
    auth.logout(token)
    return None

@app.api_route('/media/videos/{filename}', methods=['GET','HEAD'], include_in_schema=False)
def local_video(filename: str):
    if not VIDEO_FILENAME.fullmatch(filename):
        raise HTTPException(404,'视频不存在')
    root=(Path(config.media_directory)/'videos').resolve()
    path=(root/filename).resolve()
    if path.parent!=root or not path.is_file():
        raise HTTPException(404,'本地视频文件缺失')
    return FileResponse(path,media_type='video/mp4',headers={'Cache-Control':'public, max-age=31536000, immutable'})

def profile_state(user_id: str):
    profile=business_database().state(user_id)
    profile['watched']=sorted(business_database().watched_ids(user_id) | database().watched_ids(user_id))
    return profile

@app.get('/api/users/{user_id}/state')
def user_state(user_id: str, user: dict = Depends(current_user)):
    import re
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', user_id):
        raise HTTPException(422, '用户 ID 无效')
    require_identity(user, user_id)
    return profile_state(user_id)

@app.get('/api/me/state')
def my_state(user: dict = Depends(current_user)):
    return profile_state(user['id'])

@app.get('/api/videos')
def video_catalog():
    return {'items': business_database().catalog()}

@app.get('/api/business/status')
def business_status(user: dict = Depends(current_user)):
    return business_database().outbox_status()

@app.get('/api/algorithms')
def algorithms(user: dict = Depends(current_user)):
    trained = []
    if registry is not None:
        for a,b,c,d in TRAINABLE:
            active = registry.active(a)
            trained.append(dict(id=a,name=b,family=c,description=d,
                status='active' if active else 'needs_training', model_version=active['id'] if active else None))
    return {'items': [dict(id=a, name=b, family=c, description=d, status='implemented') for a,b,c,d in ALGORITHMS]+trained,
            'roadmap': ['FFM', 'Wide & Deep', 'DeepFM', 'DCN', 'DIN / DIEN', 'SASRec / BERT4Rec', 'LightGCN', 'LinUCB / Thompson Sampling', '多任务 MMoE / PLE'],
            'note': 'ALS、FM 和双塔神经网络已接入离线训练；启用模型后可在线推荐，其余深度架构尚未实现。'}

@app.get('/api/recommendations')
def recommendations(user: dict = Depends(current_user), user_id: Optional[str] = Query(None, pattern=r'^[a-zA-Z0-9_-]{1,64}$'), algorithm: str = 'hybrid', limit: int = Query(12, ge=1, le=24)):
    if user_id is not None:
        require_identity(user, user_id)
    user_id = user_id or user['id']
    start = time.perf_counter()
    if algorithm not in {a[0] for a in ALGORITHMS+TRAINABLE}:
        raise HTTPException(422, '未知算法')
    try:
        events = database().events()
        features = database().features()
        watched = business_database().watched_ids(user_id) | database().watched_ids(user_id)
    except Exception as exc:
        logger.exception('Feature store unavailable')
        raise HTTPException(503, 'MySQL 特征读取失败，请检查实时数据链路') from exc
    items = business_database().catalog()
    if algorithm in {a[0] for a in TRAINABLE}:
        if registry is None:
            raise HTTPException(503, '模型服务正在启动')
        try:
            response = registry.recommendations(algorithm,user_id,items,events,limit,features,excluded=watched)
        except LookupError as exc:
            raise HTTPException(409,str(exc)) from exc
        except (ValueError,OSError) as exc:
            raise HTTPException(503,'模型文件不可用，请恢复文件或切换模型版本') from exc
    else:
        response = {'items':recommend(items, events, user_id, algorithm, limit, features,excluded=watched), 'model_version':None,'fallback':None}
    return {**response, 'algorithm': algorithm, 'mode': config.mode, 'latency_ms': round((time.perf_counter()-start)*1000, 2)}

@app.post('/api/events', status_code=202)
def event(payload: Event, user: dict = Depends(current_user)):
    if payload.user_id is not None:
        require_identity(user, payload.user_id)
    data = {**payload.model_dump(exclude={'user_id'}), 'user_id': user['id'], 'timestamp': time.time()}
    try:
        is_new = business_database().record(data)
        if config.mode == 'demo' and publisher is not None:
            publisher.flush()
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except EventConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        logger.exception('Event delivery failed')
        raise HTTPException(503, '业务写入失败，请使用相同 event_id 重试') from exc
    return {'event_id': payload.event_id, 'status': 'accepted', 'duplicate': not is_new,
            'mode': config.mode, 'delivery': 'outbox'}

@app.get('/api/metrics')
def metrics(user: dict = Depends(current_user)):
    try:
        events = database().events()
    except Exception as exc:
        raise HTTPException(503, '数据存储不可用') from exc
    now = time.time()
    buckets = [sum(1 for e in events if now-(12-i)*300 <= e['timestamp'] < now-(11-i)*300) for i in range(12)]
    return {'mode': config.mode, 'events': len(events), 'users': len({e['user_id'] for e in events}),
            'videos': len(business_database().catalog()), 'algorithms': len(ALGORITHMS+TRAINABLE), 'timeline': buckets,
            'business': business_database().outbox_status(),
            'recent': sorted(events, key=lambda e: e['timestamp'], reverse=True)[:15],
            'actions': {a: sum(e['action'] == a for e in events) for a in ['view','like','unlike','favorite','unfavorite','complete','follow','unfollow','skip']},
            'pipeline': pipeline_status(config)+[{'name':'MySQL','status':'query_ok'}],
            'window': '最近 20,000 条行为；趋势图为最近 60 分钟'}

app.mount('/', StaticFiles(directory=Path(__file__).resolve().parent.parent/'frontend', html=True), name='frontend')
