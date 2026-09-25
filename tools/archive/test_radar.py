# -*- coding: utf-8 -*-
"""复现用户场景：信息页 → 我的足迹 → 回到信息页，雷达图必须仍在"""
import json
import time
import urllib.request

import websocket

targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9222/json', timeout=10).read())
page = next((t for t in targets if t['type'] == 'page' and '127.0.0.1:8000' in t.get('url', '')), None)
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


def click_sub(name):
    return ev('(function(){var b=Array.from(document.querySelectorAll(".el-radio-button"))'
              '.find(e=>e.textContent.includes("%s")); b&&b.click(); return "ok";})()' % name)


def canvas_count():
    return ev('(function(){var d=document.getElementById("radar"); return d? d.querySelectorAll("canvas").length : "no-div";})()')


ev("sessionStorage.clear(); localStorage.clear(); location.href='/login?autologin=1';")
time.sleep(5)
ev("(function(){var t=Array.from(document.querySelectorAll('.nav-menu .el-menu-item')).find(e=>e.textContent.includes('个人中心')); t&&t.click();})()")
time.sleep(3)
print('1 首次进入信息页 canvas:', canvas_count(), '(应 >=1)')

print('2 切到我的足迹再回来...')
click_sub('我的足迹'); time.sleep(1.5)
click_sub('个人信息'); time.sleep(1.5)
print('   canvas:', canvas_count(), '(修复前会是 0 或空)')

print('3 再切我的收藏再回来...')
click_sub('我的收藏'); time.sleep(1.5)
click_sub('个人信息'); time.sleep(1.5)
print('   canvas:', canvas_count(), '(应 >=1)')

print('4 切出去（资源检索）再回个人中心...')
ev("(function(){var t=Array.from(document.querySelectorAll('.nav-menu .el-menu-item')).find(e=>e.textContent.includes('资源检索')); t&&t.click();})()")
time.sleep(1.5)
ev("(function(){var t=Array.from(document.querySelectorAll('.nav-menu .el-menu-item')).find(e=>e.textContent.includes('个人中心')); t&&t.click();})()")
time.sleep(1.5)
print('   canvas:', canvas_count(), '(应 >=1)')

print('JS错误:', ev('JSON.stringify(window.__errs || [])'))
ws.close()
