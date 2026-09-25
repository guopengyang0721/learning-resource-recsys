# -*- coding: utf-8 -*-
"""登录过期机制专项测试：
1. 普通登录 → 2h 会话令牌；记住我 → 7d 令牌
2. 过期令牌 → 401
3. 滑动续签：签发短 ttl 令牌，超过半周期后请求 → 响应头 X-Renewed-Token 出现且 exp 后移
4. 未过半 → 不续签
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend'))
from app.security import make_token   # noqa: E402

BASE = 'http://127.0.0.1:8000'


def call(u, token=None, data=None, method=None, headers_only=False):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(u, data=body, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=20)
        return resp.status, dict(resp.headers), json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), json.loads(e.read())


def decode_exp(token):
    body = token.rsplit('.', 1)[0]
    return json.loads(base64.urlsafe_b64decode(body))['exp']


time.sleep(9)

print('== 1. 普通登录（不勾记住我）==')
s, h, r = call(BASE + '/api/auth/login', data={'username': 'student001', 'password': '123456'})
sess_tok = r['token']
ttl = decode_exp(sess_tok) - int(time.time())
print('   状态:', s, '| remember:', r['remember'], '| expires_in:', r['expires_in'], '| 实际ttl≈', ttl, '(应≈7200)')

print('== 2. 记住我登录 ==')
s, h, r = call(BASE + '/api/auth/login', data={'username': 'student001', 'password': '123456', 'remember': True})
rem_tok = r['token']
ttl = decode_exp(rem_tok) - int(time.time())
print('   状态:', s, '| remember:', r['remember'], '| expires_in:', r['expires_in'], '| 实际ttl≈', ttl, '(应≈604800)')

print('== 3. 正常令牌访问(未过半,不应续签) ==')
s, h, r = call(BASE + '/api/resources?page=1&size=1', token=rem_tok)
hkeys = {k.lower() for k in h}
print('   状态:', s, '| X-Renewed-Token:', 'x-renewed-token' in hkeys, '(应 False)')

print('== 4. 过期令牌访问 → 401 ==')
old = make_token(2, 'student', ttl=1)
time.sleep(2)
s, h, r = call(BASE + '/api/resources', token=old)
print('   状态:', s, r.get('detail'), '(应 401)')

print('== 5. 滑动续签：短ttl令牌过半后访问 ==')
short = make_token(2, 'student', ttl=8)
exp1 = decode_exp(short)
time.sleep(5)                     # 剩 3s < 半周期 4s → 应续签
s, h, r = call(BASE + '/api/auth/verify', token=short)
renewed = h.get('x-renewed-token') or h.get('X-Renewed-Token')
print('   状态:', s, '| 下发新令牌:', bool(renewed), '(应 True)')
if renewed:
    p1 = json.loads(base64.urlsafe_b64decode(short.rsplit('.', 1)[0]))
    p2 = json.loads(base64.urlsafe_b64decode(renewed.rsplit('.', 1)[0]))
    print('   新令牌 exp 后移:', p2['exp'] > p1['exp'], '| 保持会话级 ttl:', p2['ttl'] == 8, '| rem 保留:', p2['rem'] == p1['rem'])
    s, h, r = call(BASE + '/api/auth/verify', token=renewed)
    print('   新令牌可用:', s, '(应 200)')

print('== 6. 老格式令牌(无ttl字段)兼容 ==')
legacy_payload = {'uid': 2, 'role': 'student', 'exp': int(time.time()) + 604800}
body = base64.urlsafe_b64encode(json.dumps(legacy_payload).encode()).decode()
import hashlib, hmac
from app.config import SECRET_KEY
sig = hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
legacy = f'{body}.{sig}'
s, h, r = call(BASE + '/api/auth/verify', token=legacy)
print('   状态:', s, '(应 200，兼容旧令牌)')
