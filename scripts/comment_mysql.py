"""仅同步已有业务库的中文表、字段注释，不运行种子数据或创建测试库。"""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL


def main() -> None:
    # Config 在导入时读取环境变量，必须先加载本地配置。
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
    from backend.store import Config
    from backend.business import metadata as business_metadata
    from backend import auth  # 注册账号与会话表到同一业务元数据中。
    from backend.analytics_schema import metadata as analytics_metadata
    from backend.schema_comments import sync_mysql_comments

    config = Config()
    url = URL.create('mysql+pymysql', username=config.mysql_user, password=config.mysql_password,
                     host=config.mysql_host, port=config.mysql_port, database=config.mysql_database,
                     query={'charset': 'utf8mb4'})
    engine = create_engine(url, connect_args={'connect_timeout': 5, 'read_timeout': 60, 'write_timeout': 60})
    try:
        changed = sync_mysql_comments(engine, (business_metadata, analytics_metadata))
        print(f'中文注释同步完成：数据库={config.mysql_database}，更新表数={changed}')
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
