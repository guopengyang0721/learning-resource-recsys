# -*- coding: utf-8 -*-
"""定点排查：教师工作台空卡之谜 + 详情弹窗"看了又看"渲染"""
import json
import time
import urllib.parse
import urllib.request

import websocket

APP = 'http://127.0.0.1:8000'

targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9222/json', timeout=10).read())
page = next((t for t in targets if t['type'] == 'page' and APP in t.get('url', '')), None)
if page is None:
    req = urllib.request.Request(
        'http://127.0.0.1:9222/json/new?' + urllib.parse.quote(APP + '/login?autologin=1', safe=''),
        method='PUT')
    page = json.loads(urllib.request.urlopen(req, timeout=10).read())
ws = websocket.create_connection(page['webSocketDebuggerUrl'], timeout=20, origin='http://127.0.0.1:9222')
mid = [0]


def ev(expr):
    mid[0] += 1
    ws.send(json.dumps({'id': mid[0], 'method': 'Runtime.evaluate',
                        'params': {'expression': expr, 'awaitPromise': True, 'returnByValue': True}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get('id') == mid[0]:
            return msg['result']['result'].get('value')


def ready_and_errs():
    for i in range(25):
        if ev("!!(window.Vue && window.ElementPlus && window.App && document.querySelector('.nav-menu'))"):
            return True
        time.sleep(1)
    return False


# ---- 教师 ----
print('== 教师 teacher01 ==')
ev("sessionStorage.clear(); localStorage.clear(); location.href='http://127.0.0.1:8000/login?autologin=1&user=teacher';")
print('就绪:', ready_and_errs())
time.sleep(2)
page_fetch = ev("""(async function(){
  try {
    const me = JSON.parse(localStorage.getItem('me')||sessionStorage.getItem('me'));
    const r = await fetch('/api/teacher/my-resources', {headers:{Authorization:'Bearer '+me.token}});
    const j = await r.json();
    return JSON.stringify({status: r.status, n: (j.items||[]).length, first: (j.items||[])[0] ? (j.items[0].title||'').slice(0,20) : '-'});
  } catch(e) { return 'ERR ' + e; }
})()""")
print('页面内直接调 my-resources:', page_fetch)
ev("(function(){var t=Array.from(document.querySelectorAll('.nav-menu .el-menu-item'))"
   ".find(e=>e.textContent.includes('教师工作台')); t&&t.click();})()")
time.sleep(3)
cards = ev("document.querySelectorAll('.el-col .el-card').length")
empty = ev("!!document.querySelector('.el-empty')")
tag_txt = ev("(function(){var t=document.querySelector('.el-col .el-card .el-tag'); return t? t.textContent : '-';})()")
print(f'工作台: 卡片 {cards} | 空态显示 {empty} | 首卡状态标签 {tag_txt}')

# ---- 学生：详情弹窗 ----
print('== 学生 详情弹窗 ==')
ev("sessionStorage.clear(); localStorage.clear(); location.href='http://127.0.0.1:8000/login?autologin=1';")
print('就绪:', ready_and_errs())
time.sleep(2)
ev("(function(){var t=Array.from(document.querySelectorAll('.nav-menu .el-menu-item'))"
   ".find(e=>e.textContent.includes('资源检索')); t&&t.click();})()")
time.sleep(2.5)
ev("(function(){var b=Array.from(document.querySelectorAll('.el-table__row .el-button'))"
   ".find(x=>x.textContent.includes('详情')); b&&b.click();})()")
time.sleep(3)
dlg_vis = ev("(function(){var d=document.querySelector('.el-dialog');"
             "return d? getComputedStyle(d).display !== 'none' : false;})()")
dlg_text = ev("(function(){var d=document.querySelector('.el-dialog');"
              "return d? d.innerText.replace(/\\n/g,' | ').slice(0,300) : '(无)';})()")
print('弹窗可见:', dlg_vis)
print('含「看了又看」:', '看了又看' in (dlg_text or ''))
print('文本:', dlg_text)
ws.close()
