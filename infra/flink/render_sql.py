"""Render the SQL Client pipeline and inject a statement-set savepoint restore."""
from __future__ import annotations
from pathlib import Path
from typing import Mapping, Sequence
import argparse
import os

STATEMENT_SET_MARKER = 'EXECUTE STATEMENT SET'


def escape_literal(value: str) -> str:
    """Escape a value that is already wrapped in single quotes by the template."""
    return value.replace("'", "''")


def mysql_jdbc_url(host: str, port: str, database: str) -> str:
    return (f'jdbc:mysql://{host}:{port}/{database}'
            '?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC')


def render(template: str, values: Mapping[str, str],
           restore_paths: Sequence[str] = ()) -> str:
    """Substitute ${NAME} placeholders and optionally prepend restore statements.

    The three INSERTs run inside one EXECUTE STATEMENT SET job, matching the
    single savepoint restore documented in Flink SQL.md.
    """
    for name, value in values.items():
        if not value:
            raise ValueError(f'{name} must not be empty')
        template = template.replace('${' + name + '}', escape_literal(value))

    paths = [path.strip() for path in restore_paths if path.strip()]
    if not paths:
        return template
    if len(paths) != 1:
        raise ValueError(f'restore requires one savepoint path, got {len(paths)}')
    if STATEMENT_SET_MARKER not in template:
        raise ValueError(f'pipeline is missing {STATEMENT_SET_MARKER}')
    restore = f"SET 'execution.savepoint.path' = '{escape_literal(paths[0])}';\n"
    return template.replace(STATEMENT_SET_MARKER, restore + STATEMENT_SET_MARKER, 1)


def template_values(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    env = os.environ if environ is None else environ
    host = env.get('MYSQL_HOST', '127.0.0.1')
    port = env.get('MYSQL_PORT', '3306')
    database = env.get('MYSQL_DATABASE', 'yingke')
    return {
        'KAFKA_BOOTSTRAP_SERVERS': env.get('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092'),
        'KAFKA_TOPIC': env.get('KAFKA_TOPIC', 'rec-events'),
        'MYSQL_JDBC_URL': env.get('MYSQL_JDBC_URL') or mysql_jdbc_url(host, port, database),
        'MYSQL_USER': env.get('MYSQL_USER', 'root'),
        'MYSQL_PASSWORD': env.get('MYSQL_PASSWORD', ''),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('template', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()

    restore = [path for path in os.environ.get('FLINK_RESTORE_PATH', '').split(',')]
    rendered = render(args.template.read_text(encoding='utf-8'), template_values(), restore)
    args.output.write_text(rendered, encoding='utf-8')
    try:
        args.output.chmod(0o600)
    except OSError:
        pass


if __name__ == '__main__':
    main()
