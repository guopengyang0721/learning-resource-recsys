# -*- coding: utf-8 -*-
"""全量链接检测（204 条）：
- 直达型：并发 HTTP GET，2xx/3xx=PASS；403/429/超时标记 WARN 进浏览器复检队列；4xx/5xx/连接失败=FAIL
- 搜索型：CDP 无头浏览器逐条打开，以页面文本判断搜索结果非空
输出：link_check_report.json（逐条）+ 控制台摘要
"""
import base64
import concurrent.futures as cf
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
import urllib.parse

import websocket

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(_PROJ, 'backend', 'data', 'app.db')
REPORT = os.path.join(_PROJ, 'tools', 'link_check_report.json')
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'

con = sqlite3.connect(DB)
rows = con.execute('SELECT id, title, url, category FROM resource ORDER BY id').fetchall()
con.close()

SEARCH_MARKS = ('search.htm', 'search.bilibili', '?keyword=', '?search=', '?query=', '?q=')
search_items = [r for r in rows if any(m in r[2] for m in SEARCH_MARKS)]
direct_items = [r for r in rows if r not in search_items]
print(f'总计 {len(rows)} 条：搜索型 {len(search_items)}，直达型 {len(direct_items)}\n')

# ---------- 直达型：并发 HTTP ----------
def http_check(item):
    rid, title, url, cat = item
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'zh-CN'})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return item, resp.status, 'http-ok'
    except urllib.error.HTTPError as e:
        tag = 'http-antibot' if e.code in (403, 406, 429, 503) else 'http-fail'
        return item, e.code, tag
    except Exception as e:
        return item, 0, 'http-' + type(e).__name__

http_results = {}
need_browser = []
with cf.ThreadPoolExecutor(max_workers=12) as ex:
    for item, status, tag in ex.map(http_check, direct_items):
        http_results[item[0]] = (status, tag)
        if tag == 'http-ok':
            pass
        else:
            need_browser.append((item, status, tag))

print(f'直达型 HTTP 直检：{sum(1 for v in http_results.values() if v[1]=="http-ok")} PASS，'
      f'{len(need_browser)} 条需浏览器复检\n')

# ---------- 浏览器复检（直达型失败/反爬 + 全部搜索型） ----------
targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9222/json', timeout=10).read())
page = next(t for t in targets if t['type'] == 'page')
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


send('Page.enable')
JS_PAGE = """(function(){
  var t = document.body ? document.body.innerText : '';
  var m = t.match(/(\\d[\\d,]*)\\s*(个结果|门课程|条结果|个视频|个课程|道题|个需求)/);
  var empty = /没有找到|暂无相关|无相关|搜索结果为空|未找到相关|共\\s*0\\s*条/.test(t);
  return JSON.stringify({len: t.length, num: m ? m[1] : '', empty: empty,
                         title: (document.title||'').slice(0,60)});
})()"""


def browser_check(url, wait=7.0):
    """打开页面并返回 (ok, info_dict)。"""
    try:
        send('Page.navigate', {'url': url})
    except Exception:
        return False, {'error': 'navigate-failed'}
    time.sleep(wait)
    try:
        info = json.loads(ev(JS_PAGE) or '{}')
    except Exception:
        return False, {'error': 'evaluate-failed'}
    ok = (not info.get('empty')) and info.get('len', 0) > 300
    return ok, info


results = []   # (rid, title, url, category, verdict, detail)

# 搜索型全量
print(f'开始搜索型逐条实测（{len(search_items)} 条，约 {len(search_items)*7//60} 分钟）…\n')
for i, (rid, title, url, cat) in enumerate(search_items, 1):
    ok, info = browser_check(url)
    verdict = 'PASS' if ok else 'FAIL'
    detail = f'len={info.get("len", 0)} 空结果={info.get("empty")} 命中={info.get("num") or "-"}'
    results.append({'id': rid, 'title': title, 'url': url, 'category': cat,
                    'kind': 'search', 'verdict': verdict, 'detail': detail})
    print(f'{i:>3}/{len(search_items)} {"✅" if ok else "❌"} [{cat}] {title[:30]}  ({detail})')

# 直达型复检（仅 FAIL/反爬的）
print(f'\n直达型浏览器复检 {len(need_browser)} 条…\n')
for item, status, tag in need_browser:
    rid, title, url, cat = item
    ok, info = browser_check(url, wait=6.0)
    verdict = 'PASS' if ok else 'FAIL'
    detail = f'http={status}({tag}) browser_len={info.get("len", 0)} title={info.get("title", "")[:40]}'
    results.append({'id': rid, 'title': title, 'url': url, 'category': cat,
                    'kind': 'direct', 'verdict': verdict, 'detail': detail})
    print(f'{"✅" if ok else "❌"} [{cat}] {title[:34]}  ({detail})')

# 直达型 HTTP 一次通过的
for item in direct_items:
    if http_results[item[0]][1] == 'http-ok':
        results.append({'id': item[0], 'title': item[1], 'url': item[2], 'category': item[3],
                        'kind': 'direct', 'verdict': 'PASS',
                        'detail': f'http={http_results[item[0]][0]}'})

with open(REPORT, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=1)

fails = [r for r in results if r['verdict'] == 'FAIL']
print(f'\n===== 汇总：{len(results)} 条，PASS {len(results)-len(fails)}，FAIL {len(fails)} =====')
for r in fails:
    print(f"  ❌ id={r['id']} [{r['category']}] {r['title']}\n      {r['url']}\n      {r['detail']}")
ws.close()
