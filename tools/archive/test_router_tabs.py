# -*- coding: utf-8 -*-
"""页签路径同步测试：切页签变 URL / 刷新保持页签 / 角色守卫 / 前进后退"""
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


def click_tab(name):
    return ev('(function(){var t=Array.from(document.querySelectorAll(".el-tabs__item"))'
              '.find(e=>e.textContent.includes("%s")); if(!t) return "TAB_NOT_FOUND"; t.click(); return "clicked";})()' % name)


# 管理员登录
ev("sessionStorage.clear(); localStorage.clear();")
ev("location.href = '/login?autologin=1&user=admin';")
time.sleep(5)
print('1 登录后 URL:', ev('location.pathname'), '(应 /recommend 或 /)')
print('   激活页签:', ev('document.querySelector(".el-tabs__item.is-active")?.textContent.trim()'))

print('\n2 点击「资源检索」:')
print('  ', click_tab('资源检索'))
time.sleep(1)
print('   URL:', ev('location.pathname'), '(应 /search)')

print('\n3 点击「个人中心」:')
print('  ', click_tab('个人中心'))
time.sleep(1)
print('   URL:', ev('location.pathname'), '(应 /profile)')

print('\n4 点击「管理后台」:')
print('  ', click_tab('管理后台'))
time.sleep(1)
print('   URL:', ev('location.pathname'), '(应 /admin)')

print('\n5 刷新保持页签:')
ev('location.reload();')
time.sleep(5)
print('   URL:', ev('location.pathname'), '| 激活页签:', ev('document.querySelector(".el-tabs__item.is-active")?.textContent.trim()'), '(应仍是 管理后台)')

print('\n6 角色守卫：直接输 /profile（admin 有权）→')
ev("location.href='/profile';")
time.sleep(4)
print('   URL:', ev('location.pathname'), '| 页签:', ev('document.querySelector(".el-tabs__item.is-active")?.textContent.trim()'))

print('\n7 浏览器后退:')
ev('history.back();')
time.sleep(1.5)
print('   URL:', ev('location.pathname'), '| 激活:', ev('document.querySelector(".el-tabs__item.is-active")?.textContent.trim()'))

print('\n8 未登录守卫：清除登录态访问 /search')
ev("sessionStorage.clear(); localStorage.clear(); location.href='/search';")
time.sleep(4)
print('   URL:', ev('location.pathname'), '(应归位 /login) | 登录页:', ev('!!document.querySelector(".login-screen")'))

ws.close()
