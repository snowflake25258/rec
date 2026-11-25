"""User accounts and opaque bearer sessions.

Passwords are stored as PBKDF2-HMAC-SHA256 hashes with an individual salt. Session
tokens are random, only their SHA-256 digest is persisted, and tokens expire after a
configurable number of days. Accounts are the only access gate; this
module provides actual user identity.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from typing import Any

from sqlalchemy import (Column, Double, ForeignKey, Index, String, Table, delete,
                        select, update)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from backend.business import metadata, users

PASSWORD_ALGORITHM = 'pbkdf2_sha256'
PASSWORD_ITERATIONS = 600_000
PASSWORD_SALT_BYTES = 16
PASSWORD_KEY_BYTES = 32
USERNAME_PATTERN = r'^[a-zA-Z0-9_]{3,32}$'

# Credentials are kept apart from ``users``: creators and legacy event users do not
# need a login, and adding new tables avoids altering the existing users rows.
accounts = Table('accounts', metadata,
    Column('user_id', String(64), ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('username', String(64), nullable=False),
    Column('password_hash', String(255), nullable=False),
    Column('created_at', Double, nullable=False),
    Column('last_login_at', Double, nullable=False))
auth_sessions = Table('auth_sessions', metadata,
    Column('token_hash', String(64), primary_key=True),
    Column('user_id', String(64), ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
    Column('created_at', Double, nullable=False),
    Column('expires_at', Double, nullable=False),
    Column('last_seen_at', Double, nullable=False),
    Column('user_agent', String(255), nullable=False, default=''))
Index('ux_accounts_username', accounts.c.username, unique=True)
Index('ix_auth_sessions_user', auth_sessions.c.user_id)
Index('ix_auth_sessions_expiry', auth_sessions.c.expires_at)
for table in (accounts, auth_sessions):
    table.dialect_options['mysql']['charset'] = 'utf8mb4'
    table.dialect_options['mysql']['collate'] = 'utf8mb4_bin'
    table.dialect_options['mysql']['engine'] = 'InnoDB'


class AuthError(Exception):
    """Base class for expected account errors."""


class UsernameTaken(AuthError):
    pass


class InvalidCredentials(AuthError):
    pass


def normalize_username(username: str) -> str:
    return username.strip().lower()


def hash_password(password: str, *, iterations: int = PASSWORD_ITERATIONS) -> str:
    salt = secrets.token_bytes(PASSWORD_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations,
                                 dklen=PASSWORD_KEY_BYTES)
    return '$'.join((PASSWORD_ALGORITHM, str(iterations),
                     base64.b64encode(salt).decode('ascii'),
                     base64.b64encode(digest).decode('ascii')))


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split('$')
        if algorithm != PASSWORD_ALGORITHM:
            return False
        rounds = int(iterations)
        if not 1 <= rounds <= 10_000_000:
            return False
        digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'),
                                     base64.b64decode(salt, validate=True), rounds,
                                     dklen=PASSWORD_KEY_BYTES)
        return hmac.compare_digest(digest, base64.b64decode(expected, validate=True))
    except (ValueError, TypeError):
        return False


_dummy_hash: str | None = None


def _dummy_password_hash() -> str:
    """A valid hash used for unknown users so missing accounts cost the same."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password(secrets.token_urlsafe(16))
    return _dummy_hash


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


class AuthService:
    def __init__(self, engine: Engine, token_ttl_days: int = 30) -> None:
        self.engine = engine
        self.token_ttl = max(1, min(int(token_ttl_days), 365)) * 86_400
        # New tables are created independently of the existing business schema.
        accounts.create(self.engine, checkfirst=True)
        auth_sessions.create(self.engine, checkfirst=True)

    @staticmethod
    def _user(row: Any) -> dict[str, Any]:
        return dict(id=row['id'], username=row['username'], name=row['name'], avatar=row['avatar'])

    def _issue(self, db, user_id: str, user_agent: str, now: float) -> tuple[str, float]:
        token = secrets.token_urlsafe(32)
        expires_at = now + self.token_ttl
        db.execute(delete(auth_sessions).where(auth_sessions.c.expires_at <= now))
        db.execute(auth_sessions.insert().values(
            token_hash=_token_digest(token), user_id=user_id, created_at=now,
            expires_at=expires_at, last_seen_at=now,
            user_agent=(user_agent or '')[:255]))
        return token, expires_at

    def register(self, username: str, password: str, name: str = '',
                 user_agent: str = '') -> dict[str, Any]:
        username = normalize_username(username)
        display_name = (name or '').strip() or username
        now = time.time()
        try:
            with self.engine.begin() as db:
                exists = db.execute(select(accounts.c.user_id).where(
                    accounts.c.username == username)).first()
                if exists is not None:
                    raise UsernameTaken('用户名已被使用')
                user_id = 'u' + secrets.token_hex(8)
                while db.execute(select(users.c.id).where(users.c.id == user_id)).first() is not None:
                    user_id = 'u' + secrets.token_hex(8)
                db.execute(users.insert().values(id=user_id, name=display_name, avatar='Y'))
                db.execute(accounts.insert().values(
                    user_id=user_id, username=username, password_hash=hash_password(password),
                    created_at=now, last_login_at=now))
                token, expires_at = self._issue(db, user_id, user_agent, now)
        except IntegrityError as exc:
            raise UsernameTaken('用户名已被使用') from exc
        return {'token': token, 'token_type': 'bearer', 'expires_at': expires_at,
                'user': dict(id=user_id, username=username, name=display_name, avatar='Y')}

    def login(self, username: str, password: str, user_agent: str = '') -> dict[str, Any]:
        username = normalize_username(username)
        with self.engine.connect() as db:
            row = db.execute(select(users.c.id, users.c.name, users.c.avatar,
                                    accounts.c.username, accounts.c.password_hash)
                             .select_from(accounts.join(users, users.c.id == accounts.c.user_id))
                             .where(accounts.c.username == username)).mappings().first()
        if row is None:
            verify_password(password, _dummy_password_hash())
            raise InvalidCredentials('用户名或密码错误')
        if not verify_password(password, row['password_hash']):
            raise InvalidCredentials('用户名或密码错误')
        now = time.time()
        with self.engine.begin() as db:
            db.execute(update(accounts).where(accounts.c.user_id == row['id'])
                       .values(last_login_at=now))
            token, expires_at = self._issue(db, row['id'], user_agent, now)
        return {'token': token, 'token_type': 'bearer', 'expires_at': expires_at,
                'user': dict(id=row['id'], username=row['username'], name=row['name'],
                             avatar=row['avatar'])}

    def authenticate(self, token: str) -> dict[str, Any] | None:
        if not token or len(token) > 256:
            return None
        digest = _token_digest(token)
        now = time.time()
        with self.engine.begin() as db:
            row = db.execute(select(users.c.id, users.c.name, users.c.avatar,
                                    accounts.c.username, auth_sessions.c.expires_at,
                                    auth_sessions.c.last_seen_at)
                             .select_from(auth_sessions
                                          .join(users, users.c.id == auth_sessions.c.user_id)
                                          .join(accounts, accounts.c.user_id == users.c.id))
                             .where(auth_sessions.c.token_hash == digest)).mappings().first()
            if row is None:
                return None
            if row['expires_at'] <= now:
                db.execute(delete(auth_sessions).where(auth_sessions.c.token_hash == digest))
                return None
            if now - row['last_seen_at'] > 300:
                db.execute(update(auth_sessions).where(auth_sessions.c.token_hash == digest)
                           .values(last_seen_at=now))
        return self._user(row)

    def logout(self, token: str) -> None:
        if not token:
            return
        with self.engine.begin() as db:
            db.execute(delete(auth_sessions).where(
                auth_sessions.c.token_hash == _token_digest(token)))

    def close(self) -> None:
        """Kept symmetrical with other services; the engine is owned elsewhere."""
