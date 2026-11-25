"""Read-only probes of the configured Kafka topic and exact Flink job."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Any
import time
import httpx
from backend.store import Config

_cache: dict[tuple,tuple[float,list[dict[str,Any]]]]={}
_lock=Lock()


def kafka_status(config: Config) -> dict[str,Any]:
    from kafka import KafkaAdminClient
    client=None
    try:
        client=KafkaAdminClient(bootstrap_servers=config.kafka.split(','),request_timeout_ms=3000,
                               api_version_auto_timeout_ms=2000)
        topics=client.describe_topics([config.kafka_topic])
        healthy=bool(topics and topics[0].get('error_code',0)==0 and topics[0].get('partitions'))
        return {'name':'Kafka','status':'connected' if healthy else 'unavailable',
                'topic':config.kafka_topic,'partitions':len(topics[0].get('partitions',[])) if topics else 0}
    except Exception:
        return {'name':'Kafka','status':'unavailable','topic':config.kafka_topic}
    finally:
        if client:client.close()


def flink_status(config: Config) -> dict[str,Any]:
    if not config.flink_job_id:
        return {'name':'Flink SQL + Python UDF','status':'unconfigured'}
    try:
        base=config.flink_rest_url.rstrip('/')
        with httpx.Client(timeout=3,trust_env=False) as client:
            response=client.get(f'{base}/jobs/{config.flink_job_id}')
            response.raise_for_status()
            job=response.json()
            response=client.get(f'{base}/jobs/{config.flink_job_id}/checkpoints')
            response.raise_for_status()
            checkpoints=response.json()
        completed=checkpoints.get('latest',{}).get('completed') or {}
        healthy=job['state']=='RUNNING' and completed and time.time()*1000-completed['trigger_timestamp']<60000
        return {'name':'Flink SQL + Python UDF','status':'running' if healthy else 'degraded',
                'state':job['state'],'job_id':config.flink_job_id,
                'completed_checkpoints':checkpoints.get('counts',{}).get('completed',0),
                'checkpoint_path':completed.get('external_path'),
                'job_url':f'{base}/#/job/{config.flink_job_id}/overview'}
    except Exception:
        return {'name':'Flink SQL + Python UDF','status':'unavailable','job_id':config.flink_job_id}


def pipeline_status(config: Config) -> list[dict[str,Any]]:
    if config.mode!='production':
        return [{'name':'Kafka','status':'not_connected'},{'name':'Flink SQL + Python UDF','status':'not_connected'}]
    key=(config.kafka,config.kafka_topic,config.flink_rest_url,config.flink_job_id)
    with _lock:
        cached=_cache.get(key)
        if cached and time.monotonic()-cached[0]<5:return cached[1]
    with ThreadPoolExecutor(max_workers=2) as executor:
        kafka=executor.submit(kafka_status,config)
        flink=executor.submit(flink_status,config)
        result=[kafka.result(),flink.result()]
    with _lock:_cache[key]=(time.monotonic(),result)
    return result
