"""Use an existing Kafka/Flink cluster without changing its installation."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.request import urlopen
from dotenv import load_dotenv, set_key

ROOT=Path(__file__).resolve().parent.parent


def prepare() -> None:
    from kafka import KafkaAdminClient
    from kafka.admin import NewTopic
    from kafka.errors import TopicAlreadyExistsError
    from backend.store import Config
    from backend.business import BusinessStore
    from backend.analytics_schema import metadata
    config=Config()
    with urlopen(config.flink_rest_url.rstrip('/')+'/overview',timeout=5) as response:
        cluster=json.load(response)
    print('Flink',cluster['flink-version'],'available slots',cluster['slots-available'],flush=True)
    admin=KafkaAdminClient(bootstrap_servers=config.kafka.split(','),request_timeout_ms=10000)
    try:
        if config.kafka_topic not in admin.list_topics():
            try:admin.create_topics([NewTopic(config.kafka_topic,3,1)])
            except TopicAlreadyExistsError:pass
        print('Kafka topic ready:',config.kafka_topic,flush=True)
    finally:admin.close()
    business=BusinessStore(config)
    try:metadata.create_all(business.engine)
    finally:business.close()


def submit() -> None:
    prepare()
    from backend.store import Config
    from infra.flink.render_sql import render, template_values
    from urllib.parse import urlparse
    config=Config()
    with urlopen(config.flink_rest_url.rstrip('/')+'/jobs/overview',timeout=5) as response:
        active=[j for j in json.load(response)['jobs']
                if j['name'].startswith('yingke-realtime-') and j['state'] not in ('FINISHED','FAILED','CANCELED')]
    if active:
        names=', '.join(f"{j['name']}({j['jid']})" for j in active)
        raise RuntimeError(f'已有实时作业运行：{names}。请先保存 savepoint 并停止旧作业，再提交 SQL Client 作业')
    home=Path(os.environ.get('FLINK_HOME','/usr/local/soft/flink-1.18.1'))
    executable=home/'bin/sql-client.sh'
    python=os.environ.get('FLINK_PYTHON','/usr/bin/python3')
    if not executable.is_file():raise ValueError('设置 FLINK_HOME 为已有 Flink 安装目录')
    if not Path(python).is_file():raise ValueError('设置 FLINK_PYTHON 为已有 PyFlink Python')
    parsed=urlparse(config.flink_rest_url)
    if not parsed.hostname:raise ValueError('FLINK_REST_URL 必须包含主机名')
    restore=[part.strip() for part in os.environ.get('FLINK_RESTORE_PATH','').split(',') if part.strip()]
    rendered=render((ROOT/'infra/flink/pipeline.sql').read_text(encoding='utf-8'),template_values(os.environ),restore)
    rendered_path=ROOT/'runtime/pipeline.rendered.sql'
    rendered_path.parent.mkdir(parents=True,exist_ok=True)
    rendered_path.write_text(rendered,encoding='utf-8')
    rendered_path.chmod(0o600)
    command=[str(executable),'-Drest.address='+parsed.hostname,
             '-Drest.port='+str(parsed.port or (443 if parsed.scheme=='https' else 8081)),
             '-Dexecution.runtime-mode=streaming',
             '-f',str(rendered_path),
             '--pyFiles',str(ROOT/'infra/flink/udfs.py'),
             '--pyExecutable',python]
    env=dict(os.environ)
    process=subprocess.run(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    output=process.stdout.replace(config.mysql_password,'[redacted]') if config.mysql_password else process.stdout
    (ROOT/'runtime/flink-submit.log').write_text(output)
    lines=output.splitlines()
    print('\n'.join(lines if len(lines)<60 else lines[:30]+['... full redacted log: runtime/flink-submit.log ...']+lines[-15:]),flush=True)
    if process.returncode:raise RuntimeError('Flink SQL Client 提交失败；查看 runtime/flink-submit.log')
    match=re.search(r'Job ID: ([a-f0-9]{32})',output)
    if not match:
        raise RuntimeError('提交成功但未识别到 Job ID；查看 runtime/flink-submit.log')
    job_id=match.group(1)
    set_key(str(ROOT/'.env'),'FLINK_JOB_ID',job_id)
    payload={'job_id':job_id,'name':'yingke-realtime-recommendations','rest_url':config.flink_rest_url}
    (ROOT/'runtime/flink-job.json').write_text(json.dumps(payload,ensure_ascii=False))
    print('Saved Flink job ID:',job_id)


def replay() -> None:
    from dataclasses import replace
    from backend.store import Config,Store
    from backend.business import BusinessStore
    config=Config()
    business=BusinessStore(config)
    source=Store(replace(config,mode='demo',seed_analytics=False),business.engine)
    sink=Store(replace(config,mode='production'),business.engine)
    try:
        events=source.events()
        for event in events:sink.append(event)
        print('Replayed historical events:',len(events),'(original event IDs preserved)')
    finally:sink.close();source.close();business.close()


def main() -> None:
    load_dotenv(ROOT/'.env')
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['prepare','submit','replay'])
    parser.add_argument('--restore',help='savepoint URI；作为单个 Statement Set 作业恢复')
    args=parser.parse_args()
    if args.restore:os.environ['FLINK_RESTORE_PATH']=args.restore
    {'prepare':prepare,'submit':submit,'replay':replay}[args.action]()

if __name__=='__main__':main()
