"""认证与安全工具 —— 密码哈希（PBKDF2 加盐）、登录令牌（滑动过期）、接口鉴权依赖"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import REMEMBER_TTL, SECRET_KEY, SESSION_TTL
from app.db import get_db
from app.models import User

_PBKDF2_ROUNDS = 60_000        # 兼顾安全与响应速度（单次校验约 30ms）
_SALT_BYTES = 16


def hash_pwd(pwd: str) -> str:
    """PBKDF2-HMAC-SHA256 加盐哈希，格式 pbkdf2$<salt_hex>$<hash_hex>。

    历史上曾用无盐 SHA-256（见 verify_pwd 的兼容分支），新写入一律用本格式。
    """
    salt = secrets.token_bytes(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", pwd.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2${salt.hex()}${dk.hex()}"


def verify_pwd(pwd: str, stored: str) -> bool:
    """校验密码：支持新格式（加盐 PBKDF2）与旧格式（历史无盐 SHA-256）。"""
    if not stored:
        return False
    if stored.startswith("pbkdf2$"):
        try:
            _, salt_hex, hash_hex = stored.split("$")
            dk = hashlib.pbkdf2_hmac("sha256", pwd.encode("utf-8"),
                                     bytes.fromhex(salt_hex), _PBKDF2_ROUNDS)
            return hmac.compare_digest(dk.hex(), hash_hex)
        except (ValueError, TypeError):
            return False
    # 兼容旧库中的无盐 SHA-256
    return hmac.compare_digest(hashlib.sha256(pwd.encode("utf-8")).hexdigest(), stored)


def needs_rehash(stored: str) -> bool:
    """旧格式哈希在用户下次成功登录时可顺手升级为加盐格式。"""
    return bool(stored) and not stored.startswith("pbkdf2$")


def make_token(user_id: int, role: str, ttl: int = None, remember: bool = False) -> str:
    """签发令牌：负载含 uid/role/exp/ttl（本令牌有效期）/rem（是否记住我）。"""
    ttl = ttl or (REMEMBER_TTL if remember else SESSION_TTL)
    payload = {"uid": user_id, "role": role, "ttl": ttl, "rem": int(bool(remember)),
               "exp": int(time.time()) + ttl}
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    sig = hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{body}.{sig}"


def verify_token(token: str) -> dict:
    """校验登录令牌，无效/过期抛 401。"""
    try:
        body, sig = token.rsplit(".", 1)
        expect = hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(expect, sig):     # 常量时间比较，防时序侧信道
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(body))
        if payload.get("exp", 0) < time.time():
            raise ValueError
        return payload
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="登录状态无效或已过期")


_bearer = HTTPBearer(auto_error=False)


def get_current_user(request: Request,
                     cred: HTTPAuthorizationCredentials = Depends(_bearer),
                     db: Session = Depends(get_db)) -> User:
    """接口鉴权依赖：校验令牌 + 滑动续签。

    剩余寿命不足一半时签发全周期新令牌，写入 request.state.renewed_token，
    由中间件放入响应头 X-Renewed-Token 下发，前端自动替换本地令牌。
    """
    if cred is None:
        raise HTTPException(status_code=401, detail="未登录或缺少令牌")
    payload = verify_token(cred.credentials)
    u = db.get(User, payload.get("uid"))
    if not u:
        raise HTTPException(status_code=401, detail="用户不存在")
    if u.status == "disabled":
        raise HTTPException(status_code=403, detail="账号已被禁用，请联系管理员")
    # 滑动过期续签
    ttl = payload.get("ttl") or REMEMBER_TTL
    remaining = payload.get("exp", 0) - time.time()
    if remaining < ttl / 2:
        request.state.renewed_token = make_token(
            u.id, u.role, ttl=ttl, remember=bool(payload.get("rem")))
    return u


def require_roles(*roles):
    """角色权限依赖工厂：require_roles("teacher", "admin") 限定角色。"""
    def dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403,
                                detail=f"需要 {'/'.join(roles)} 角色权限")
        return user
    return dep


def require_admin(user: User = Depends(get_current_user)) -> User:
    """管理员权限依赖：非 admin 角色返回 403。"""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
