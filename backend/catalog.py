"""Twenty-four independent, attributed stock-video sources for the demo catalog."""
from __future__ import annotations
import json
import math
from pathlib import Path
from typing import Any
from backend.media import local_sources,load_manifest,media_root

SOURCES=json.loads(Path(__file__).with_name('video_sources.json').read_text(encoding='utf-8'))
CLIPS=[source['source_url'] for source in SOURCES]
TOPICS=[
    ('旅行','山野来信','🌊','#旅行 #治愈风景 #奔赴山海'),
    ('生活','日常观察员','☕','#生活碎片 #慢生活 #记录日常'),
    ('运动','追风计划','🏄','#户外运动 #自由 #热爱'),
    ('美食','一口好食','🍜','#美食 #人间烟火 #城市味道'),
    ('科技','未来放映室','🪐','#科技 #创意 #探索'),
    ('音乐','落日唱片','🎧','#音乐现场 #氛围感 #好歌分享'),
]


def catalog() -> list[dict[str,Any]]:
    if len(SOURCES)!=24 or len(set(CLIPS))!=24:
        raise ValueError('Each demo video must have a distinct source')
    clips=local_sources(CLIPS)
    manifest=load_manifest(media_root())
    result=[]
    for i,source in enumerate(SOURCES):
        category,author,avatar,tags=TOPICS[i%6]
        entry=manifest['videos'].get(source['source_url'],{})
        duration=math.ceil(entry.get('duration_seconds',15+i%4*5))
        result.append(dict(id=source['id'],category=category,title=source['title'],author=author,avatar=avatar,
            tags=tags,description=source['source_title'],video_url=clips[i],cover=source['cover_url'],
            likes=1240+i*937,duration=duration,created_at=1795536000+i*3600))
    return result
