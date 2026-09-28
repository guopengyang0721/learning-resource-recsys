# -*- coding: utf-8 -*-
"""前端路由测试：/login 直达登录页 → 登录跳 / → 退出回 /login → 未登录访问 / 归位 /login"""
import json
import time
import urllib.request

import websocket

BASE = 'http://127.0.0.1:8000'


def http_get(path):
    try:
        resp = urllib.request.urlopen(BASE + path, timeout=10)
        return resp.status, resp.read().decode('utf-8', 'ignore')[:80]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'ignore')[:80]


print('== 服务端路由回退 ==')
print('/login   →', http_get('/login')[0], '(应 200 且为 index.html)')
print('不存在的路径 /xyz →', http_get('/xyz')[0], '(应 200)')
print('/api/不存在 →', http_get('/api/nonexist')[0], '(应 404 JSON)')

# ---- CDP 浏览器流程 ----
targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9222/json', timeout=10).read())
page = next((t for t in targets if t['type'] == 'page' and '127.0.0.1:8000' in t.get('url', '')), None)
if page:
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

    # 1. 清掉旧登录态，直接访问 /login
    ev("sessionStorage.clear(); localStorage.clear();")
    ev("location.href = '/login';")
    time.sleep(4)
    print('\n== 浏览器：访问 /login ==')
    print('URL:', ev('location.pathname'), '(应 /login)')
    print('是登录页:', ev('!!document.querySelector(".login-screen")'))

    # 2. 填表登录
    ev("(function(){var i=document.querySelectorAll('.login-main .el-input__inner');"
       "i[0].value='student001';i[0].dispatchEvent(new Event('input'));"
       "i[1].value='123456';i[1].dispatchEvent(new Event('input'));})()")
    ev("(function(){var bs=Array.from(document.querySelectorAll('.login-main button')).find(b=>b.textContent.includes('登'));bs.click();})()")
    time.sleep(3)
    print('\n== 登录后 ==')
    print('URL:', ev('location.pathname'), '(应 /)')
    print('登录态:', ev('document.body.innerText.includes("同学001")'))

    # 3. 退出
    ev("(function(){var bs=Array.from(document.querySelectorAll('button')).find(b=>b.textContent.includes('退出'));bs&&bs.click();})()")
    time.sleep(2)
    print('\n== 退出后 ==')
    print('URL:', ev('location.pathname'), '(应 /login)')
    print('是登录页:', ev('!!document.querySelector(".login-screen")'))

    # 4. 未登录直接访问 /
    ev("location.href = '/';")
    time.sleep(3)
    print('\n== 未登录访问 / ==')
    print('URL:', ev('location.pathname'), '(应被归位为 /login)')
    print('是登录页:', ev('!!document.querySelector(".login-screen")'))
    ws.close()
else:
    print('CDP 页面未找到（无浏览器调试实例），仅完成服务端部分')
