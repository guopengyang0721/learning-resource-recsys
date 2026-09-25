# -*- coding: utf-8 -*-
"""防暴力破解测试（前提：服务已重启，内存限流状态为空）：
A. 连续 5 次错密码 → 锁定 → 锁定期内正确密码被拒
B. 进程内单元测试：锁定期满逻辑（同进程模拟时间流逝）
C. 密保答案防猜测（集成，5 次错答案 → 429）
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend'))
BASE = 'http://127.0.0.1:8000'
USER = 'student042'


def call(u, token=None, data=None, method=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(u, data=body, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=20)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


print('== A. 登录锁定（服务端集成）==')
for i in range(4):
    s, r = call(BASE + '/api/auth/login', data={'username': USER, 'password': f'wrong{i}'})
    print(f'   第{i+1}次错:', s)
s, r = call(BASE + '/api/auth/login', data={'username': USER, 'password': 'wrong5'})
print('   第5次错:', s, '|', r.get('detail'))
s, r = call(BASE + '/api/auth/login', data={'username': USER, 'password': '123456'})
print('   锁定期内正确密码:', s, r.get('detail'), '(应 429)')

print('\n== B. 锁定期满逻辑（进程内单元，同进程模拟时间流逝）==')
import app.ratelimit as rl
rl._attempts.clear()
for i in range(5):
    rl.record_failure('unituser')
left = rl.remaining_lock_seconds('unituser')
print('   5 次失败后剩余锁定秒数:', left, '(应 > 0)')
rl._attempts['unituser']['locked_until'] = time.time() - 1   # 模拟时间流逝到期
print('   到期后剩余:', rl.remaining_lock_seconds('unituser'), '(应 0)')
print('   到期后再失败从零计数:', rl.record_failure('unituser'), '(应 0，未达阈值)')
rl._attempts.clear()

print('\n== C. 密保答案防猜测（服务端集成，独立用户）==')
import random
uname = 'bf%d' % random.randint(1000, 9999)
s, r = call(BASE + '/api/auth/register', data={
    'username': uname, 'password': 'test123456', 'nickname': '防猜测试',
    'sec_question': '你的出生城市是？', 'sec_answer': '西安'})
print('   注册(带密保):', s)
for i in range(5):
    s, r = call(BASE + '/api/auth/forgot-password',
                data={'username': uname, 'answer': f'bad{i}', 'new_password': 'xxxx66'})
print('   连续 5 次错答案:', s, '|', r.get('detail'))
s, r = call(BASE + '/api/auth/forgot-password',
            data={'username': uname, 'answer': '西安', 'new_password': 'xxxx66'})
print('   正确答案仍被拦:', s, r.get('detail'), '(应 429)')
