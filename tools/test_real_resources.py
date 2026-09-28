# -*- coding: utf-8 -*-
"""真实资源替换验证：接口返回 / 搜索匹配 / 图表数据一致性 / 详情弹窗"去学习"按钮"""
import base64
import json
import time
import urllib.parse
import urllib.request

import websocket

BASE = 'http://127.0.0.1:8000'


def api(path, method='GET', data=None, token=None):
    r = urllib.request.Request(BASE + urllib.parse.quote(path, safe=':/?&=%()'), method=method,
                               data=json.dumps(data).encode() if data is not None else None,
                               headers={'Content-Type': 'application/json',
                                        **({'Authorization': 'Bearer ' + token} if token else {})})
    return json.loads(urllib.request.urlopen(r, timeout=25).read())


T = api('/api/auth/login', method='POST', data={'username': 'student001', 'password': '123456'})['token']
A = api('/api/auth/login', method='POST', data={'username': 'admin', 'password': 'admin123'})['token']

print('== 1. 检索与关键词匹配 ==')
for kw in ('机器学习', '数据库', 'Python', '算法'):
    b = api('/api/resources?size=4&keyword=' + kw, token=T)
    print(f'  关键词「{kw}」命中 {b["total"]} 条，前 2 条:',
          [x['title'] for x in b['items'][:2]])

print('\n== 2. 详情接口字段 ==')
d = api('/api/resources/23', token=T)
print('  id=23:', d['title'])
print('  url:', d['url'])
print('  描述:', d['description'])

print('\n== 3. 图表与推荐一致性 ==')
st = api('/api/admin/stats/dashboard', token=A)
print('  分类分布:', st['category_dist'])
print('  类型分布(行为):', st['action_count'])
print('  离线指标:', {k: v['precision'] for k, v in st['offline_metrics']['results'].items()})
rec = api(f'/api/recommend/2?n=5&algo=user_cf', token=T)
print('  user_cf 推荐 5 条:', [x['title'] for x in rec['items'][:3]])
print('  热门 Top3:', [x['title'] for x in api('/api/resources?size=3&sort=hot', token=T)['items']])
print('  评分榜 Top3:', [x['title'] for x in api('/api/resources?size=3&sort=rating', token=T)['items']])

print('\n== 4. 详情弹窗「去学习」按钮 ==')
targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9222/json', timeout=10).read())
page = next((t for t in targets if t['type'] == 'page' and BASE in t.get('url', '')), None)
if page is None:
    req = urllib.request.Request('http://127.0.0.1:9222/json/new?'
                                 + urllib.parse.quote(BASE + '/login?autologin=1', safe=''), method='PUT')
    page = json.loads(urllib.request.urlopen(req, timeout=10).read())
ws = websocket.create_connection(page['webSocketDebuggerUrl'], timeout=25, origin='http://127.0.0.1:9222')
mid = [0]


def ev(expr):
    mid[0] += 1
    ws.send(json.dumps({'id': mid[0], 'method': 'Runtime.evaluate',
                        'params': {'expression': expr, 'awaitPromise': True, 'returnByValue': True}}))
    while True:
        m = json.loads(ws.recv())
        if m.get('id') == mid[0]:
            return m['result']['result'].get('value')


ev("sessionStorage.clear(); localStorage.clear(); location.href='http://127.0.0.1:8000/login?autologin=1';")
for i in range(25):
    if ev("!!(window.Vue && window.App && document.querySelector('.nav-menu'))"):
        break
    time.sleep(1)
time.sleep(2)
ev("(function(){var t=Array.from(document.querySelectorAll('.nav-menu .el-menu-item')).find(e=>e.textContent.includes('资源检索')); t&&t.click();})()")
time.sleep(2.5)
print('  检索页标题列前 3 行:',
      ev("""(function(){var rs=document.querySelectorAll('.el-table__row');
        return JSON.stringify(Array.from(rs).slice(0,3).map(r=>r.innerText.split('\\t')[0].trim()));})()"""))
ev("document.querySelector('.el-table__row td')&&document.querySelector('.el-table__row td').click()")
time.sleep(3)
has_btn = ev("""(function(){var d=document.querySelector('.el-dialog');
  return d? d.innerText.includes('去学习') : false;})()""")
url_txt = ev("""(function(){var d=document.querySelector('.el-dialog');
  var m=d&&d.innerText.match(/https?:\\/\\/[^\\s]+/); return m? m[0] : '-';})()""")
print('  弹窗含「去学习」按钮:', has_btn, '| 显示链接:', url_txt)
mid[0] += 1
ws.send(json.dumps({'id': mid[0], 'method': 'Page.captureScreenshot', 'params': {'format': 'png'}}))
while True:
    m = json.loads(ws.recv())
    if m.get('id') == mid[0]:
        open(__file__.rsplit('\\', 1)[0] + '\\ui_13_real_detail.png', 'wb').write(base64.b64decode(m['result']['data']))
        print('  📷 ui_13_real_detail.png')
        break
ws.close()
print('\n结论:', 'PASS ✅' if has_btn and d['url'] else '需复核')
