"""Initialize project schemas without changing existing databases or credentials."""
from __future__ import annotations
from pathlib import Path
import re
from dotenv import load_dotenv
from sqlalchemy import inspect, text
from sqlalchemy.dialects.mysql import FLOAT
import pymysql


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent/'.env')
    from backend.store import Config, Store
    from backend.business import BusinessStore
    from backend.auth import AuthService
    from backend.analytics_schema import metadata as analytics_metadata
    from backend.business import metadata as business_metadata
    from backend.schema_comments import sync_mysql_comments
    config=Config()
    if not re.fullmatch(r'[A-Za-z0-9_]{1,64}',config.mysql_database):
        raise ValueError('MYSQL_DATABASE must contain only letters, digits and underscores')
    with pymysql.connect(host=config.mysql_host,port=config.mysql_port,user=config.mysql_user,
                         password=config.mysql_password,connect_timeout=5) as db:
        with db.cursor() as cursor:
            cursor.execute(f'CREATE DATABASE IF NOT EXISTS `{config.mysql_database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin')
    business=BusinessStore(config)
    try:
        AuthService(business.engine, config.auth_token_ttl_days)
        analytics_metadata.create_all(business.engine)
        # Widen columns from the earlier prototype without deleting rows.
        with business.engine.begin() as connection:
            inspector=inspect(connection)
            for table,names in {'videos':['created_at'],'event_outbox':['created_at','delivered_at'],
                                'model_versions':['created_at'],'events':['weight'],
                                'user_item_features':['preference'],'item_hotness':['score']}.items():
                for column in inspector.get_columns(table):
                    if column['name'] in names and isinstance(column['type'],FLOAT):
                        nullability='NULL' if column['nullable'] else 'NOT NULL'
                        connection.execute(text(f"ALTER TABLE `{table}` MODIFY `{column['name']}` DOUBLE {nullability}"))
        # create_all 只负责缺失表；已有表的中文注释需要显式 ALTER 才会生效。
        changed = sync_mysql_comments(business.engine, (business_metadata, analytics_metadata))
        print(f'MySQL Chinese comments synchronized: tables={changed}')
        analytics=Store(config,business.engine)
        try:
            print(f'MySQL schema ready: {config.mysql_database}; videos={len(business.catalog())}; events={len(analytics.events())}')
        finally:
            analytics.close()
    finally:
        business.close()

if __name__=='__main__':
    main()
