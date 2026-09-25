# -*- coding: utf-8 -*-
"""UI 验证：排行榜页 / 推荐解释卡片 / 管理端导出下拉，逐处截图。"""
import base64
import json
import time
import urllib.request

import websocket

BASE = 'http://127.0.0.1:8000'
targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9222/json', timeout=10).read())
page = [t for t in targets if t['type'] == 'page'][0]
ws = websocket.create_connection(page['webSocketDebuggerUrl'], timeout=60,
                                 origin='http://127.0.0.1:9222')
mid = [0]


def ev(expr):
    mid[0] += 1
    ws.send(json.dumps({'id': mid[0], 'method': 'Runtime.evaluate',
                        'params': {'expression': expr, 'awaitPromise': True,
                                   'returnByValue': True}}))
    while True:
        m = json.loads(ws.recv())
        if m.get('id') == mid[0]:
            return m['result']['result'].get('value')


def shot(name):
    mid[0] += 1
    ws.send(json.dumps({'id': mid[0], 'method': 'Page.captureScreenshot',
                        'params': {'format': 'png'}}))
    while True:
        m = json.loads(ws.recv())
        if m.get('id') == mid[0]:
            with open(name, 'wb') as f:
                f.write(base64.b64decode(m['result']['data']))
            print('📷', name)
            return


def menu(text):
    ev("(function(){var x=Array.from(document.querySelectorAll('.nav-menu .el-menu-item'))"
       ".find(function(e){return e.textContent.indexOf('%s') >= 0;}); x&&x.click();})()" % text)


# 登录学生
ev("sessionStorage.clear(); localStorage.clear(); "
   "location.href='http://127.0.0.1:8000/login?autologin=1';")
for _ in range(25):
    if ev("!!(window.Vue && window.App && document.querySelector('.nav-menu'))"):
        break
    time.sleep(1)
time.sleep(2.5)

# 1 推荐解释卡片
ev("(function(){var x=Array.from(document.querySelectorAll('.nav-menu .el-menu-item'))"
   ".find(e=>e.textContent.indexOf('个性化推荐')>=0); x&&x.click();})()")
time.sleep(3.5)
reasons = ev("JSON.stringify(Array.from(document.querySelectorAll('.el-col-16 .el-card'))"
             ".slice(0,2).map(c=>c.innerText.split('\\n').filter(l=>l.indexOf('💡')>=0)[0]))")
print('推荐解释示例:', reasons)
shot('ui_30_explain.png')

# 2 排行榜页
menu('排行榜')
time.sleep(3)
medals = ev("JSON.stringify(Array.from(document.querySelectorAll('.el-card div'))"
            ".filter(d=>/🥇|🥈/.test(d.innerText)&&d.innerText.length<60)"
            ".slice(0,2).map(d=>d.innerText.replace(/\\n/g,' ')))")
print('排行榜前两名:', medals)
shot('ui_31_rank.png')

# 3 管理端导出下拉
ev("sessionStorage.clear(); localStorage.clear(); "
   "location.href='http://127.0.0.1:8000/login?autologin=1&user=admin';")
for _ in range(25):
    if ev("!!(window.Vue && window.App && document.querySelector('.nav-menu'))"):
        break
    time.sleep(1)
time.sleep(2.5)
menu('管理后台')
time.sleep(3.5)
ev("(function(){var b=Array.from(document.querySelectorAll('.el-button'))"
   ".find(x=>x.textContent.indexOf('导出数据')>=0); b&&b.click();})()")
time.sleep(1.5)
items = ev("JSON.stringify(Array.from(document.querySelectorAll('.el-dropdown-menu__item'))"
           ".map(x=>x.innerText.trim()))")
print('导出菜单:', items)
# 点导出用户 CSV（验证真实下载不报错即可）
ev("(function(){var it=Array.from(document.querySelectorAll('.el-dropdown-menu__item'))"
   ".find(x=>x.innerText.indexOf('用户数据')>=0); it&&it.click();})()")
time.sleep(3)
shot('ui_32_export.png')
ws.close()
