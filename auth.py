import hashlib
import os
import uuid
from database import get_user_by_username, create_session, get_session_user, delete_session


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return salt.hex() + ":" + key.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, key_hex = stored.split(":")
        salt = bytes.fromhex(salt_hex)
        key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
        return key.hex() == key_hex
    except Exception:
        return False


def login(username: str, password: str):
    user = get_user_by_username(username.strip().lower())
    if not user or not verify_password(password, user["password_hash"]):
        return None
    token = str(uuid.uuid4())
    create_session(token, user["id"])
    return {"token": token, "role": user["role"], "name": user["name"], "id": user["id"]}


def get_user_from_token(token: str):
    if not token:
        return None
    return get_session_user(token)


def logout(token: str):
    delete_session(token)
