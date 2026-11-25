"""Provision a distinct, fully downloaded source for every seeded video ID."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
from uuid import uuid4
import json
import math
import os
import subprocess
import time
from typing import Any
from dotenv import load_dotenv
from backend.media import media_root,load_manifest
from backend.video_metadata import video_metadata
from scripts.download_videos import digest

ROOT=Path(__file__).resolve().parent.parent
lock=Lock()


def save_entry(root: Path,url: str,entry: dict[str,Any]) -> None:
    with lock:
        data=load_manifest(root);data['videos'][url]=entry
        temp=root/f'.manifest-{uuid4().hex}.json'
        temp.write_text(json.dumps(data,ensure_ascii=False,indent=2))
        os.replace(temp,root/'manifest.json')


def fetch(source: dict[str,Any],root: Path,existing: dict[str,Any]) -> dict[str,Any]:
    folder=root/'videos';folder.mkdir(parents=True,exist_ok=True)
    path=folder/existing.get('filename','missing')
    if path.is_file() and path.stat().st_size==existing.get('bytes') and digest(path)==existing.get('sha256'):
        return {**existing,**video_metadata(path)}
    part=folder/f'.{source["id"]}-unique.part'
    result=subprocess.run(['curl','--fail','--location','--continue-at','-','--retry','2','--retry-delay','1',
        '--connect-timeout','10','--max-time','180','--max-filesize','33554432','--silent','--show-error',
        '--output',str(part),source['source_url']],capture_output=True,text=True)
    if result.returncode:raise RuntimeError(f'{source["id"]}: download failed: {result.stderr[-250:]}')
    with part.open('rb') as stream:
        if b'ftyp' not in stream.read(32):raise ValueError(f'{source["id"]}: not MP4')
    meta=video_metadata(part)
    sha=digest(part);name=sha+'.mp4'
    os.replace(part,folder/name)
    entry={'filename':name,'sha256':sha,'bytes':(folder/name).stat().st_size,'downloaded_at':time.time(),
           'source_page':source['source_page'],'license_url':source['license_url'],'quality':source['quality'],**meta}
    save_entry(root,source['source_url'],entry)
    return entry


def main() -> None:
    load_dotenv(ROOT/'.env')
    from sqlalchemy import select
    from backend.business import BusinessStore,videos
    from backend.store import Config
    sources=json.loads((ROOT/'backend/video_sources.json').read_text())
    if len(sources)!=24 or len({s['source_url'] for s in sources})!=24:
        raise ValueError('Expected 24 distinct source URLs')
    root=media_root();root.mkdir(parents=True,exist_ok=True)
    manifest=load_manifest(root)
    business=BusinessStore(Config())
    try:
        with business.engine.connect() as db:
            before={r.id:r.video_url for r in db.execute(select(videos.c.id,videos.c.video_url))}
        entries={}
        with ThreadPoolExecutor(max_workers=8) as executor:
            pending={executor.submit(fetch,s,root,manifest['videos'].get(s['source_url'],{})):s for s in sources}
            for future in as_completed(pending):
                source=pending[future];entries[source['id']]=future.result()
                print('Downloaded',source['id'],f'{len(entries)}/24',flush=True)
        if len({entry['sha256'] for entry in entries.values()})!=24:
            raise ValueError('Duplicate video CONTENT detected; catalog not updated')
        with business.engine.begin() as db:
            current={r.id:r.video_url for r in db.execute(select(videos.c.id,videos.c.video_url).with_for_update())}
            if any(current.get(s['id'])!=before.get(s['id']) or s['id'] not in current for s in sources):
                raise ValueError('Catalog changed during download; no URLs overwritten')
            for source in sources:
                entry=entries[source['id']]
                db.execute(videos.update().where(videos.c.id==source['id']).values(
                    video_url='/media/videos/'+entry['filename'],title=source['title'],cover=source['cover_url'],
                    duration=math.ceil(entry['duration_seconds'])))
        report={'videos':24,'unique_sources':24,'unique_content_hashes':24,
                'bytes':sum(entry['bytes'] for entry in entries.values()),'quality':'360p preview',
                'entries':[{**source,**entries[source['id']]} for source in sources]}
        (root/'unique-catalog.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print('Catalog updated:',{k:v for k,v in report.items() if k!='entries'},flush=True)
    finally:business.close()

if __name__=='__main__':main()
