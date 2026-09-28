# -*- coding: utf-8 -*-
"""UI 验证：学生登录 → 个人中心「升级为教师」按钮与弹窗。"""
import json
import time
import base64
import urllib.request

import websocket

BASE = 'http://127.0.0.1:8000'
targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9222/json', timeout=10).read())
page = [t for t in targets if t['type'] == 'page'][0]
ws = websocket.create_connection(page['webSocketDebuggerUrl'], timeout=40,
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


JS_FILL = ("(function(){const set=function(el,v){var s=Object.getOwnPropertyDescriptor("
           "window.HTMLInputElement.prototype,'value').set;s.call(el,v);"
           "el.dispatchEvent(new Event('input',{bubbles:true}));};"
           "var inputs=document.querySelectorAll('.login-main input');"
           "set(inputs[0],'upstu02');set(inputs[1],'stu123456');})()")

ev("sessionStorage.clear(); localStorage.clear(); "
   "location.href='http://127.0.0.1:8000/login';")
for _ in range(25):
    if ev('!!(window.Vue && window.App && window.ElementPlus)'):
        break
    time.sleep(1)
time.sleep(1.5)
ev(JS_FILL)
ev("(function(){var b=Array.from(document.querySelectorAll('.login-btn'))"
   ".find(function(x){return x.textContent.indexOf('登') >= 0;}); b&&b.click();})()")
time.sleep(4)
print('登录后菜单项:', ev("JSON.stringify(Array.from("
    "document.querySelectorAll('.nav-menu .el-menu-item')).map(x=>x.innerText.trim()))"))
ev("(function(){var x=Array.from(document.querySelectorAll('.nav-menu .el-menu-item'))"
   ".find(function(e){return e.textContent.indexOf('个人中心') >= 0;}); x&&x.click();})()")
time.sleep(3)
has_btn = ev("!!Array.from(document.querySelectorAll('.el-button'))"
             ".find(b=>b.textContent.indexOf('升级为教师') >= 0)")
print('学生看到「升级为教师」按钮:', has_btn)
ev("(function(){var b=Array.from(document.querySelectorAll('.el-button'))"
   ".find(function(b){return b.textContent.indexOf('升级为教师') >= 0;}); b&&b.click();})()")
time.sleep(1.5)
d = ev("(function(){var d=document.querySelector('.el-dialog');"
       " return d? d.innerText.replace(/\\n/g,' | ').slice(0,160) : '(未弹出)';})()")
print('升级弹窗:', d)
shot('ui_29_upgrade_dialog.png')
ws.close()
