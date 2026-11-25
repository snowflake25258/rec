from __future__ import annotations
from dataclasses import replace
import time
import httpx
from backend.store import Config
from backend.pipeline import flink_status,pipeline_status


def test_demo_does_not_probe_live_cluster(monkeypatch):
    def fail(*args,**kwargs):raise AssertionError('demo must not touch cluster')
    monkeypatch.setattr('backend.pipeline.kafka_status',fail)
    assert all(p['status']=='not_connected' for p in pipeline_status(Config(mode='demo')))


def test_flink_running_requires_recent_checkpoint(monkeypatch):
    stale=[False]
    transport=httpx.MockTransport(lambda req:httpx.Response(200,json=
        {'latest':{'completed':{'trigger_timestamp':(time.time()-(120 if stale[0] else 0))*1000,'external_path':'file:/checkpoint'}},'counts':{'completed':3}}
        if req.url.path.endswith('checkpoints') else {'state':'RUNNING'}))
    original=httpx.Client
    monkeypatch.setattr('backend.pipeline.httpx.Client',lambda **kwargs:original(transport=transport,**kwargs))
    c=Config(mode='production',flink_job_id='a'*32)
    assert flink_status(c)['status']=='running'
    stale[0]=True
    assert flink_status(c)['status']=='degraded'
    assert flink_status(replace(c,flink_job_id=''))['status']=='unconfigured'
