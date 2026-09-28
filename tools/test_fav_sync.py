# -*- coding: utf-8 -*-
"""收藏列表同步测试：收藏操作后个人中心收藏数据立即更新"""
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


def click_menu(name):
    return ev('(function(){var t=Array.from(document.querySelectorAll(".nav-menu .el-menu-item"))'
              '.find(e=>e.textContent.includes("%s")); t&&t.click(); return "ok";})()' % name)


ev("sessionStorage.clear(); localStorage.clear(); location.href='/login?autologin=1';")
time.sleep(5)

# 个人中心 → 我的收藏，记录当前数量
click_menu('个人中心')
time.sleep(1.5)
ev('(function(){var b=Array.from(document.querySelectorAll(".el-radio-button")).find(e=>e.textContent.includes("我的收藏")); b&&b.click();})()')
time.sleep(1.5)
before = ev('document.body.innerText.match(/共收藏\\s*(\\d+)/)?.[1]')
cards_before = ev('document.querySelectorAll(".el-card .el-tag").length')  # 粗略
print('1 收藏前数量:', before)

# 去推荐页打开第一个详情并收藏
click_menu('个性化推荐')
time.sleep(1.5)
ev('(function(){var c=document.querySelector(".el-col .el-card"); c&&c.click();})()')
time.sleep(2)
ev('(function(){var bs=Array.from(document.querySelectorAll(".el-dialog button")).find(b=>b.textContent.includes("收藏")); bs&&bs.click();})()')
time.sleep(1.5)

# 回个人中心看数量
click_menu('个人中心')
time.sleep(1.5)
ev('(function(){var b=Array.from(document.querySelectorAll(".el-radio-button")).find(e=>e.textContent.includes("我的收藏")); b&&b.click();})()')
time.sleep(1.5)
after = ev('document.body.innerText.match(/共收藏\\s*(\\d+)/)?.[1]')
print('2 收藏操作后数量:', after, '(应比收藏前 +1 或提示已收藏)')

ws.close()
