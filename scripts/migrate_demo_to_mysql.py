"""Copy the earlier local demo into MySQL without overwriting existing rows."""
from __future__ import annotations
from pathlib import Path
import json
import sqlite3
from dotenv import load_dotenv


def rows(path: Path,table: str) -> list[dict]:
    if not path.is_file():
        return []
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as source:
        source.row_factory=sqlite3.Row
        exists=source.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()
        if not exists:
            return []
        # Table identifiers are provided only by the fixed internal table list.
        return [dict(row) for row in source.execute(f'SELECT * FROM "{table}"')]


def main() -> None:
    load_dotenv('.env')
    from backend.store import Config, Store
    from backend.business import BusinessStore, metadata
    from backend.training.artifacts import load
    config=Config()
    if config.business_backend!='mysql' or config.mode!='demo':
        raise ValueError('Demo migration requires MySQL with REC_MODE=demo; stop streaming writers first')
    business=BusinessStore(config)
    analytics=Store(config,business.engine)
    copied={}
    try:
        with business.engine.begin() as db:
            for name in ['users','videos','video_interactions','follows','event_outbox','model_versions']:
                entries=rows(Path('runtime/business.sqlite3'),name)
                for record in entries:
                    for field in ['metrics','payload']:
                        if field in record and isinstance(record[field],str):
                            record[field]=json.loads(record[field])
                    if name=='model_versions':
                        record['active']=False  # Preserve the current online model selection.
                        if record['metrics'].get('status')=='ready':
                            load(Path(record['artifact_path']),record['metrics']['sha256'])
                        elif record['metrics'].get('status') in ('queued','running'):
                            record['metrics']={**record['metrics'],'status':'failed','error':'旧演示任务在迁移时已中断'}
                    business.upsert(db,metadata.tables[name],record)
                copied[name]=len(entries)
            events=rows(Path('runtime/events.sqlite3'),'events')
            for event in events:
                analytics._append_sql(db,event)
            copied['source_events']=len(events)
        print('Demo migration complete (existing rows preserved):',copied)
        print('MySQL total events:',len(analytics.events()))
    finally:
        analytics.close()
        business.close()

if __name__=='__main__':
    main()
