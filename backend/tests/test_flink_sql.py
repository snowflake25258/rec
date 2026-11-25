from __future__ import annotations
from pathlib import Path
from infra.flink.render_sql import render, template_values

ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATE = ROOT / 'infra' / 'flink' / 'pipeline.sql'


def values() -> dict[str, str]:
    return {
        'KAFKA_BOOTSTRAP_SERVERS': 'kafka:9092',
        'KAFKA_TOPIC': 'rec-events',
        'MYSQL_JDBC_URL': 'jdbc:mysql://db:3306/yingke?useSSL=false',
        'MYSQL_USER': 'yingke',
        'MYSQL_PASSWORD': "pa'ss",
    }


def test_render_replaces_placeholders_and_escapes_password() -> None:
    sql = render(TEMPLATE.read_text(encoding='utf-8'), values())
    assert '${' not in sql
    assert "pa''ss" in sql
    assert sql.count('EXECUTE STATEMENT SET') == 1
    assert sql.count('INSERT INTO ') == 3


def test_restore_is_a_single_statement_before_the_statement_set() -> None:
    sql = render(TEMPLATE.read_text(encoding='utf-8'), values(), ['file:/savepoints/job1'])
    marker = "SET 'execution.savepoint.path' = 'file:/savepoints/job1';"
    assert marker in sql
    assert sql.index(marker) < sql.index('EXECUTE STATEMENT SET')


def test_restore_rejects_multiple_paths() -> None:
    try:
        render(TEMPLATE.read_text(encoding='utf-8'), values(), ['file:/a', 'file:/b'])
    except ValueError as error:
        assert 'one savepoint' in str(error)
    else:
        raise AssertionError('multiple savepoints must be rejected')


def test_template_values_builds_jdbc_url() -> None:
    result = template_values({'MYSQL_HOST': 'db', 'MYSQL_PORT': '3307',
                              'MYSQL_DATABASE': 'yingke', 'MYSQL_PASSWORD': 'secret'})
    assert result['MYSQL_JDBC_URL'].startswith('jdbc:mysql://db:3307/yingke?')
