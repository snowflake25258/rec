from __future__ import annotations
import hashlib
import time
from sqlalchemy import select, update
from backend.auth import accounts, auth_sessions
from backend.tests.test_recommendations import client, register
import backend.main as main

def test_register_stores_hash_and_token_digest(client):
    headers, data = register(client, 'Alice', 'password123', '爱丽丝')
    assert data['user']['username'] == 'alice'
    assert data['user']['name'] == '爱丽丝'
    token = data['token']
    assert client.get('/api/auth/me', headers=headers).json()['user']['username'] == 'alice'
    with main.business.engine.connect() as db:
        account = db.execute(select(accounts)).mappings().one()
        session = db.execute(select(auth_sessions)).mappings().one()
    assert account['password_hash'].startswith('pbkdf2_sha256$')
    assert 'password123' not in account['password_hash']
    assert session['token_hash'] == hashlib.sha256(token.encode()).hexdigest()
    assert session['token_hash'] != token

def test_duplicate_username_is_case_insensitive(client):
    register(client, 'Alice', 'password123')
    response = client.post('/api/auth/register', json={'username': 'alice', 'password': 'password456'})
    assert response.status_code == 409

def test_login_and_wrong_password(client):
    register(client, 'alice', 'password123')
    assert client.post('/api/auth/login', json={'username': 'alice', 'password': 'wrong-pass'}).status_code == 401
    response = client.post('/api/auth/login', json={'username': 'ALICE', 'password': 'password123'})
    assert response.status_code == 200
    data = response.json()
    assert data['token']
    assert client.get('/api/auth/me', headers={'Authorization': f"Bearer {data['token']}"}).status_code == 200

def test_logout_revokes_token(client):
    headers, data = register(client, 'alice', 'password123')
    assert client.post('/api/auth/logout', headers=headers).status_code == 204
    assert client.get('/api/auth/me', headers=headers).status_code == 401
    assert client.post('/api/auth/login', json={'username': 'alice', 'password': 'password123'}).status_code == 200

def test_expired_session_is_rejected(client):
    headers, data = register(client, 'alice', 'password123')
    with main.business.engine.begin() as db:
        db.execute(update(auth_sessions).where(
            auth_sessions.c.token_hash == hashlib.sha256(data['token'].encode()).hexdigest()
        ).values(expires_at=time.time() - 1))
    assert client.get('/api/auth/me', headers=headers).status_code == 401

def test_credential_validation(client):
    assert client.post('/api/auth/register', json={'username': 'ab', 'password': 'password123'}).status_code == 422
    assert client.post('/api/auth/register', json={'username': 'bad name', 'password': 'password123'}).status_code == 422
    assert client.post('/api/auth/register', json={'username': 'alice', 'password': 'short'}).status_code == 422

def test_auth_routes_are_public(client):
    response = client.post('/api/auth/register', json={'username': 'alice', 'password': 'password123'})
    assert response.status_code == 201
    token = response.json()['token']
    assert client.get('/api/auth/me').status_code == 401
    assert client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'}).status_code == 200
