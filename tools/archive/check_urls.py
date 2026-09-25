# -*- coding: utf-8 -*-
"""URL 可达性核验：逐个检查真实资源链接（并发），输出状态分类"""
import os
_PROJ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # 项目根（tools/archive 上溯三层）
import concurrent.futures as cf
import sqlite3
import urllib.error
import urllib.request

DB = os.path.join(_PROJ, 'backend', 'data', 'app.db')
con = sqlite3.connect(DB)
rows = con.execute("SELECT DISTINCT url FROM resource WHERE url != ''").fetchall()
con.close()
urls = [r[0] for r in rows]
print(f'待核验 URL: {len(urls)} 个（去重后）\n')


def check(u):
    req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return u, r.status, 'OK'
    except urllib.error.HTTPError as e:
        tag = 'OK(反爬拦截)' if e.code in (403, 429, 406) else f'HTTP {e.code}'
        return u, e.code, tag
    except Exception as e:
        return u, 0, type(e).__name__


ok = bad = 0
with cf.ThreadPoolExecutor(max_workers=10) as ex:
    for u, code, tag in ex.map(check, urls):
        mark = '✅' if code == 200 or 'OK' in tag else ('⚠️' if tag == 'HTTP 404' else '❓')
        print(f'{mark} [{code or "-":>4}] {tag:<14} {u}')
        if code == 200:
            ok += 1
        elif 'OK' in tag:
            ok += 1
        else:
            bad += 1
print(f'\n可达 {ok} / 需关注 {bad} / 共 {len(urls)}')
