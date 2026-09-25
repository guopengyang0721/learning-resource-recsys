# -*- coding: utf-8 -*-
"""删除用户功能验证：teacher01 恢复 + 新接口资源转匿名 + 前端删除按钮"""
import os
_PROJ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # 项目根（tools/archive 上溯三层）
import json
import time
import urllib.parse
import urllib.request
import urllib.error

import websocket

BASE = 'http://127.0.0.1:8000'


def api(path, method='GET', data=None, token=None):
    r = urllib.request.Request(BASE + urllib.parse.quote(path, safe=':/?&=%()'), method=method,
                               data=json.dumps(data).encode() if data is not None else None,
                               headers={'Content-Type': 'application/json',
                                        **({'Authorization': 'Bearer ' + token} if token else {})})
    try:
        return 200, json.loads(urllib.request.urlopen(r, timeout=25).read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


for i in range(30):
    try:
        api('/api/recommend/hot?limit=1')
        break
    except Exception:
        time.sleep(2)

print('== 1. teacher01 恢复核对 ==')
c, b = api('/api/auth/login', 'POST', {'username': 'teacher01', 'password': '123456'})
print(f'登录: [{c}]', b.get('nickname') or b.get('detail'))
T = b['token']
mr = api('/api/teacher/my-resources', token=T)[1]
print('我的资源:', len(mr['items']), '条 / 在线', len([x for x in mr['items'] if x['status'] == 'online']))
A = api('/api/auth/login', 'POST', {'username': 'admin', 'password': 'admin123'})[1]['token']
d = api('/api/admin/stats/dashboard', token=A)[1]
print(f'全局核对: 用户 {d["users"]} / 资源 {d["resources"]} / 评分 {d["scores"]}')

print('\n== 2. 带资源用户删除（资源应转匿名保留）==')
name = 'tempdel' + str(int(time.time()))[-5:]
c, b = api('/api/auth/register', 'POST', {'username': name, 'password': 'temp123456',
                                          'nickname': '待删临时教师'})
if c == 200:
    # 注册只能建学生；改库升级为教师的路径不存在，改用教师上传接口需 teacher 角色
    print('临时学生注册成功', b.get('user_id'), '（学生无上传权限，改由 teacher01 代传一条再转移署名测试）')
    tuid = b['user_id']
# 用 teacher01 上传一条资源，然后把 uploader 改成临时号（模拟"该用户名下有资源"）再删账号
up = api('/api/teacher/resources', 'POST', {'title': '待删账号的测试资源', 'category': '算法', 'type': 'doc',
                                            'difficulty': 3, 'url': 'https://example.com/tmp',
                                            'description': '删除账号测试用'}, token=T)[1]
rid = (up.get('resource') or {}).get('id') or up.get('id')
print('teacher01 上传测试资源 id =', rid)
import sqlite3
con = sqlite3.connect(os.path.join(_PROJ, 'backend', 'data', 'app.db'))
con.execute('UPDATE resource SET uploader_id=? WHERE id=?', (tuid, rid))
con.commit()
con.close()
print(f'已把资源署名转到临时账号 id={tuid}（模拟名下有 1 条资源）')
c, b2 = api(f'/api/admin/users/{tuid}', 'DELETE', token=A)
print(f'删除该账号: [{c}]', b2.get('message') or b2.get('detail'))
c, rb = api(f'/api/resources/{rid}', token=T)
print('资源是否仍存在:', c == 200, '| 上传者字段:', (rb.get('uploader') if isinstance(rb, dict) else '?'))
c, ar = api('/api/admin/resources?keyword=待删账号的测试资源', token=A)
hit = [x for x in ar.get('items', []) if x['id'] == rid]
print('管理后台可见:', bool(hit), '| uploader =', hit[0]['uploader'] if hit else '-')
# 清理这条测试资源
api(f'/api/admin/resources/{rid}', 'DELETE', token=A)
print('测试资源已清理')

print('\n== 3. 前端删除按钮 UI ==')
targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9222/json', timeout=10).read())
page = next((t for t in targets if t['type'] == 'page' and BASE in t.get('url', '')), None)
if page is None:
    req = urllib.request.Request('http://127.0.0.1:9222/json/new?'
                                 + urllib.parse.quote(BASE + '/login?autologin=1&user=admin', safe=''),
                                 method='PUT')
    page = json.loads(urllib.request.urlopen(req, timeout=10).read())
ws = websocket.create_connection(page['webSocketDebuggerUrl'], timeout=25, origin='http://127.0.0.1:9222')
mid = [0]


def ev(expr):
    mid[0] += 1
    ws.send(json.dumps({'id': mid[0], 'method': 'Runtime.evaluate',
                        'params': {'expression': expr, 'awaitPromise': True, 'returnByValue': True}}))
    while True:
        m = json.loads(ws.recv())
        if m.get('id') == mid[0]:
            return m['result']['result'].get('value')


ev("sessionStorage.clear(); localStorage.clear(); location.href='http://127.0.0.1:8000/login?autologin=1&user=admin';")
for i in range(25):
    if ev("!!(window.Vue && window.App && document.querySelector('.nav-menu'))"):
        break
    time.sleep(1)
time.sleep(2.5)
ev("(function(){var t=Array.from(document.querySelectorAll('.nav-menu .el-menu-item')).find(e=>e.textContent.includes('管理后台')); t&&t.click();})()")
time.sleep(2.5)
ev("(function(){var b=Array.from(document.querySelectorAll('.el-radio-button')).find(e=>e.textContent.includes('用户管理')); b&&b.click();})()")
time.sleep(2.5)
btns = ev("""(function(){
  var rows=document.querySelectorAll('.el-table__row');
  if(!rows.length) return 'no-rows';
  var b=Array.from(rows[0].querySelectorAll('.el-button')).map(x=>x.textContent.trim());
  return JSON.stringify(b);
})()""")
print('首行按钮:', btns)
# 点删除按钮，看确认框
ev("(function(){var r=document.querySelector('.el-table__row');"
   "var b=Array.from(r.querySelectorAll('.el-button')).find(x=>x.textContent.includes('删')); b&&b.click();})()")
time.sleep(1.5)
box = ev("(function(){var b=document.querySelector('.el-message-box'); return b? b.innerText.replace(/\\n/g,' | ') : '(未弹出)';})()")
print('确认框:', box)
ev("(function(){var b=document.querySelector('.el-message-box__btns .el-button'); b&&b.click();})()")  # 取消
time.sleep(1)
print('已取消（不实际删除）')
ws.close()
