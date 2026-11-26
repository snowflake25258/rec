from __future__ import annotations
from pathlib import Path
import hashlib
from scripts.download_videos import download
from dataclasses import replace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import backend.main as main


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'config',replace(main.config,media_directory=str(tmp_path/'media')))
    app=FastAPI()
    app.add_api_route('/media/videos/{filename}',main.local_video,methods=['GET','HEAD'])
    with TestClient(app) as client:
        yield client


def test_local_video_supports_seek_and_head(client):
    payload=b'\x00\x00\x00\x18ftypmp42'+b'video-data'*256
    name=hashlib.sha256(payload).hexdigest()+'.mp4'
    root=Path(main.config.media_directory)/'videos'
    root.mkdir(parents=True)
    (root/name).write_bytes(payload)
    response=client.get('/media/videos/'+name,headers={'Range':'bytes=10-29'})
    assert response.status_code==206
    assert response.content==payload[10:30]
    assert response.headers['content-range']==f'bytes 10-29/{len(payload)}'
    assert response.headers['content-type']=='video/mp4'
    assert client.head('/media/videos/'+name).content==b''
    assert client.get('/media/videos/'+name,headers={'Range':'bytes=999999-'}).status_code==416
    assert client.get('/media/videos/not-a-video.mp4').status_code==404
    assert client.get('/media/videos/'+('a'*64)+'.mp4').status_code==404


def test_download_reuses_verified_file_without_network(tmp_path,monkeypatch):
    payload=b'\x00\x00\x00\x18ftypmp42'+b'data'*32
    digest=hashlib.sha256(payload).hexdigest()
    (tmp_path/'videos').mkdir()
    (tmp_path/'videos'/f'{digest}.mp4').write_bytes(payload)
    existing={'filename':digest+'.mp4','sha256':digest,'bytes':len(payload)}
    def fail(*args,**kwargs):raise AssertionError('Should reuse verified file')
    monkeypatch.setattr('scripts.download_videos.httpx.stream',fail)
    assert download('https://example.com/video.mp4',tmp_path,existing)==existing


def test_download_rejects_html_instead_of_saving_video(tmp_path,monkeypatch):
    import httpx
    import pytest
    transport=httpx.MockTransport(lambda request:httpx.Response(200,content=b'<html>temporary failure</html>',headers={'content-type':'text/html'}))
    with httpx.Client(transport=transport) as client:
        monkeypatch.setattr('scripts.download_videos.httpx.stream',lambda method,url,**kwargs:client.stream(method,url))
        monkeypatch.setattr('scripts.download_videos.time.sleep',lambda seconds:None)
        with pytest.raises(RuntimeError,match='下载失败'):
            download('https://example.com/bad.mp4',tmp_path,{})
    assert list((tmp_path/'videos').iterdir())==[]


def test_seed_catalog_uses_24_distinct_sources():
    from backend.catalog import SOURCES,catalog
    assert len(SOURCES)==len({v['source_url'] for v in SOURCES})==24
    assert len({v['source_page'] for v in SOURCES})==24
    items=catalog()
    assert len({v['video_url'] for v in items})==24
    assert len({v['title'] for v in items})==24
