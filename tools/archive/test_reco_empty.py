# -*- coding: utf-8 -*-
"""复现用户场景：登录 student001 → 个性化推荐页，抓取推荐请求状态与前端错误。"""
import json
import time
import urllib.request

import websocket

BASE = 'http://127.0.0.1:8000'
targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9222/json', timeout=10).read())
page = [t for t in targets if t['type'] == 'page'][0]
ws = websocket.create_connection(page['webSocketDebuggerUrl'], timeout=60,
                                 origin='http://127.0.0.1:9222')
mid = [0]


def send(m, p=None):
    mid[0] += 1
    ws.send(json.dumps({'id': mid[0], 'method': m, 'params': p or {}}))
    while True:
        r = json.loads(ws.recv())
        if r.get('id') == mid[0]:
            return r.get('result')


def ev(e):
    r = send('Runtime.evaluate', {'expression': e, 'awaitPromise': True, 'returnByValue': True})
    return r['result'].get('value')


send('Runtime.enable')
send('Network.enable')

# 登录
ev("sessionStorage.clear(); localStorage.clear(); "
   "location.href='http://127.0.0.1:8000/login?autologin=1';")
for _ in range(30):
    if ev("!!document.querySelector('.nav-menu')"):
        break
    time.sleep(1)
time.sleep(2)

print('身份:', ev("JSON.stringify({u:(JSON.parse(localStorage.getItem('me')||sessionStorage.getItem('me')||'{}')).username,"
                "r:(JSON.parse(localStorage.getItem('me')||sessionStorage.getItem('me')||'{}')).role,"
                "id:(JSON.parse(localStorage.getItem('me')||sessionStorage.getItem('me')||'{}')).user_id})"))
print('recList 长度:', ev('window.App.store.state.recList.length'))
print('recSource:', ev('window.App.store.state.recSource'))
print('me.user_id:', ev('window.App.store.state.me.user_id'))

# 手动再点一次刷新推荐，观察结果
ev("(function(){var b=Array.from(document.querySelectorAll('.el-button'))"
   ".find(x=>x.textContent.indexOf('刷新推荐')>=0); b&&b.click();})()")
time.sleep(4)
print('刷新后 recList:', ev('window.App.store.state.recList.length'))

# 直接在页面里调一次接口看返回
r = ev("(async function(){"
       "  const me = JSON.parse(localStorage.getItem('me')||sessionStorage.getItem('me'));"
       "  const resp = await fetch('/api/recommend/' + me.user_id + '?n=10&algo=user_cf',"
       "                            {headers:{Authorization:'Bearer '+me.token}});"
       "  const j = await resp.json().catch(()=>({}));"
       "  return resp.status + ' items=' + ((j.items||[]).length) + ' source=' + (j.source||JSON.stringify(j).slice(0,80));"
       "})()")
print('页面内直调接口:', r)

errs = ev("JSON.stringify(window.__errs||[])")
print('JS 错误:', errs)
ws.close()
