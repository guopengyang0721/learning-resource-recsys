# -*- coding: utf-8 -*-
"""资源行点击修复验证：点行打开详情+记录浏览、点按钮不误触发、推荐页热门可点"""
import base64
import json
import time
import urllib.parse
import urllib.request

import websocket

BASE = 'http://127.0.0.1:8000'


def api(path, method='GET', data=None, token=None):
    r = urllib.request.Request(BASE + urllib.parse.quote(path, safe=':/?&=%()'), method=method,
                               data=json.dumps(data).encode() if data is not None else None,
                               headers={'Content-Type': 'application/json',
                                        **({'Authorization': 'Bearer ' + token} if token else {})})
    return json.loads(urllib.request.urlopen(r, timeout=20).read())


tok = api('/api/auth/login', method='POST', data={'username': 'student001', 'password': '123456'})['token']
h0 = len(api('/api/user/history?limit=200', token=tok)['items'])
print('操作前足迹条数:', h0)

targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9222/json', timeout=10).read())
page = next((t for t in targets if t['type'] == 'page' and BASE in t.get('url', '')), None)
if page is None:
    req = urllib.request.Request('http://127.0.0.1:9222/json/new?'
                                 + urllib.parse.quote(BASE + '/login?autologin=1', safe=''), method='PUT')
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


def shot(name):
    mid[0] += 1
    ws.send(json.dumps({'id': mid[0], 'method': 'Page.captureScreenshot', 'params': {'format': 'png'}}))
    while True:
        m = json.loads(ws.recv())
        if m.get('id') == mid[0]:
            open(__file__.rsplit('\\', 1)[0] + '\\' + name, 'wb').write(base64.b64decode(m['result']['data']))
            print('  📷', name)
            return


POPUP = "document.body.classList.contains('el-popup-parent--hidden')"
DLG_TITLE = ("(function(){var d=document.querySelector('.el-dialog');"
             "return d? d.innerText.replace(/\\n/g,' ').slice(0,50):''})()")

ev("sessionStorage.clear(); localStorage.clear(); location.href='http://127.0.0.1:8000/login?autologin=1';")
for i in range(25):
    if ev("!!(window.Vue && window.App && document.querySelector('.nav-menu'))"):
        break
    time.sleep(1)
time.sleep(2)

# ---- 1 检索页：点整行 ----
ev("(function(){var t=Array.from(document.querySelectorAll('.nav-menu .el-menu-item')).find(e=>e.textContent.includes('资源检索')); t&&t.click();})()")
time.sleep(2.5)
ev("document.querySelector('.el-table__row td')&&document.querySelector('.el-table__row td').click()")
time.sleep(2.5)
print('点整行 -> 弹窗打开:', ev(POPUP), '|', ev(DLG_TITLE))
shot('ui_12_row_click.png')
ev("document.querySelector('.el-dialog__headerbtn')&&document.querySelector('.el-dialog__headerbtn').click()")
time.sleep(1.2)
print('关闭后弹窗:', ev(POPUP))

# ---- 2 点行内收藏按钮（不应打开弹窗）----
ev("""(function(){var r=document.querySelector('.el-table__row');
  var b=Array.from(r.querySelectorAll('.el-button')).find(x=>x.textContent.includes('收藏')); b&&b.click();})()""")
time.sleep(2)
pop_after_fav = ev(POPUP)
fav_msg = ev("(function(){var m=document.querySelector('.el-message'); return m? m.innerText.trim():'(无提示)'})()")
print('点收藏按钮 -> 弹窗误开:', pop_after_fav, '| 提示:', fav_msg)
# 还原收藏状态
ev("""(function(){var r=document.querySelector('.el-table__row');
  var b=Array.from(r.querySelectorAll('.el-button')).find(x=>x.textContent.includes('收藏')); b&&b.click();})()""")
time.sleep(1.8)

# ---- 3 推荐页热门资源可点 ----
ev("(function(){var t=Array.from(document.querySelectorAll('.nav-menu .el-menu-item')).find(e=>e.textContent.includes('个性化推荐')); t&&t.click();})()")
time.sleep(2.5)
ev("""(function(){var els=document.querySelectorAll('.el-card div[style*="cursor:pointer"], .el-card div[style*="cursor: pointer"]');
  var t=Array.from(els).find(x=>x.textContent.includes('热度')); t&&t.click();})()""")
time.sleep(2.5)
print('点热门资源 -> 弹窗打开:', ev(POPUP), '|', ev(DLG_TITLE))
ev("document.querySelector('.el-dialog__headerbtn')&&document.querySelector('.el-dialog__headerbtn').click()")
time.sleep(1)

h1 = len(api('/api/user/history?limit=200', token=tok)['items'])
print(f'\n操作后足迹条数: {h1}（应比 {h0} 多 2 条浏览记录）')
print('结论:', 'PASS ✅' if ev(POPUP) is False and h1 >= h0 + 2 and pop_after_fav is False else '需复核')
ws.close()
