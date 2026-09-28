# -*- coding: utf-8 -*-
"""分页跳页功能验证：4 处分页的 jumper 渲染 + 中文文案 + 实际跳页"""
import base64
import json
import time
import urllib.parse
import urllib.request

import websocket

APP = 'http://127.0.0.1:8000'
OUT = __file__.rsplit('\\', 1)[0]

targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9222/json', timeout=10).read())
page = next((t for t in targets if t['type'] == 'page' and APP in t.get('url', '')), None)
if page is None:
    req = urllib.request.Request(
        'http://127.0.0.1:9222/json/new?' + urllib.parse.quote(APP + '/login?autologin=1', safe=''),
        method='PUT')
    page = json.loads(urllib.request.urlopen(req, timeout=10).read())
ws = websocket.create_connection(page['webSocketDebuggerUrl'], timeout=25, origin='http://127.0.0.1:9222')
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
    try:
        mid[0] += 1
        ws.send(json.dumps({'id': mid[0], 'method': 'Page.captureScreenshot', 'params': {'format': 'png'}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get('id') == mid[0]:
                open(OUT + '\\' + name, 'wb').write(base64.b64decode(msg['result']['data']))
                print('  📷', name)
                return
    except Exception as e:
        print(f'  ⚠️ 截图失败: {type(e).__name__}')


def ready():
    for i in range(25):
        if ev("!!(window.Vue && window.ElementPlus && window.App && document.querySelector('.nav-menu'))"):
            return True
        time.sleep(1)
    return False


def jumper_info():
    return ev("""(function(){
      var j=document.querySelector('.el-pagination__jump');
      if(!j) return null;
      var inp=j.querySelector('input');
      var total=document.querySelector('.el-pagination__total');
      return JSON.stringify({jumpText:j.innerText.trim(), hasInput:!!inp,
        totalText: total? total.innerText.trim():''});
    })()""")


def goto_page(n):
    # Element Plus 跳页框：input 同步 v-model，浏览器原生 change（回车/blur）才提交
    ev("""(function(){
      var inp=document.querySelector('.el-pagination__jump input');
      inp.focus();
      inp.select();
      var setter=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
      setter.call(inp, '%d');
      inp.dispatchEvent(new Event('input',{bubbles:true}));
      inp.dispatchEvent(new Event('change',{bubbles:true}));
      inp.blur();
    })()""" % n)
    time.sleep(2.5)
    return ev("document.querySelector('.el-pagination .el-pager li.is-active')?.textContent.trim()")


def click_menu(t):
    ev("(function(){var x=Array.from(document.querySelectorAll('.nav-menu .el-menu-item'))"
       ".find(e=>e.textContent.includes('%s')); x&&x.click();})()" % t)


def click_radio(t):
    ev("(function(){var b=Array.from(document.querySelectorAll('.el-radio-button'))"
       ".find(e=>e.textContent.includes('%s')); b&&b.click();})()" % t)


findings = []

# ---- 学生：检索页 ----
ev("sessionStorage.clear(); localStorage.clear(); location.href='http://127.0.0.1:8000/login?autologin=1';")
assert ready(), '未就绪'
time.sleep(2.5)
click_menu('资源检索'); time.sleep(2.5)
info = jumper_info()
print('检索页 jumper:', info)
if not info or 'jumpText' not in json.loads(info):
    findings.append('检索页无跳页框')
else:
    d = json.loads(info)
    if not d['hasInput']:
        findings.append('检索页跳页框无输入框')
    if '前往' not in d['jumpText']:
        findings.append('检索页跳页文案非中文: ' + d['jumpText'])
active = goto_page(13)
first_row = ev("document.querySelector('.el-table__row')?.innerText.trim().slice(0,20)")
print('跳转到第 13 页 -> 激活页码:', active, '| 首行:', first_row)
if active != '13':
    findings.append(f'检索页跳页失败(激活={active})')
shot('ui_08_jumper_search.png')

# ---- 学生：收藏页 ----
click_menu('个人中心'); time.sleep(2)
click_radio('我的收藏'); time.sleep(2.5)
info2 = jumper_info()
active2 = goto_page(4)
t = ev("(function(){var c=document.querySelector('.el-col .el-card b'); return c? c.textContent : '-'})()")
print('收藏页 jumper:', info2, '-> 跳第 4 页 激活:', active2, '首卡:', t[:16])
if not info2:
    findings.append('收藏页无跳页框')
elif active2 != '4':
    findings.append(f'收藏页跳页失败(激活={active2})')

# ---- 管理员：资源管理 / 用户管理 ----
ev("sessionStorage.clear(); localStorage.clear(); location.href='http://127.0.0.1:8000/login?autologin=1&user=admin';")
assert ready(), '管理员未就绪'
time.sleep(2.5)
click_menu('管理后台'); time.sleep(2.5)
click_radio('资源管理'); time.sleep(2.5)
i3 = jumper_info()
a3 = goto_page(5)
print('资源管理 jumper:', i3, '-> 跳第 5 页 激活:', a3)
if not i3: findings.append('资源管理无跳页框')
elif a3 != '5': findings.append(f'资源管理跳页失败(激活={a3})')
shot('ui_09_jumper_admin.png')

click_radio('用户管理'); time.sleep(2.5)
i4 = jumper_info()
a4 = goto_page(3)
print('用户管理 jumper:', i4, '-> 跳第 3 页 激活:', a4)
if not i4: findings.append('用户管理无跳页框')
elif a4 != '3': findings.append(f'用户管理跳页失败(激活={a4})')

# 表格空态文案（中文语言包生效的旁证）
click_radio('数据看板'); time.sleep(2)

print('\n结论:', '全部通过 ✅' if not findings else '发现 %d 项:\n- %s' % (len(findings), '\n- '.join(findings)))
ws.close()
