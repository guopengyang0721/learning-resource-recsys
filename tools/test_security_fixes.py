# -*- coding: utf-8 -*-
"""安全修复专项回归：提权/冒充/越权全部被拒 + 旧密码兼容 + 新哈希生效"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = 'http://127.0.0.1:8000'
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def api(path, method='GET', data=None, token=None):
    r = urllib.request.Request(BASE + urllib.parse.quote(path, safe=':/?&=%()'), method=method,
                               data=json.dumps(data).encode() if data is not None else None,
                               headers={'Content-Type': 'application/json',
                                        **({'Authorization': 'Bearer ' + token} if token else {})})
    try:
        return 200, json.loads(urllib.request.urlopen(r, timeout=60).read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


for i in range(40):
    try:
        api('/api/recommend/hot?limit=1')
        break
    except Exception:
        time.sleep(2)

results = []


def check(name, cond):
    results.append((name, cond))
    print(('✅' if cond else '❌'), name)


print('=== 1. 种子账号登录（旧哈希兼容 + 自动升级） ===')
c, b = api('/api/auth/login', 'POST', {'username': 'student001', 'password': '123456'})
check('旧格式密码可登录', c == 200 and b.get('token'))
S = b['token']
import sqlite3
con = sqlite3.connect(os.path.join(_PROJ, 'backend', 'data', 'app.db'))
fmt = con.execute("SELECT password_hash FROM user WHERE username='student001'").fetchone()[0]
con.close()
check('登录后哈希已自动升级为 pbkdf2', fmt.startswith('pbkdf2$'))

print('\n=== 2. 注册提权封锁 ===')
c, b = api('/api/auth/register', 'POST', {'username': 'hacker_probe', 'password': 'hack123',
                                          'nickname': '越权探测', 'role': 'admin'})
check('带 role=admin 注册被强制为学生', c == 200 and b.get('role') == 'student')
if c == 200:
    A = api('/api/auth/login', 'POST', {'username': 'admin', 'password': 'admin123'})[1]['token']
    uid = b['user_id']
    c2, b2 = api(f'/api/admin/users/{uid}', 'DELETE', token=A)
    check('探测账号已清理', c2 == 200)

print('\n=== 3. 行为上报身份伪造封锁 ===')
c, b = api('/api/behavior', 'POST', {'user_id': 999, 'resource_id': 1, 'action': 'view'}, token=S)
check('上报行为忽略伪造 user_id（写入本人）', c == 200)
con = sqlite3.connect(os.path.join(_PROJ, 'backend', 'data', 'app.db'))
w = con.execute("SELECT user_id FROM behavior_log ORDER BY id DESC LIMIT 1").fetchone()[0]
con.close()
check('最新行为记录归属 student001(id=2) 而非 999', w == 2)

print('\n=== 4. 收藏接口身份伪造封锁 ===')
c, b = api('/api/favorites/1?user_id=999', 'POST', token=S)
check('收藏忽略伪造 user_id（写入本人）', c == 200)
api('/api/favorites/1', 'DELETE', token=S)      # 还原

print('\n=== 5. 推荐越权封锁 ===')
c, b = api('/api/recommend/1?n=5', token=S)      # admin(id=1) 的推荐，用学生 token
check('学生查他人推荐被拒', c == 403)
c, b = api('/api/recommend/2?n=5', token=S)      # 本人
check('查自己的推荐正常', c == 200 and len(b.get('items', [])) > 0)

print('\n=== 6. 参数校验 ===')
c, b = api('/api/recommend/2?n=5&algo=hack', token=S)
check('非法算法被拒', c == 400)
c, b = api('/api/behavior', 'POST', {'resource_id': 1, 'action': 'rate', 'value': 99}, token=S)
check('评分越界(99)被拒', c == 422)
c, b = api('/api/resources?page=1&size=9999', token=S)
check('size 超上限被拒', c == 422)

print('\n=== 7. 管理员看板（聚合重构后） ===')
A = api('/api/auth/login', 'POST', {'username': 'admin', 'password': 'admin123'})[1]['token']
c, d = api('/api/admin/stats/dashboard', token=A)
check('看板数据完整', c == 200 and d.get('users') == 112 and len(d.get('category_dist', {})) == 7)
c, d2 = api('/api/admin/stats/recommend', token=A)
check('推荐统计接口正常', c == 200 and d2.get('users') == 112)

print()
ok = sum(1 for _, v in results if v)
print(f'结论: {ok}/{len(results)} 通过')
