# -*- coding: utf-8 -*-
"""聚焦探测：个人中心-个人信息子页的渲染内容"""
import json
import time
import urllib.request

import websocket

targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9222/json', timeout=10).read())
page = next(t for t in targets if t['type'] == 'page' and '127.0.0.1:8000' in t.get('url', ''))
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


time.sleep(1)
print('当前URL:', ev('location.href'))
print('激活页签:', ev('document.querySelector(".el-tabs__item.is-active")?.textContent.trim()'))
# 强制回到个人信息子页
print('点击个人信息按钮:', ev('(function(){var b=Array.from(document.querySelectorAll(".el-radio-button")).find(e=>e.textContent.includes("个人信息")); if(!b) return "BTN_NOT_FOUND"; (b.querySelector("input")||b).click(); return "clicked";})()'))
time.sleep(1.5)
print('含"编辑资料/密码"按钮:', ev('!!Array.from(document.querySelectorAll("button")).find(b=>b.textContent.includes("编辑资料"))'))
print('含"用户名":', ev('document.body.innerText.includes("用户名：")'))
print('兴趣标签区:', ev('document.body.innerText.includes("兴趣类别")'))
print('统计卡"我的收藏":', ev('document.body.innerText.includes("我的收藏")'))
print('信息区文本片段:', ev('(function(){var el=Array.from(document.querySelectorAll(".el-card")).find(c=>c.textContent.includes("编辑资料")); return el ? el.textContent.slice(0,150) : "CARD_NOT_FOUND";})()'))

ws.close()
