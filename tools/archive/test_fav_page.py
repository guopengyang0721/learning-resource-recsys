# -*- coding: utf-8 -*-
"""收藏分页点击换页测试"""
import json
import time
import urllib.parse
import urllib.request

import websocket

APP = 'http://127.0.0.1:8000'

targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9222/json', timeout=10).read())
page = next((t for t in targets if t['type'] == 'page' and APP in t.get('url', '')), None)
if page is None:
    # 冷启动：经 CDP 新开一个应用页签（新版本 DevTools 要求 PUT）
    req = urllib.request.Request(
        'http://127.0.0.1:9222/json/new?' + urllib.parse.quote(APP + '/login?autologin=1', safe=''),
        method='PUT')
    page = json.loads(urllib.request.urlopen(req, timeout=10).read())
    print('新建页签:', page.get('url'))
else:
    print('复用页签:', page.get('url'))

ws = websocket.create_connection(page['webSocketDebuggerUrl'], timeout=15, origin='http://127.0.0.1:9222')
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
for i in range(25):                     # 等 Vue + Element Plus + 侧边菜单就绪（CDN 加载可能较慢）
    ready = ev("!!(window.Vue && window.ElementPlus && window.App && document.querySelector('.nav-menu'))")
    if ready:
        print(f'应用就绪（{i}s 内）')
        break
    time.sleep(1)
else:
    raise SystemExit('应用 25s 内未就绪，检查后端/CDN')
time.sleep(1)

ev("(function(){var t=Array.from(document.querySelectorAll('.nav-menu .el-menu-item')).find(e=>e.textContent.includes('个人中心')); t&&t.click();})()")
time.sleep(1.5)
ev('(function(){var b=Array.from(document.querySelectorAll(".el-radio-button")).find(e=>e.textContent.includes("我的收藏")); b&&b.click();})()')
time.sleep(2)

first_title = ev('(function(){var c=document.querySelector(".el-col .el-card b"); return c? c.textContent : "-";})()')
print('第 1 页首条:', first_title)

# 点击页码 2
ev('(function(){var items=document.querySelectorAll(".el-pagination .el-pager li");'
   'var t=Array.from(items).find(li=>li.textContent.trim()==="2"); t&&t.click();})()')
time.sleep(2)
second_title = ev('(function(){var c=document.querySelector(".el-col .el-card b"); return c? c.textContent : "-";})()')
active = ev('document.querySelector(".el-pagination .el-pager li.is-active")?.textContent.trim()')
print('点击页码 2 后激活页码:', active, '| 首条:', second_title, '(应与第 1 页不同)')

# 判定
ok = active == '2' and first_title != '-' and second_title != '-' and first_title != second_title
print('测试结论:', 'PASS ✅' if ok else 'FAIL ❌')

ws.close()
