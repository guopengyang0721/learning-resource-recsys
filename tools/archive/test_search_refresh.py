# -*- coding: utf-8 -*-
"""复现用户场景：登录 → 资源检索 → 刷新 → 数据应仍在"""
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


def click_tab(name):
    return ev('(function(){var t=Array.from(document.querySelectorAll(".el-tabs__item"))'
              '.find(e=>e.textContent.includes("%s")); t&&t.click(); return "ok";})()' % name)


time.sleep(4)
click_tab('资源检索')
time.sleep(2)
rows_before = ev('document.querySelectorAll(".el-table__body tbody tr").length')
print('1 进入检索页:', rows_before, '行数据')

print('2 刷新（模拟用户 F5）...')
ev('location.reload();')
time.sleep(6)
print('   刷新后 URL:', ev('location.pathname'), '| 激活页签:', ev('document.querySelector(".el-tabs__item.is-active")?.textContent.trim()'))
rows_after = ev('document.querySelectorAll(".el-table__body tbody tr").length')
print('   刷新后数据行数:', rows_after, '(应 > 0)')

# 验证筛选也正常：点类型"视频"复选
ev('(function(){var c=Array.from(document.querySelectorAll(".el-checkbox")).find(e=>e.textContent.includes("视频")); c&&c.querySelector("input").click();})()')
time.sleep(2)
rows_video = ev('document.querySelectorAll(".el-table__body tbody tr").length')
print('3 勾选"视频"筛选后行数:', rows_video, '(应 ≤ 刷新后行数)')

ws.close()
