# -*- coding: utf-8 -*-
"""把 resource 表文案层替换为真实学习资源（方案 A）

- resource_id 保持不变 → 评分矩阵/收藏/行为日志/离线指标零影响
- 只更新 title / type / difficulty / description / url
- 分类内按 id 升序一一对应；数量不匹配时打印警告并跳过多余项
"""
import os
import sqlite3
import sys

sys.path.insert(0, __file__.rsplit('\\', 1)[0])
from real_resources import RESOURCES

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend', 'data', 'app.db')

con = sqlite3.connect(DB)
cur = con.cursor()

before = cur.execute("SELECT COUNT(*) FROM resource").fetchone()[0]
print(f'替换前资源总数: {before}')
print(f'数据清单总数: {sum(len(v) for v in RESOURCES.values())}')
print()

total_updated = 0
for cat, items in RESOURCES.items():
    ids = [r[0] for r in cur.execute(
        "SELECT id FROM resource WHERE category=? ORDER BY id", (cat,)).fetchall()]
    if len(ids) != len(items):
        print(f'⚠️ {cat}: 库中 {len(ids)} 条 / 清单 {len(items)} 条 —— 按较小数量对齐')
    for rid, (title, rtype, diff, url, desc) in zip(ids, items):
        cur.execute("UPDATE resource SET title=?, type=?, difficulty=?, description=?, url=? WHERE id=?",
                    (title, rtype, diff, desc, url, rid))
        total_updated += 1
    print(f'{cat}: 更新 {min(len(ids), len(items))} 条')
con.commit()
print(f'\n共更新 {total_updated} 条')

print('\n=== 核对：随机看几条 ===')
for r in cur.execute("SELECT id, title, type, category, difficulty, substr(url,1,48), substr(description,1,30) FROM resource ORDER BY RANDOM() LIMIT 6"):
    print(' ', r)

print('\n=== 未更新的残留（仍为模板标题）===')
old = cur.execute("SELECT COUNT(*) FROM resource WHERE title LIKE '%-%-%-%' AND title NOT LIKE '%LeetCode%'").fetchone()[0]
print(' 形如"分类-类型NNN-后缀"的标题数:', old)
print('\n=== 交互数据未动核对 ===')
for t in ('score', 'favorite', 'behavior_log'):
    print(f'  {t}:', cur.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0])

print('\n=== 字段填充率 ===')
for col in ('url', 'description'):
    n = cur.execute(f"SELECT COUNT(*) FROM resource WHERE {col} IS NOT NULL AND {col} != ''").fetchone()[0]
    print(f'  {col}: {n}/{before}')
con.close()
