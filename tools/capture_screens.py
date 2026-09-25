# -*- coding: utf-8 -*-
"""为报告生成最新界面截图，输出到 screenshots/（替换旧版截图）。

覆盖：登录/注册 → 学生（推荐/对比/检索/详情/画像/周报/收藏）
      → 教师（资源列表/上传）→ 管理员（看板/资源/用户/邀请码）

注意：不要使用 Emulation.setDeviceMetricsOverride —— 在 Edge 无头模式下
会让渲染 surface 失配，截出全白图；直接使用浏览器启动时的窗口尺寸即可，
长页面用滚动分段截。
"""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request

APP = 'http://127.0.0.1:8000'
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), 'screenshots')

if subprocess.run([sys.executable, os.path.join(HERE, 'start_browser.py')],
                  capture_output=True).returncode != 0:
    raise SystemExit('无头浏览器启动失败，请检查 Edge 是否安装')

targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9222/json', timeout=10).read())
# 必须定位到已打开本站的标签页，没有就新建一个：
# headless=new 启动时的初始 about:blank 标签页不参与渲染合成，在它上面操作与截图都会得到空白。
page = next((t for t in targets if t['type'] == 'page' and APP in (t.get('url') or '')), None)
if page is None:
    req = urllib.request.Request(
        'http://127.0.0.1:9222/json/new?' + urllib.parse.quote(APP + '/login', safe=''), method='PUT')
    page = json.loads(urllib.request.urlopen(req, timeout=10).read())
    print('已新建标签页:', (page.get('url') or '')[:60])
else:
    print('复用已有标签页:', (page.get('url') or '')[:60])

import websocket
ws = websocket.create_connection(page['webSocketDebuggerUrl'], timeout=30,
                                 origin='http://127.0.0.1:9222')
mid = [0]


def ev(expr):
    mid[0] += 1
    ws.send(json.dumps({'id': mid[0], 'method': 'Runtime.evaluate',
                        'params': {'expression': expr, 'awaitPromise': True, 'returnByValue': True}}))
    while True:
        m = json.loads(ws.recv())
        if m.get('id') == mid[0]:
            return m['result']['result'].get('value')


def shot(name, note=''):
    try:
        mid[0] += 1
        ws.send(json.dumps({'id': mid[0], 'method': 'Page.captureScreenshot', 'params': {'format': 'png'}}))
        while True:
            m = json.loads(ws.recv())
            if m.get('id') == mid[0]:
                path = os.path.join(OUT, name)
                with open(path, 'wb') as f:
                    f.write(base64.b64decode(m['result']['data']))
                kb = os.path.getsize(path) / 1024
                flag = 'OK ' if kb > 20 else '?? '          # < 20KB 基本是空白页
                print('  %s %-30s %7.0f KB  %s' % (flag, name, kb, note))
                return kb > 20
    except Exception as e:
        print('  !! 截图失败 %s: %s' % (name, type(e).__name__))
        return False


def click_text(text, sel="button, .el-button, .el-menu-item, .el-radio-button,"
                        " .el-tabs__item, .el-link, .el-dropdown, span, a"):
    res = ev("(function(){var t=Array.from(document.querySelectorAll(%r))"
             ".filter(e=>e.offsetParent!==null)"
             ".find(e=>e.textContent.trim().includes(%r));"
             "if(t){t.click();return t.tagName+'.'+(t.className||'').slice(0,26)}return '';})()"
             % (sel, text))
    print('       点击「%s」→ %s' % (text, res or '未找到'))
    return res


def wait_ready():
    for _ in range(25):
        if ev("!!(window.Vue && window.App && (document.querySelector('.nav-menu')"
              "|| document.querySelector('.login-panel')))"):
            return True
        time.sleep(1)
    return False


def goto(url):
    ev("sessionStorage.clear(); localStorage.clear(); location.href=%r;" % url)
    ok = wait_ready()
    time.sleep(2.5)
    return ok


def viewport_note():
    return ev("window.innerWidth+'x'+window.innerHeight")


os.makedirs(OUT, exist_ok=True)

print('== 未登录：登录 / 注册 ==')
goto(APP + '/login')
print('   视口:', viewport_note())
shot('01_login.png', '登录页')

click_text('注册')
time.sleep(1.5)
if ev("!!document.querySelector('.login-panel')"):
    shot('02_register_student.png', '注册页（学生）')
    click_text('教师')
    time.sleep(1.5)
    shot('03_register_teacher.png', '注册页（教师·邀请码）')

print('== 学生 student001 ==')
goto(APP + '/login?autologin=1')
click_text('个性化推荐'); time.sleep(3)
shot('11_recommend.png', '个性化推荐')
click_text('并排对比'); time.sleep(4.5)
ev("window.scrollTo(0, 0)"); time.sleep(1.5)      # 对比面板紧跟在工具栏下方，需在页面顶部
visible = ev("document.body.innerText.includes('三种推荐算法结果对比')")
print('       对比面板已渲染:', visible)
shot('12_recommend_compare.png', '三算法并排对比')

click_text('资源检索'); time.sleep(3)
shot('13_resources.png', '资源检索')
# 检索结果与收藏页都是卡片 / 表格两种可能，依次尝试点开详情
opened = ev("(function(){var r=document.querySelector('.el-table__row'); if(r){r.click();return 'row';}"
            "var c=document.querySelector('.el-col .el-card'); if(c){c.click();return 'card';}return '';})()")
time.sleep(3)
print('       打开详情方式:', opened or '未找到可点元素')
shot('14_resource_detail.png', '资源详情弹窗（含相似推荐）')
ev("document.querySelector('.el-dialog__headerbtn')&&document.querySelector('.el-dialog__headerbtn').click()")
time.sleep(1.2)

click_text('个人中心'); time.sleep(3.5)
shot('15_profile.png', '个人中心·用户画像')
ev("window.scrollTo(0, 700)"); time.sleep(2)
shot('16_weekly.png', '个人中心·学习周报')
ev("window.scrollTo(0, 0)"); time.sleep(1)
click_text('我的收藏'); time.sleep(3)
shot('17_favorites.png', '我的收藏')

print('== 教师 teacher01 ==')
goto(APP + '/login?autologin=1&user=teacher')
click_text('教师工作台'); time.sleep(3)
shot('21_teacher_resources.png', '教师·我的资源（审核状态）')
click_text('上传新资源'); time.sleep(2)
shot('22_teacher_upload.png', '教师·上传资源弹窗')
ev("document.querySelector('.el-dialog__headerbtn')&&document.querySelector('.el-dialog__headerbtn').click()")
time.sleep(1)

print('== 管理员 admin ==')
goto(APP + '/login?autologin=1&user=admin')
click_text('管理后台'); time.sleep(4)
shot('31_admin_dashboard.png', '数据看板')
ev("window.scrollTo(0, 500)"); time.sleep(1.5)
shot('31b_admin_dashboard_lower.png', '数据看板·下半')
ev("window.scrollTo(0, 0)"); time.sleep(1)
click_text('资源管理'); time.sleep(3)
shot('32_admin_resources.png', '资源管理')
click_text('用户管理'); time.sleep(3)
shot('33_admin_users.png', '用户管理')
click_text('邀请码'); time.sleep(2.5)
shot('34_admin_invites.png', '教师邀请码')

ws.close()
print('\n完成，screenshots/ 现有：')
for f in sorted(os.listdir(OUT)):
    print('   %-34s %7.0f KB' % (f, os.path.getsize(os.path.join(OUT, f)) / 1024))
