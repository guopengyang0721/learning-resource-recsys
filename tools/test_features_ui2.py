# -*- coding: utf-8 -*-
"""补拍：推荐解释卡片 + 排行榜页（等待主界面就绪后再操作）。"""
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


def wait_main(timeout=40):
    for _ in range(int(timeout)):
        if ev("!!document.querySelector('.nav-menu')"):
            return True
        time.sleep(1)
    return False


def click_menu(text):
    ev("(function(){var x=Array.from(document.querySelectorAll('.nav-menu .el-menu-item'))"
       ".find(function(e){return e.textContent.indexOf('%s')>=0;}); x&&x.click();})()" % text)


ev("sessionStorage.clear(); localStorage.clear(); "
   "location.href='http://127.0.0.1:8000/login?autologin=1';")
time.sleep(3)
if not wait_main():
    raise SystemExit('主界面未就绪')
time.sleep(2)
click_menu('个性化推荐')
time.sleep(3.5)
reasons = ev("JSON.stringify((document.body.innerText.match(/💡[^\\n]+/g)||[]).slice(0,3))")
print('推荐解释示例:', reasons)
shot('ui_30_explain.png')

click_menu('排行榜')
time.sleep(3.5)
rows = ev("JSON.stringify((document.body.innerText.match(/🥇[^\\n]+|🥈[^\\n]+/g)||[]).slice(0,2))")
print('排行榜前两名:', rows)
shot('ui_31_rank.png')
ws.close()
