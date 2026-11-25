"""Download all video sources, validate files, then atomically update MySQL URLs."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4
import hashlib
import json
import os
import time
from urllib.parse import urlparse
from typing import Any
import httpx
from dotenv import load_dotenv

from backend.media import media_root,load_manifest,NAME


def digest(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def download(url: str,root: Path,existing: dict[str,Any]) -> dict[str,Any]:
    name=existing.get('filename','')
    if NAME.fullmatch(name):
        path=root/'videos'/name
        if path.is_file() and path.stat().st_size==existing.get('bytes') and digest(path)==existing.get('sha256'):
            return existing
    if urlparse(url).scheme not in ('http','https'):
        raise ValueError('只接受 HTTP/HTTPS 视频地址')
    destination=root/'videos'
    destination.mkdir(parents=True,exist_ok=True)
    temp=destination/f'.{uuid4().hex}.part'
    last_error: Exception | None=None
    for attempt in range(3):
        try:
            total=0
            sha=hashlib.sha256()
            header=b''
            with httpx.stream('GET',url,follow_redirects=True,timeout=httpx.Timeout(60,connect=10),
                              headers={'User-Agent':'Yingke-Local-Media/1.0','Accept-Encoding':'identity'}) as response:
                response.raise_for_status()
                expected=response.headers.get('content-length')
                if expected and int(expected)>512*1024*1024:raise ValueError('单个视频超过 512MB 下载限制')
                with temp.open('wb') as output:
                    for chunk in response.iter_bytes(1024*1024):
                        total+=len(chunk)
                        if total>512*1024*1024:raise ValueError('单个视频超过 512MB 下载限制')
                        if len(header)<64:header=(header+chunk)[:64]
                        sha.update(chunk)
                        output.write(chunk)
            if total<32 or b'ftyp' not in header[:32]:raise ValueError('返回内容不是有效 MP4 文件头')
            if expected and total!=int(expected):raise ValueError('视频下载长度不完整')
            value=sha.hexdigest()
            name=value+'.mp4'
            os.replace(temp,destination/name)
            return {'filename':name,'sha256':value,'bytes':total,'downloaded_at':time.time()}
        except (httpx.HTTPError,OSError,ValueError) as exc:
            last_error=exc
            temp.unlink(missing_ok=True)
            if attempt<2:time.sleep(attempt+1)
    raise RuntimeError(f'视频下载失败 ({urlparse(url).hostname}): {type(last_error).__name__}') from last_error


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent/'.env')
    from sqlalchemy import select
    from backend.business import BusinessStore,videos
    from backend.store import Config
    # Include unpublished videos too; never overwrite a concurrent metadata edit.
    business=BusinessStore(Config())
    root=media_root()
    try:
        with business.engine.connect() as db:
            rows=list(db.execute(select(videos.c.id,videos.c.video_url)).mappings())
        manifest=load_manifest(root)
        source_by_local={'/media/videos/'+entry['filename']:url for url,entry in manifest['videos'].items() if NAME.fullmatch(entry.get('filename',''))}
        sources=sorted({r['video_url'] if urlparse(r['video_url']).scheme in ('http','https') else source_by_local[r['video_url']]
                        for r in rows if urlparse(r['video_url']).scheme in ('http','https') or r['video_url'] in source_by_local})
        with ThreadPoolExecutor(max_workers=3) as executor:
            jobs={url:executor.submit(download,url,root,manifest['videos'].get(url,{})) for url in sources}
            results={url:job.result() for url,job in jobs.items()}
        for row in rows:
            if row['video_url'].startswith('/media/videos/'):
                name=row['video_url'].rsplit('/',1)[-1]
                if row['video_url'] not in source_by_local:
                    path=root/'videos'/name
                    if not NAME.fullmatch(name) or not path.is_file() or digest(path)!=name[:-4]:
                        raise ValueError(f"本地视频缺失或校验失败: {row['id']}")
        manifest['videos'].update(results)
        root.mkdir(parents=True,exist_ok=True)
        temporary=root/f'.manifest-{uuid4().hex}.json'
        temporary.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(temporary,root/'manifest.json')
        changed=0
        with business.engine.begin() as db:
            for row in rows:
                original=source_by_local.get(row['video_url'],row['video_url'])
                if original in results:
                    local='/media/videos/'+results[original]['filename']
                    if row['video_url']==local:continue
                    changed+=db.execute(videos.update().where(videos.c.id==row['id'],videos.c.video_url==row['video_url']).values(video_url=local)).rowcount
        total=sum(p.stat().st_size for p in (root/'videos').glob('*.mp4'))
        print({'catalog_videos':len(rows),'distinct_remote_sources':len(sources),'updated_urls':changed,
               'local_files':len(list((root/'videos').glob('*.mp4'))),'total_bytes':total,'directory':str(root/'videos')})
    finally:business.close()

if __name__=='__main__':main()
