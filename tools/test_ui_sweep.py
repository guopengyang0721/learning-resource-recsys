# -*- coding: utf-8 -*-
"""UI 全页签巡检：学生 5 页签 + 教师工作台 + 管理员三子页，收集 JS 错误 + 关键渲染产物 + 截图"""
import base64
import json
import time
import urllib.parse
import urllib.request

import websocket

APP = 'http://127.0.0.1:8000'
OUT = __file__.rsplit('\\', 1)[0]

# 确保无头浏览器就绪（CDP 9222 未启动时自动拉起，profile 落在系统临时目录）
import os
import subprocess
import sys
_here = os.path.dirname(os.path.abspath(__file__))
if subprocess.run([sys.executable, os.path.join(_here, 'start_browser.py')],
                  capture_output=True).returncode != 0:
    raise SystemExit('无头浏览器启动失败，请检查 Edge 是否安装')

targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9222/json', timeout=10).read())
page = next((t for t in targets if t['type'] == 'page' and APP in t.get('url', '')), None)
if page is None:
    req = urllib.request.Request(
        'http://127.0.0.1:9222/json/new?' + urllib.parse.quote(APP + '/login?autologin=1', safe=''),
        method='PUT')
    page = json.loads(urllib.request.urlopen(req, timeout=10).read())

ws = websocket.create_connection(page['webSocketDebuggerUrl'], timeout=20, origin='http://127.0.0.1:9222')
mid = [0]
findings = []


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
        ws.settimeout(30)
        mid[0] += 1
        ws.send(json.dumps({'id': mid[0], 'method': 'Page.captureScreenshot', 'params': {'format': 'png'}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get('id') == mid[0]:
                with open(OUT + '\\' + name, 'wb') as f:
                    f.write(base64.b64decode(msg['result']['data']))
                print('  📷', name)
                return
    except Exception as e:
        print(f'  ⚠️ 截图失败 {name}: {type(e).__name__}（不影响检查项）')
    finally:
        ws.settimeout(20)


def click_menu(text):
    ev("(function(){var t=Array.from(document.querySelectorAll('.nav-menu .el-menu-item'))"
       ".find(e=>e.textContent.includes('%s')); t&&t.click();})()" % text)


def click_radio(text):
    ev("(function(){var b=Array.from(document.querySelectorAll('.el-radio-button'))"
       ".find(e=>e.textContent.includes('%s')); b&&b.click();})()" % text)


def wait_ready():
    for i in range(25):
        if ev("!!(window.Vue && window.ElementPlus && window.App && document.querySelector('.nav-menu'))"):
            return True
        time.sleep(1)
    return False


# ========== 学生视角 ==========
print('== 学生 student001 ==')
ev("sessionStorage.clear(); localStorage.clear(); location.href='http://127.0.0.1:8000/login?autologin=1';")
if not wait_ready():
    raise SystemExit('未就绪')
time.sleep(2)
ev("window.__errs=[]; window.addEventListener('error',e=>window.__errs.push(String(e.message)));"
   "window.addEventListener('unhandledrejection',e=>window.__errs.push('rejection:'+String(e.reason)));")

# 1 个性化推荐
click_menu('个性化推荐'); time.sleep(2.5)
cards = ev("document.querySelectorAll('.el-col .el-card').length")
errs = ev("window.__errs.length")
print(f'推荐页: 卡片 {cards} | JS错误 {errs}')
if cards < 1: findings.append('推荐页无卡片')
shot('ui_01_recommend.png')

# 2 资源检索
click_menu('资源检索'); time.sleep(2.5)
rows = ev("document.querySelectorAll('.el-table__row').length")
print(f'检索页: 表格行 {rows} (期望8)')
if rows != 8: findings.append(f'检索页行数 {rows}!=8')
shot('ui_02_search.png')

# 3 个人中心-信息(雷达)
click_menu('个人中心'); time.sleep(2.5)
canvas = ev("document.querySelectorAll('#radar canvas').length")
print(f'个人中心: 雷达 canvas {canvas}')
if canvas < 1: findings.append('雷达图未渲染')
shot('ui_03_profile_info.png')

# 4 足迹
click_radio('我的足迹'); time.sleep(2)
hrows = ev("document.querySelectorAll('.el-table__row').length")
print(f'足迹页: 行 {hrows}')
if hrows < 1: findings.append('足迹为空')

# 5 收藏 + 翻页
click_radio('我的收藏'); time.sleep(2)
fav_cards = ev("document.querySelectorAll('.el-col .el-card').length")
t1 = ev("(function(){var c=document.querySelector('.el-col .el-card b');return c?c.textContent:'-'})()")
ev("(function(){var li=Array.from(document.querySelectorAll('.el-pagination .el-pager li'))"
   ".find(x=>x.textContent.trim()==='2'); li&&li.click();})()"); time.sleep(2)
t2 = ev("(function(){var c=document.querySelector('.el-col .el-card b');return c?c.textContent:'-'})()")
pag_ok = t1 != t2 and t2 != '-'
print(f'收藏页: 首页卡 {fav_cards} | 翻页换数据 {pag_ok} ({t1[:12]}→{t2[:12]})')
if not pag_ok: findings.append('收藏翻页未换数据')
shot('ui_04_favs_page2.png')

# 6 详情弹窗（嵌套相似推荐）
ev("(function(){var c=document.querySelector('.el-col .el-card'); c&&c.click();})()"); time.sleep(2.5)
dlg = ev("!!document.querySelector('.el-dialog')")
sim_n = ev("(function(){var d=document.querySelector('.el-dialog');"
           "return d? d.querySelectorAll('.el-card').length : -1;})()")
print(f'详情弹窗: 打开 {dlg} | 相似卡片 {sim_n}')
if not dlg: findings.append('详情弹窗未打开')
ev("document.querySelector('.el-dialog__headerbtn')&&document.querySelector('.el-dialog__headerbtn').click()")
time.sleep(1)

# 7 通知中心
bell_n = ev("(function(){var b=document.querySelector('.el-badge'); return b? true:false;})()")
print(f'通知铃铛存在: {bell_n}')

errs_all = ev("JSON.stringify(window.__errs||[])")
print('学生全程 JS 错误:', errs_all)
if errs_all not in ('[]', None) and json.loads(errs_all or '[]'):
    findings.append('学生页 JS 错误: ' + errs_all[:200])

# ========== 教师视角 ==========
print('== 教师 teacher01 ==')
ev("sessionStorage.clear(); localStorage.clear(); location.href='http://127.0.0.1:8000/login?autologin=1&user=teacher';")
if not wait_ready():
    raise SystemExit('教师登录未就绪')
time.sleep(2)
ev("window.__errs=[]; window.addEventListener('error',e=>window.__errs.push(String(e.message)));")
click_menu('教师工作台'); time.sleep(2.5)
tcards = ev("(function(){var n=document.querySelectorAll('.el-col .el-card').length; return n;})()")
print(f'教师工作台: 我的资源卡 {tcards}')
if tcards < 1: findings.append('教师工作台无资源卡')
shot('ui_05_teacher.png')

# ========== 管理员视角 ==========
print('== 管理员 admin ==')
ev("sessionStorage.clear(); localStorage.clear(); location.href='http://127.0.0.1:8000/login?autologin=1&user=admin';")
if not wait_ready():
    raise SystemExit('管理员登录未就绪')
time.sleep(2)
ev("window.__errs=[]; window.addEventListener('error',e=>window.__errs.push(String(e.message)));")
click_menu('管理后台'); time.sleep(3)
cv = ev("document.querySelectorAll('#chart canvas, #chart-cat canvas, #chart-act canvas').length")
print(f'数据看板: canvas {cv}/3')
if cv != 3: findings.append(f'看板 canvas {cv}/3')

click_radio('资源管理'); time.sleep(2.5)
arows = ev("document.querySelectorAll('.el-table__row').length")
print(f'资源管理: 表格行 {arows}')
if arows < 1: findings.append('资源管理表格空')
shot('ui_06_admin_resources.png')

click_radio('用户管理'); time.sleep(2.5)
urows = ev("document.querySelectorAll('.el-table__row').length")
print(f'用户管理: 表格行 {urows}')
if urows < 1: findings.append('用户管理表格空')
shot('ui_07_admin_users.png')
click_radio('数据看板'); time.sleep(2)

errs_all2 = ev("JSON.stringify(window.__errs||[])")
print('管理员 JS 错误:', errs_all2)
if errs_all2 not in ('[]', None) and json.loads(errs_all2 or '[]'):
    findings.append('管理员页 JS 错误: ' + errs_all2[:200])

print('\n结论:', '全部正常 ✅' if not findings else '发现 %d 项:\n- %s' % (len(findings), '\n- '.join(findings)))
ws.close()
