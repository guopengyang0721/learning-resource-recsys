# -*- coding: utf-8 -*-
"""补测：51MB 超限拒绝（白名单内类型）+ 上传消息大小格式 + UI 拖拽上传实拍"""
import base64
import json
import os
_PROJ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # 项目根（tools/archive 上溯三层）
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import websocket

BASE = 'http://127.0.0.1:8000'
UPLOAD_DIR = os.path.join(_PROJ, 'backend', 'data', 'uploads')
TMP = os.path.join(_PROJ, 'tools')
BIG = os.path.join(TMP, '_big_test.zip')
SMALL = os.path.join(TMP, '_small_test.txt')


def api(path, method='GET', data=None, token=None):
    r = urllib.request.Request(BASE + urllib.parse.quote(path, safe=':/?&=%()'), method=method,
                               data=json.dumps(data).encode() if data is not None else None,
                               headers={'Content-Type': 'application/json',
                                        **({'Authorization': 'Bearer ' + token} if token else {})})
    try:
        return 200, json.loads(urllib.request.urlopen(r, timeout=180).read())
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
    body = (f'--{boundary}\r\n'.encode()
            + f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'.encode('utf-8')
            + b'Content-Type: application/octet-stream\r\n\r\n' + data
            + b'\r\n' + f'--{boundary}--\r\n'.encode())
    req = urllib.request.Request(BASE + '/api/teacher/resources/upload', data=body, method='POST',
                                 headers={'Content-Type': f'multipart/form-data; boundary={boundary}',
                                          'Authorization': 'Bearer ' + token})
    try:
        return 200, json.loads(urllib.request.urlopen(req, timeout=180).read())
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

T = api('/api/auth/login', 'POST', {'username': 'teacher01', 'password': '123456'})[1]['token']

print('=== 补测 1：小文件消息格式 ===')
with open(SMALL, 'wb') as f:
    f.write(b'demo')
c, b = upload(SMALL, T)
print(f'  [{c}]', b.get('message'))
if b.get('file_path'):
    os.remove(os.path.join(UPLOAD_DIR, b['file_path']))

print('\n=== 补测 2：51MB zip 超限拒绝 ===')
with open(BIG, 'wb') as f:
    f.write(os.urandom(51 * 1024 * 1024))
c2, b2 = upload(BIG, T)
print(f'  [{c2}]', b2.get('detail'))
print('  上传目录是否残留半截文件:', len(os.listdir(UPLOAD_DIR)) if os.path.isdir(UPLOAD_DIR) else 0, '个')
os.remove(BIG)

print('\n=== UI：拖拽上传区 + 选择文件 + 提交全流程 ===')
targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9222/json', timeout=10).read())
page = next((t for t in targets if t['type'] == 'page' and BASE in t.get('url', '')), None)
if page is None:
    req = urllib.request.Request('http://127.0.0.1:9222/json/new?'
                                 + urllib.parse.quote(BASE + '/login?autologin=1&user=teacher', safe=''), method='PUT')
    page = json.loads(urllib.request.urlopen(req, timeout=10).read())
ws = websocket.create_connection(page['webSocketDebuggerUrl'], timeout=40, origin='http://127.0.0.1:9222')
mid = [0]


def ev(expr):
    mid[0] += 1
    ws.send(json.dumps({'id': mid[0], 'method': 'Runtime.evaluate',
                        'params': {'expression': expr, 'awaitPromise': True, 'returnByValue': True}}))
    while True:
        m = json.loads(ws.recv())
        if m.get('id') == mid[0]:
            return m['result']['result'].get('value')


def send(method, params=None):
    mid[0] += 1
    ws.send(json.dumps({'id': mid[0], 'method': method, 'params': params or {}}))
    while True:
        m = json.loads(ws.recv())
        if m.get('id') == mid[0]:
            return m.get('result')


def shot(name):
    r = send('Page.captureScreenshot', {'format': 'png'})
    open(os.path.join(TMP, name), 'wb').write(base64.b64decode(r['data']))
    print('  📷', name)


ev("sessionStorage.clear(); localStorage.clear(); location.href='http://127.0.0.1:8000/login?autologin=1&user=teacher';")
for i in range(25):
    if ev("!!(window.Vue && window.App && document.querySelector('.nav-menu'))"):
        break
    time.sleep(1)
time.sleep(2.5)
ev("(function(){var t=Array.from(document.querySelectorAll('.nav-menu .el-menu-item')).find(e=>e.textContent.includes('教师工作台')); t&&t.click();})()")
time.sleep(3)
ev("(function(){var b=Array.from(document.querySelectorAll('.el-button')).find(x=>x.textContent.includes('上传新资源')); b&&b.click();})()")
time.sleep(2)
has_drag = ev("!!document.querySelector('.el-dialog .el-upload-dragger')")
print('  拖拽区存在:', has_drag)
shot('ui_17_upload_drag.png')

# 用 CDP 真实给 file input 塞文件
send('DOM.enable')
doc = send('DOM.getDocument')
fpath = SMALL.replace('/', '\\')
node = send('DOM.querySelector', {'nodeId': doc['root']['nodeId'], 'selector': '.el-dialog input[type=file]'})
print('  file input nodeId:', node.get('nodeId'))
send('DOM.setFileInputFiles', {'nodeId': node['nodeId'], 'files': [fpath]})
time.sleep(1.5)
picked = ev("(function(){var d=document.querySelector('.el-dialog'); return d.innerText.match(/_small_test\\.txt/) ? '_small_test.txt' : '(未显示)'})()")
print('  选择文件后弹窗显示:', picked)
shot('ui_18_upload_picked.png')

# 填标题并提交
ev("""(function(){
  const set=(el,v)=>{const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
    s.call(el,v); el.dispatchEvent(new Event('input',{bubbles:true}));};
  var d=document.querySelector('.el-dialog');
  var inputs=d.querySelectorAll('.el-form-item input');
  set(inputs[0],'拖拽上传链路测试资源');
})()""")
time.sleep(0.5)
ev("(function(){var d=document.querySelector('.el-dialog'); var b=Array.from(d.querySelectorAll('.el-button')).find(x=>x.textContent.includes('提')); b&&b.click();})()")
time.sleep(6)
res = ev("(function(){var m=document.querySelector('.el-message'); return m? m.innerText.trim() : '(无提示)'})()")
print('  提交提示:', res)
shot('ui_19_upload_done.png')
ws.close()

# 清理：删除该测试资源
A = api('/api/auth/login', 'POST', {'username': 'admin', 'password': 'admin123'})[1]['token']
b = api('/api/admin/resources?keyword=拖拽上传链路测试资源', token=A)[1]
for x in b.get('items', []):
    c, r = api(f"/api/admin/resources/{x['id']}", 'DELETE', token=A)
    print('  清理:', x['id'], r.get('message'))
if os.path.exists(SMALL):
    os.remove(SMALL)
print('\n上传目录剩余:', len(os.listdir(UPLOAD_DIR)) if os.path.isdir(UPLOAD_DIR) else 0, '个文件')
