# -*- coding: utf-8 -*-
"""实测站内搜索结果（v2）：以页面文本为准判断有无结果，抽样 20 条"""
import os
_PROJ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # 项目根（tools/archive 上溯三层）
import json
import random
import sqlite3
import time
import urllib.parse
import urllib.request

import websocket

DB = os.path.join(_PROJ, 'backend', 'data', 'app.db')
con = sqlite3.connect(DB)
rows = con.execute("SELECT title, url FROM resource WHERE url LIKE '%search%' OR url LIKE '%keyword=%'").fetchall()
con.close()
random.seed(20260912)
sample = random.sample(rows, 20)

targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9222/json', timeout=10).read())
page = next((t for t in targets if t['type'] == 'page'), None)
ws = websocket.create_connection(page['webSocketDebuggerUrl'], timeout=30, origin='http://127.0.0.1:9222')
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


send('Page.enable')
JS = """(function(){
  var t = document.body ? document.body.innerText : '';
  var m = t.match(/(\\d[\\d,]*)\\s*(个结果|门课程|条结果|个视频|个课程|道题)/);
  var empty = /没有找到|暂无|无相关|搜索结果为空|未找到/.test(t);
  return JSON.stringify({len: t.length, num: m ? m[1] : '', empty: empty, head: t.slice(0,60).replace(/\\n/g,' ')});
})()"""

print(f'抽测 {len(sample)} 条站内搜索链接（以页面文本判断）\n')
bad = []
for title, url in sample:
    send('Page.navigate', {'url': url})
    time.sleep(8)
    try:
        info = json.loads(ev(JS) or '{}')
    except Exception:
        info = {}
    empty = info.get('empty')
    ln = info.get('len', 0)
    good = (not empty) and ln > 400
    if not good:
        bad.append((title, url, info))
    host = urllib.parse.urlparse(url).netloc
    flag = '✅' if good else '❌'
    print(f'{flag} [{host[:20]:<20}] len={ln:<6} 空结果={empty}  命中数={info.get("num") or "-"}  {title[:24]}')

print()
if bad:
    print(f'需复核 {len(bad)} 条:')
    for t, u, i in bad:
        print(f'  {t}\n    {u}\n    {i}')
else:
    print('全部抽测条目均有搜索结果 ✅（未出现"没有找到/暂无结果"）')
ws.close()
