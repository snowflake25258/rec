from __future__ import annotations
import pytest
from backend.auth import hash_password,verify_password,normalize_username


def test_password_hash_is_salted_and_verifiable():
    first=hash_password('password123')
    second=hash_password('password123')
    assert first!=second
    assert first.startswith('pbkdf2_sha256$')
    assert 'password123' not in first
    assert verify_password('password123',first)
    assert not verify_password('wrong-password',first)


@pytest.mark.parametrize('encoded',['invalid','other$10$abc$def','pbkdf2_sha256$0$abc$def','pbkdf2_sha256$10000001$abc$def'])
def test_malformed_hash_is_rejected(encoded):
    assert not verify_password('password123',encoded)


def test_username_normalization():
    assert normalize_username('  ALIce  ')=='alice'
