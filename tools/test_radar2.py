# -*- coding: utf-8 -*-
"""深入探测：切换子页后 section 值、radar div、renderRadar 是否被调用"""
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


def click_sub(name):
    return ev('(function(){var b=Array.from(document.querySelectorAll(".el-radio-button"))'
              '.find(e=>e.textContent.includes("%s")); b&&b.click(); return "ok";})()' % name)


# 挂钩 Vue nextTick 调用追踪（简单法：给 renderRadar 打补丁不可行，直接看状态）
ev("sessionStorage.clear(); localStorage.clear(); location.href='/login?autologin=1';")
time.sleep(5)
ev("(function(){var t=Array.from(document.querySelectorAll('.nav-menu .el-menu-item')).find(e=>e.textContent.includes('个人中心')); t&&t.click();})()")
time.sleep(3)
print('section:', ev('window.App.store.state.section'))
print('canvas:', ev('(function(){var d=document.getElementById("radar"); return d? d.querySelectorAll("canvas").length : "no-div";})()'))

click_sub('我的足迹'); time.sleep(1)
print('切足迹后 section:', ev('window.App.store.state.section'))
click_sub('个人信息'); time.sleep(1)
print('切回信息后 section:', ev('window.App.store.state.section'))
print('radar div:', ev('(function(){var d=document.getElementById("radar"); return d? ("exists "+d.offsetWidth+"x"+d.offsetHeight+" innerHTML:"+d.innerHTML.length) : "no-div";})()'))
print('portrait.total:', ev('window.App.store.state.portrait.total'))
# 手动触发 Vue 重渲染看是否数据在、视图在但 chart 没画
print('手动 echarts 重画:', ev('(function(){var d=document.getElementById("radar"); if(!d||!window.echarts) return "no"; var c=echarts.init(d); var dist=window.App.store.state.portrait.distribution; var cats=Object.keys(dist); c.setOption({radar:{indicator:cats.map(function(x){return {name:x,max:30}}),radius:"62%"},series:[{type:"radar",data:[{value:cats.map(function(x){return dist[x]}),areaStyle:{opacity:.35}}]}]}); return d.querySelectorAll("canvas").length;})()'))
ws.close()
