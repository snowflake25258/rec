"""用元数据和模拟连接验证注释维护，不创建测试数据库。"""
from types import SimpleNamespace

from sqlalchemy import Column, MetaData, String, Table
from sqlalchemy.dialects.mysql import dialect
from sqlalchemy.schema import CreateTable

from backend import auth, schema_comments
from backend.business import metadata as business_metadata
from backend.analytics_schema import metadata as analytics_metadata


def test_all_tables_and_columns_have_chinese_comments() -> None:
    tables = [t for m in (business_metadata, analytics_metadata) for t in m.tables.values()]
    assert {t.name for t in tables} == set(schema_comments.TABLE_COMMENTS)
    for table in tables:
        assert any('\u4e00' <= ch <= '\u9fff' for ch in table.comment)
        sql = str(CreateTable(table).compile(dialect=dialect()))
        for column in table.columns:
            assert column.comment and column.comment in sql
        assert table.comment in sql


def test_comment_replacement_preserves_server_column_attributes() -> None:
    original = "`modified` timestamp(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '旧注释',"
    result = schema_comments.replace_column_comment(original, "'新注释'")
    assert result == original.removesuffix(" COMMENT '旧注释',") + " COMMENT '新注释'"


def test_comment_replacement_does_not_touch_quoted_default_text() -> None:
    original = "`value` varchar(100) DEFAULT 'x COMMENT ''keep''' COMMENT '旧\\'注释',"
    result = schema_comments.replace_column_comment(original, "'中文'")
    assert result == "`value` varchar(100) DEFAULT 'x COMMENT ''keep''' COMMENT '中文'"


def test_identical_comments_do_not_issue_ddl(monkeypatch) -> None:
    table = Table('sample', MetaData(), Column('id', String(64), comment='编号'), comment='示例')
    inspector = SimpleNamespace(get_columns=lambda name: [{'name': 'id', 'comment': '编号'}],
                                get_table_comment=lambda name: {'text': '示例'})
    monkeypatch.setattr(schema_comments, 'inspect', lambda connection: inspector)
    assert schema_comments.comment_sql(SimpleNamespace(dialect=dialect()), table) is None


def test_sync_uses_existing_type_and_default_not_orm_type(monkeypatch) -> None:
    table = Table('sample', MetaData(), Column('id', String(64), comment='编号'), comment='示例')
    inspector = SimpleNamespace(get_columns=lambda name: [{'name': 'id', 'comment': ''}],
                                get_table_comment=lambda name: {'text': ''})
    monkeypatch.setattr(schema_comments, 'inspect', lambda connection: inspector)
    ddl = "CREATE TABLE `sample` (\n  `id` varchar(128) NOT NULL DEFAULT 'kept',\n  PRIMARY KEY (`id`)\n)"
    connection = SimpleNamespace(dialect=dialect(), exec_driver_sql=lambda sql: SimpleNamespace(one=lambda: ('sample', ddl)))
    result = schema_comments.comment_sql(connection, table)
    assert "varchar(128) NOT NULL DEFAULT 'kept' COMMENT '编号'" in result
    assert 'varchar(64)' not in result
