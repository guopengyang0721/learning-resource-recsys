# -*- coding: utf-8 -*-
"""文件上传/下载全链路验证：上传→建资源→详情→下载→删除联动"""
import json
import os
_PROJ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # 项目根（tools/archive 上溯三层）
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = 'http://127.0.0.1:8000'
UPLOAD_DIR = os.path.join(_PROJ, 'backend', 'data', 'uploads')
TMP = os.path.join(_PROJ, 'tools')
THE_FILE = os.path.join(TMP, '_upload_test.txt')
BIG_FILE = os.path.join(TMP, '_upload_big.bin')
BAD_FILE = os.path.join(TMP, '_upload_test.exe')


def api(path, method='GET', data=None, token=None):
    r = urllib.request.Request(BASE + urllib.parse.quote(path, safe=':/?&=%()'), method=method,
                               data=json.dumps(data).encode() if data is not None else None,
                               headers={'Content-Type': 'application/json',
                                        **({'Authorization': 'Bearer ' + token} if token else {})})
    try:
        return 200, json.loads(urllib.request.urlopen(r, timeout=60).read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


def upload(path, token, filename=None):
    name = filename or os.path.basename(path)
    with open(path, 'rb') as f:
        data = f.read()
    boundary = '----WB' + uuid.uuid4().hex
    body = b''
    body += f'--{boundary}\r\n'.encode()
    body += f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'.encode('utf-8')
    body += b'Content-Type: application/octet-stream\r\n\r\n'
    body += data + b'\r\n' + f'--{boundary}--\r\n'.encode()
    req = urllib.request.Request(BASE + '/api/teacher/resources/upload', data=body, method='POST',
                                 headers={'Content-Type': f'multipart/form-data; boundary={boundary}',
                                          'Authorization': 'Bearer ' + token})
    try:
        return 200, json.loads(urllib.request.urlopen(req, timeout=120).read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


for i in range(40):
    try:
        api('/api/recommend/hot?limit=1')
        break
    except Exception:
        time.sleep(2)

print('=== 0. 表结构迁移 ===')
import sqlite3
con = sqlite3.connect(os.path.join(_PROJ, 'backend', 'data', 'app.db'))
cols = [r[1] for r in con.execute('PRAGMA table_info(resource)')]
print('  附件列:', [c for c in cols if c.startswith('file_')], '齐全:', all(c in cols for c in ('file_name', 'file_size', 'file_path')))
con.close()

T = api('/api/auth/login', 'POST', {'username': 'teacher01', 'password': '123456'})[1]['token']
A = api('/api/auth/login', 'POST', {'username': 'admin', 'password': 'admin123'})[1]['token']
S = api('/api/auth/login', 'POST', {'username': 'student001', 'password': '123456'})[1]['token']

# 准备测试文件
with open(THE_FILE, 'w', encoding='utf-8') as f:
    f.write('真实上传链路测试内容 2026-09-12\n第二行：' + 'x' * 200 + '\n')
with open(BAD_FILE, 'wb') as f:
    f.write(b'MZ fake exe')
with open(BIG_FILE, 'wb') as f:
    f.write(os.urandom(51 * 1024 * 1024))
print(f'\n测试文件: {os.path.getsize(THE_FILE)}B / 非法exe {os.path.getsize(BAD_FILE)}B / 超限 {os.path.getsize(BIG_FILE)/1024/1024:.0f}MB')

print('\n=== 1. 正常上传（含中文文件名） ===')
c, up = upload(THE_FILE, T, filename='课程讲义·第一章.txt')
print(f'  [{c}]', up.get('message') or up.get('detail'), '| file_path =', up.get('file_path'))
stored = up.get('file_path')
print('  磁盘存在:', os.path.isfile(os.path.join(UPLOAD_DIR, stored)) if stored else False)

print('\n=== 2. 非法类型被拒 ===')
c2, b2 = upload(BAD_FILE, T)
print(f'  [{c2}]', b2.get('detail'))

print('\n=== 3. 超大小被拒（51MB > 50MB） ===')
c3, b3 = upload(BIG_FILE, T)
print(f'  [{c3}]', b3.get('detail'))

print('\n=== 4. 建资源并带附件 ===')
c4, r4 = api('/api/teacher/resources', 'POST', {
    'title': '文件上传链路测试资源', 'category': '算法', 'type': 'doc', 'difficulty': 2,
    'url': '', 'description': '验证附件上传与下载。',
    'file_name': up['file_name'], 'file_size': up['file_size'], 'file_path': up['file_path']}, token=T)
rid = r4.get('id')
print(f'  [{c4}] id={rid}', r4.get('message') or r4.get('detail'))
api(f'/api/admin/resources/{rid}/status', 'PUT', {'status': 'online'}, token=A)

print('\n=== 5. 学生端详情含附件信息 ===')
d = api(f'/api/resources/{rid}', token=S)[1]
print(f"  has_file={d['has_file']} file_name={d['file_name']!r} file_size={d['file_size']}")

print('\n=== 6. 下载并比对内容 ===')
req = urllib.request.Request(f'{BASE}/api/resources/{rid}/download', headers={'Authorization': 'Bearer ' + S})
resp = urllib.request.urlopen(req, timeout=60)
got = resp.read()
with open(THE_FILE, 'rb') as f:
    want = f.read()
print('  HTTP', resp.status, '| Content-Disposition:', resp.headers.get('Content-Disposition'))
print(f'  字节一致: {got == want}（{len(got)} B）')

print('\n=== 7. 无附件资源的下载接口 ===')
print('  资源 1（无附件）->', api('/api/resources/1/download', token=S)[0], '（应为 404）')

print('\n=== 8. 删除资源联动删文件 ===')
api(f'/api/admin/resources/{rid}', 'DELETE', token=A)
print('  磁盘文件还在吗:', os.path.isfile(os.path.join(UPLOAD_DIR, stored)))
print('  上传目录剩余文件:', len(os.listdir(UPLOAD_DIR)) if os.path.isdir(UPLOAD_DIR) else 0)

# 清理临时文件
for p in (THE_FILE, BIG_FILE, BAD_FILE):
    if os.path.exists(p):
        os.remove(p)
print('\n临时文件已清理')
