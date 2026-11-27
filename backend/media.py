"""Local video paths and a resumable download manifest."""
from __future__ import annotations
from pathlib import Path
import json
import os
import re

ROOT=Path(__file__).resolve().parent.parent
NAME=re.compile(r'^[a-f0-9]{64}\.mp4$')


def media_root() -> Path:
    return Path(os.getenv('MEDIA_DIRECTORY',str(ROOT/'runtime/media'))).resolve()


def load_manifest(root: Path) -> dict:
    # 加载版本化下载清单；清单不存在时允许远程地址回退，格式异常时明确报错。
    path=root/'manifest.json'
    if not path.exists():return {'version':1,'videos':{}}
    data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('version')!=1 or not isinstance(data.get('videos'),dict):
        raise ValueError('视频下载清单格式不兼容')
    return data


def local_sources(urls: list[str]) -> list[str]:
    # 仅当清单文件名符合 SHA-256 命名且本地文件存在时改用媒体接口。
    # 避免将任意路径拼接到本地视频根目录之外。
    root=media_root()
    manifest=load_manifest(root)
    result=[]
    for url in urls:
        entry=manifest['videos'].get(url,{})
        name=entry.get('filename','')
        result.append('/media/videos/'+name if NAME.fullmatch(name) and (root/'videos'/name).is_file() else url)
    return result
