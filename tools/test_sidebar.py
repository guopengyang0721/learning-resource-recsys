# -*- coding: utf-8 -*-
"""侧边导航布局回归：菜单渲染、页面切换、角色过滤、URL 同步"""
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
              '.find(e=>e.textContent.includes("%s")); if(!t) return "NOT_FOUND"; t.click(); return "clicked";})()' % name)


ev("sessionStorage.clear(); localStorage.clear(); location.href='/login?autologin=1&user=admin';")
time.sleep(5)
print('1 登录后布局:', ev('!!document.querySelector(".side-nav")'), '| 侧栏菜单项:',
      ev('document.querySelectorAll(".nav-menu .el-menu-item").length'), '(admin 应 5)')
print('   页头标题:', ev('document.querySelector(".page-head h2")?.textContent'))
print('   用户卡昵称:', ev('document.querySelector(".nav-uinfo .un")?.textContent'))

for name, path, mark in [('资源检索', '/search', '关键词检索'),
                         ('个人中心', '/profile', '编辑资料'),
                         ('管理后台', '/admin', '数据看板')]:
    print(f'2 点击侧栏[{name}]:', click_menu(name))
    time.sleep(1.2)
    print('   URL:', ev('location.pathname'), '| 页头:', ev('document.querySelector(".page-head h2")?.textContent'),
          '| 内容含关键元素:', ev(f'document.body.innerText.includes("{mark}")'))

print('5 点击侧栏[个性化推荐]:', click_menu('个性化推荐'))
time.sleep(1.2)
print('   URL:', ev('location.pathname'), '| 推荐卡:', ev('document.querySelectorAll(".el-card").length > 0'))

ev("sessionStorage.clear(); localStorage.clear(); location.href='/profile';")
time.sleep(4)
print('6 学生越权路径守卫(清登录态访问 /profile):', ev('location.pathname'), '| 登录页:', ev('!!document.querySelector(".login-screen")'))

ws.close()
