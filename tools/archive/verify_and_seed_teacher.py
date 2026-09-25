# -*- coding: utf-8 -*-
"""补充巡检：详情弹窗"看了又看"渲染核实 + 给 teacher01 补演示资源（上传→审核→上架）"""
import json
import time
import urllib.parse
import urllib.request

import websocket

BASE = 'http://127.0.0.1:8000'
APP = BASE


def api(path, method='GET', data=None, token=None):
    r = urllib.request.Request(BASE + urllib.parse.quote(path, safe=':/?&=%()'), method=method,
                               data=json.dumps(data).encode() if data is not None else None,
                               headers={'Content-Type': 'application/json',
                                        **({'Authorization': 'Bearer ' + token} if token else {})})
    return json.loads(urllib.request.urlopen(r, timeout=30).read())


# ---- 1 详情弹窗"看了又看"核实 ----
targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9222/json', timeout=10).read())
page = next((t for t in targets if t['type'] == 'page' and APP in t.get('url', '')), None)
if page is None:
    req = urllib.request.Request(
        'http://127.0.0.1:9222/json/new?' + urllib.parse.quote(APP + '/login?autologin=1', safe=''),
        method='PUT')
    page = json.loads(urllib.request.urlopen(req, timeout=10).read())
ws = websocket.create_connection(page['webSocketDebuggerUrl'], timeout=20, origin='http://127.0.0.1:9222')
mid = [0]


def ev(expr):
    mid[0] += 1
    ws.send(json.dumps({'id': mid[0], 'method': 'Runtime.evaluate',
                        'params': {'expression': expr, 'awaitPromise': True, 'returnByValue': True}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get('id') == mid[0]:
            return msg['result']['result'].get('value')


ev("sessionStorage.clear(); localStorage.clear(); location.href='http://127.0.0.1:8000/login?autologin=1';")
for i in range(25):
    if ev("!!(window.Vue && window.ElementPlus && window.App && document.querySelector('.nav-menu'))"):
        break
    time.sleep(1)
time.sleep(2)
ev("(function(){var t=Array.from(document.querySelectorAll('.nav-menu .el-menu-item'))"
   ".find(e=>e.textContent.includes('资源检索')); t&&t.click();})()")
time.sleep(2.5)
ev("document.querySelector('.el-table__row')&&document.querySelector('.el-table__row').click()")
time.sleep(3)
dlg_text = ev("(function(){var d=document.querySelector('.el-dialog'); return d? d.innerText.slice(0,400) : '';})()")
has_sim = '看了又看' in (dlg_text or '')
print('弹窗含「看了又看」:', has_sim)
print('弹窗文本预览:', (dlg_text or '')[:150].replace('\n', ' | '))
ws.close()

# ---- 2 给 teacher01 补演示资源 ----
print('\n== 补演示资源 ==')
tea = api('/api/auth/login', 'POST', {'username': 'teacher01', 'password': '123456'})
T = tea['token']
adm = api('/api/auth/login', 'POST', {'username': 'admin', 'password': 'admin123'})
A = adm['token']

demo = [
    {'title': '软件工程：结构化开发方法精讲', 'category': '软件工程', 'type': 'doc',
     'difficulty': 3, 'url': 'https://example.com/se-structured',
     'description': '从需求分析到总体设计的结构化开发全流程讲解，含课后练习。'},
    {'title': '机器学习实战：协同过滤从原理到编码', 'category': '机器学习', 'type': 'video',
     'difficulty': 4, 'url': 'https://example.com/ml-cf-video',
     'description': 'User-CF / Item-CF 手写实现与调参技巧，配套数据集。'},
    {'title': 'Web 数据挖掘课堂案例集', 'category': 'Web开发', 'type': 'ppt',
     'difficulty': 2, 'url': 'https://example.com/webmining-cases',
     'description': '爬虫、日志分析与推荐系统三类课堂案例的幻灯片合集。'},
]
mr = api('/api/teacher/my-resources', token=T)
have = {x['title'] for x in mr.get('items', [])}
for d in demo:
    if d['title'] in have:
        print('已存在，跳过:', d['title'])
        continue
    up = api('/api/teacher/resources', 'POST', d, token=T)
    rid = (up.get('resource') or {}).get('id') or up.get('id')
    api(f'/api/admin/resources/{rid}/status', 'PUT', {'status': 'online'}, token=A)
    print(f'上传并上架 id={rid}: {d["title"]}')

mr2 = api('/api/teacher/my-resources', token=T)
online = [x for x in mr2.get('items', []) if x.get('status') == 'online']
print('teacher01 名下资源:', len(mr2.get('items', [])), '条 / 在线', len(online), '条')
