# -*- coding: utf-8 -*-
"""注册报错修复验证：中文用户名可注册 + 422 错误中文化 + 前端表单校验"""
import json
import time
import urllib.parse
import urllib.request
import urllib.error

import websocket

BASE = 'http://127.0.0.1:8000'
APP = BASE


def api(path, method='GET', data=None, token=None):
    r = urllib.request.Request(BASE + urllib.parse.quote(path, safe=':/?&=%()'), method=method,
                               data=json.dumps(data).encode() if data is not None else None,
                               headers={'Content-Type': 'application/json',
                                        **({'Authorization': 'Bearer ' + token} if token else {})})
    try:
        return 200, json.loads(urllib.request.urlopen(r, timeout=20).read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


# 等后端
for i in range(30):
    try:
        api('/api/recommend/hot?limit=1')
        break
    except Exception:
        time.sleep(2)

print('== 后端层 ==')
c, b = api('/api/auth/register', 'POST', {'username': '张三', 'password': '123456', 'nickname': '张三',
                                          'gender': '男', 'interests': ['机器学习']})
print(f'注册"张三": [{c}]', b.get('nickname') or b.get('detail'))
c2, b2 = api('/api/auth/register', 'POST', {'username': '张三', 'password': '123456', 'nickname': '张三'})
print(f'重复注册: [{c2}]', b2.get('detail'))
c3, b3 = api('/api/auth/register', 'POST', {'username': 'a', 'password': '123456'})
print(f'1 字符用户名: [{c3}]', b3.get('detail'))
c4, b4 = api('/api/auth/register', 'POST', {'username': 'ab', 'password': '123'})
print(f'密码 3 位: [{c4}]', b4.get('detail'))

# ---- 前端层：错误归一化 + 表单校验 ----
print('\n== 前端层 ==')
targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9222/json', timeout=10).read())
page = next((t for t in targets if t['type'] == 'page' and APP in t.get('url', '')), None)
if page is None:
    req = urllib.request.Request(
        'http://127.0.0.1:9222/json/new?' + urllib.parse.quote(APP + '/login', safe=''), method='PUT')
    page = json.loads(urllib.request.urlopen(req, timeout=10).read())
ws = websocket.create_connection(page['webSocketDebuggerUrl'], timeout=25, origin='http://127.0.0.1:9222')
mid = [0]


def ev(expr):
    mid[0] += 1
    ws.send(json.dumps({'id': mid[0], 'method': 'Runtime.evaluate',
                        'params': {'expression': expr, 'awaitPromise': True, 'returnByValue': True}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get('id') == mid[0]:
            return msg['result']['result'].get('value')


ev("sessionStorage.clear(); localStorage.clear(); location.href='http://127.0.0.1:8000/login';")
for i in range(25):
    if ev("!!(window.Vue && window.App && window.ElementPlus)"):
        break
    time.sleep(1)
time.sleep(1.5)
# 归一化逻辑：直接看 api 层返回的 detail
norm = ev("""(async function(){
  const r1 = await window.App.api.register({username:'a', password:'123456', nickname:'', interests:[]});
  const r2 = await window.App.api.register({username:'张三', password:'123456', nickname:''});
  return JSON.stringify({short: r1.detail, dup: r2.detail, dupIsString: typeof r2.detail === 'string'});
})()""")
print('api 层 detail 归一化:', norm)

# 表单校验：切注册 tab，填 1 字符用户名点注册，看 ElMessage 文案
ev("(function(){var t=Array.from(document.querySelectorAll('.el-tabs__item')).find(e=>e.textContent.includes('注册新账号')); t&&t.click();})()")
time.sleep(1)
ev("""(function(){
  const set=(el,v)=>{const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
    s.call(el,v); el.dispatchEvent(new Event('input',{bubbles:true}));};
  const pane=document.querySelector('#pane-register');
  const inputs=pane.querySelectorAll('input');
  set(inputs[0],'a'); set(inputs[1],'123456');
})()""")
time.sleep(0.5)
ev("(function(){var p=document.querySelector('#pane-register');var b=p&&p.querySelector('.login-btn'); b&&b.click();})()")
time.sleep(1.2)
msg = ev("(function(){var m=document.querySelector('.el-message'); return m? m.innerText.trim() : '(无提示)';})()")
print('1 字符用户名提交 ->', msg)
ev("(function(){var m=document.querySelector('.el-message'); m&&m.remove();})()")
# 5 位密码
ev("""(function(){
  const set=(el,v)=>{const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
    s.call(el,v); el.dispatchEvent(new Event('input',{bubbles:true}));};
  const inputs=document.querySelector('#pane-register').querySelectorAll('input');
  set(inputs[0],'测试用户'); set(inputs[1],'12345');
})()""")
time.sleep(0.5)
ev("(function(){var p=document.querySelector('#pane-register');var b=p&&p.querySelector('.login-btn'); b&&b.click();})()")
time.sleep(1.2)
msg2 = ev("(function(){var m=document.querySelector('.el-message'); return m? m.innerText.trim() : '(无提示)';})()")
print('5 位密码提交 ->', msg2)
placeholder = ev("document.querySelector('#pane-register input').placeholder")
print('注册用户名 placeholder:', placeholder)
# 正常注册一个中文名（走前端流程）
ev("(function(){var m=document.querySelector('.el-message'); m&&m.remove();})()")
ev("""(function(){
  const set=(el,v)=>{const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
    s.call(el,v); el.dispatchEvent(new Event('input',{bubbles:true}));};
  const inputs=document.querySelector('#pane-register').querySelectorAll('input');
  set(inputs[0],'李四'); set(inputs[1],'lisi123456');
})()""")
time.sleep(0.5)
ev("(function(){var p=document.querySelector('#pane-register');var b=p&&p.querySelector('.login-btn'); b&&b.click();})()")
time.sleep(3)
ok = ev("!!document.querySelector('.nav-menu')")
print('前端注册"李四" -> 进入主界面:', ok)
ws.close()
