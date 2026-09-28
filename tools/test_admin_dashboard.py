# -*- coding: utf-8 -*-
"""管理员数据看板渲染测试：三图表 + Top10 + 最近流水 + 子页切换回归"""
import base64
import json
import time
import urllib.parse
import urllib.request

import websocket

APP = 'http://127.0.0.1:8000'

targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9222/json', timeout=10).read())
page = next((t for t in targets if t['type'] == 'page' and APP in t.get('url', '')), None)
if page is None:
    req = urllib.request.Request(
        'http://127.0.0.1:9222/json/new?' + urllib.parse.quote(APP + '/login?autologin=1&user=admin', safe=''),
        method='PUT')
    page = json.loads(urllib.request.urlopen(req, timeout=10).read())
    print('新建页签:', page.get('url'))
else:
    print('复用页签:', page.get('url'))

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


def shot(name):
    mid[0] += 1
    ws.send(json.dumps({'id': mid[0], 'method': 'Page.captureScreenshot', 'params': {'format': 'png'}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get('id') == mid[0]:
            with open(name, 'wb') as f:
                f.write(base64.b64decode(msg['result']['data']))
            print('截图:', name)
            return


ev("sessionStorage.clear(); localStorage.clear(); location.href='http://127.0.0.1:8000/login?autologin=1&user=admin&tab=admin';")
ok = False
for i in range(25):
    ready = ev("!!(window.Vue && window.ElementPlus && window.App && document.querySelector('.nav-menu'))")
    if ready:
        ok = True
        print(f'应用就绪（{i}s 内），当前路径:', ev('location.pathname'))
        break
    time.sleep(1)
if not ok:
    raise SystemExit('应用未就绪')
time.sleep(3)                              # 等看板数据 + 图表动画

canvas = ev("document.querySelectorAll('#chart canvas, #chart-cat canvas, #chart-act canvas').length")
top_rows = ev("""(function(){var c=Array.from(document.querySelectorAll('.el-card')).find(x=>x.textContent.includes('热门资源'));
return c ? c.querySelectorAll('.el-table__row').length : -1;})()""")
log_rows = ev("""(function(){var c=Array.from(document.querySelectorAll('.el-card')).find(x=>x.textContent.includes('最近行为流水'));
return c ? c.querySelectorAll('.el-table__row').length : -1;})()""")
cards = ev("document.querySelectorAll('.el-statistic').length")
print(f'统计卡: {cards} 个 | 图表 canvas: {canvas}/3 | Top10 行数: {top_rows} | 流水行数: {log_rows}')
shot('shot_dashboard_first.png')

# 子页切换回归：切到资源管理再切回，v-if 重建后图表必须还能画出来
ev("(function(){var b=Array.from(document.querySelectorAll('.el-radio-button')).find(e=>e.textContent.includes('资源管理')); b&&b.click();})()")
time.sleep(1.5)
ev("(function(){var b=Array.from(document.querySelectorAll('.el-radio-button')).find(e=>e.textContent.includes('数据看板')); b&&b.click();})()")
time.sleep(3)
canvas2 = ev("document.querySelectorAll('#chart canvas, #chart-cat canvas, #chart-act canvas').length")
top_rows2 = ev("""(function(){var c=Array.from(document.querySelectorAll('.el-card')).find(x=>x.textContent.includes('热门资源'));
return c ? c.querySelectorAll('.el-table__row').length : -1;})()""")
print(f'切回后 canvas: {canvas2}/3 | Top10 行数: {top_rows2}')
shot('shot_dashboard_back.png')

passed = canvas == 3 and top_rows == 10 and log_rows == 30 and canvas2 == 3 and top_rows2 == 10
print('测试结论:', 'PASS ✅' if passed else 'FAIL ❌')
ws.close()
