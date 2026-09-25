# -*- coding: utf-8 -*-
"""全功能 API 体检：三角色全接口 + 越权 + 边界 + 计时（测试数据自清理）"""
import json
import time
import urllib.request
import urllib.error
from urllib.parse import quote

BASE = 'http://127.0.0.1:8000'
results = []


def req(path, method='GET', data=None, token=None, expect=200):
    r = urllib.request.Request(BASE + quote(path, safe=':/?&=%()'), method=method,
                               data=json.dumps(data).encode() if data is not None else None,
                               headers={'Content-Type': 'application/json',
                                        **({'Authorization': 'Bearer ' + token} if token else {})})
    t0 = time.time()
    try:
        body = json.loads(urllib.request.urlopen(r, timeout=30).read())
        code, ms = 200, (time.time() - t0) * 1000
    except urllib.error.HTTPError as e:
        body, code, ms = json.loads(e.read() or b'{}'), e.code, (time.time() - t0) * 1000
    ok = code == expect
    results.append((ok, f'[{code}] {method} {path}', ms, body if not ok else None))
    return body, code, ms


def section(title):
    results.append((None, f'\n===== {title} =====', 0, None))


# ---------- 临时账号自动清理 ----------
# 脚本注册的测试账号在退出时（含异常退出）统一删除，避免演示数据被历次巡检污染。
import atexit

_created, _admin_token = [], [None]


def track_account(user_id, username):
    """登记本脚本创建的临时账号，供退出时清理。"""
    if user_id:
        _created.append((user_id, username))


@atexit.register
def _cleanup_accounts():
    if not _created or not _admin_token[0]:
        return
    print('\n-- 清理本次创建的测试账号 --')
    for uid, uname in _created:
        try:
            _, code, _ = req(f'/api/admin/users/{uid}', 'DELETE', token=_admin_token[0])
            print('   %s %s' % ('已删除' if code == 200 else '删除失败[%d]' % code, uname))
        except Exception as e:
            print('   删除失败 %s: %s' % (uname, type(e).__name__))


# ---------- 匿名/鉴权边界 ----------
section('鉴权边界')
req('/api/resources?page=1&size=1', expect=401)                    # 无令牌
req('/api/resources?page=1&size=1', token='fake.token.here', expect=401)  # 伪造令牌
b, c, ms = req('/api/recommend/hot?limit=5')                        # 公开接口
assert_ok = len(b.get('items', [])) == 5

# 三角色登录（错误密码只试 1 次，防触发锁定阈值5）
stu, _, _ = req('/api/auth/login', 'POST', {'username': 'student001', 'password': '123456'})
tea, _, _ = req('/api/auth/login', 'POST', {'username': 'teacher01', 'password': '123456'})
adm, _, _ = req('/api/auth/login', 'POST', {'username': 'admin', 'password': 'admin123'})
S, T, A = stu['token'], tea['token'], adm['token']
_admin_token[0] = A                     # 供脚本退出时清理临时账号
req('/api/auth/login', 'POST', {'username': 'student001', 'password': 'wrongpw'}, expect=400)  # 错密码
stu2, c2, _ = req('/api/auth/verify', token=S)
results.append((c2 == 200 and stu2.get('user_id') == stu['user_id'], 'verify 令牌身份一致', 0, None))

# ---------- 注册 + 冷启动 ----------
section('注册/密保')
suffix = str(int(time.time()))[-6:]
reg, _, _ = req('/api/auth/register', 'POST', {
    'username': 'sweep' + suffix, 'password': 'sweep123', 'nickname': '巡检临时号',
    'interests': ['机器学习', '人工智能'], 'gender': '男', 'grade': '2024级',
    'college': '信息学院', 'sec_question': '你的出生城市是？', 'sec_answer': '北京'})
track_account(reg.get('user_id'), 'sweep' + suffix)      # 退出时自动清理
SW = reg.get('token', '')
results.append((bool(SW), '注册带兴趣+密保', 0, None))
# 防枚举测试用随机用户名：固定用户名多轮累计会触发限流 429（限流正常工作，测试不应误伤）
ghost = 'no_such_' + suffix
req('/api/auth/sec-question', 'POST', {'username': ghost}, expect=404)              # 防枚举
req('/api/auth/forgot-password', 'POST', {'username': ghost, 'answer': 'x',
                                          'new_password': 'abc123'}, expect=400)    # 400=不暴露用户存在性（防枚举✓）

# ---------- 个人中心 ----------
section('个人中心')
p, _, _ = req('/api/user/profile', 'PUT', {'nickname': '学生001', 'gender': '男', 'grade': '2024级',
                                           'college': '软件学院'}, token=S)
b, _, _ = req('/api/user/change-password', 'POST', {'old_password': '123456',
                                                    'new_password': 'abc12345'}, token=S)   # 独立改密接口
_, c3, _ = req('/api/auth/login', 'POST', {'username': 'student001', 'password': 'abc12345'})
results.append((c3 == 200, '新密码可登录', 0, None))
b, _, _ = req('/api/user/change-password', 'POST', {'old_password': 'abc12345',
                                                    'new_password': '123456'}, token=S)     # 改回
h, _, _ = req('/api/user/history?limit=50', token=S)
results.append((len(h.get('items', [])) > 0, f'足迹 {len(h.get("items", []))} 条', 0, None))
if h.get('items'):
    req('/api/user/history/' + str(h['items'][-1]['id']), 'DELETE', token=S)              # 删自己最旧一条
req('/api/user/history/99999999', 'DELETE', token=S, expect=404)                          # 他人/不存在
f1, _, _ = req('/api/user/favorites?page=1&size=6', token=S)
f2, _, _ = req('/api/user/favorites?page=99&size=6', token=S)
results.append((len(f1['items']) == 6 and f2['items'] == [] and f2['total'] == f1['total'],
                f'收藏分页 page1=6条/越界页空/total={f1["total"]}', 0, None))
nt, _, _ = req('/api/user/notifications', token=S)
results.append(('items' in nt, f'通知 {len(nt.get("items", []))} 条/未读 {nt.get("unread")}', 0, None))
if nt.get('items') and not nt['items'][0]['is_read']:
    req(f"/api/user/notifications/{nt['items'][0]['id']}/read", 'POST', token=S)
pt, _, _ = req('/api/user/portrait', token=S)
results.append(('distribution' in pt, f'画像 {len(pt.get("distribution", {}))} 类', 0, None))

# ---------- 资源检索 ----------
section('资源检索/详情/相似')
r0, _, _ = req('/api/resources?page=1&size=8', token=S)
results.append((len(r0['items']) == 8 and r0['total'] > 0, f'默认列表 total={r0["total"]}', 0, None))
for q, name in [('keyword=机器', '关键词'), ('category=数据库', '分类'), ('type=video,doc', '类型多选'),
                ('sort=rating', '评分排序'), ('sort=xxx', '非法sort忽略'), ('days=30', '时间窗')]:
    b, _, ms = req(f'/api/resources?page=1&size=8&{q}', token=S)
    results.append((isinstance(b.get('items'), list), f'{name} 筛选 {len(b.get("items", []))} 条', ms, None))
# 挑一个当前未被该学生收藏的资源：后面的收藏/取消用例才不会动到真实收藏数据
# （此前固定取列表首条，若它恰好已被收藏，用例的 DELETE 会把真实收藏删掉且无法恢复）
rid, was_fav = None, False
for it in r0['items']:
    dd, _, _ = req(f"/api/resources/{it['id']}", token=S)
    if dd.get('favorited') is not True:
        rid = it['id']
        break
if rid is None:                                   # 兜底：首屏全被收藏时取首条，并在用例结束后复原
    rid = r0['items'][0]['id']
    was_fav = req(f'/api/resources/{rid}', token=S)[0].get('favorited') is True
d, _, _ = req(f'/api/resources/{rid}', token=S)
sim, _, _ = req(f'/api/resources/{rid}/similar?n=5', token=S)
results.append(('title' in d and len(sim.get('items', [])) <= 5, f'详情+相似 {len(sim.get("items", []))} 条', 0, None))

# ---------- 行为与收藏 ----------
section('行为/收藏状态机')
req('/api/behavior', 'POST', {'user_id': stu['user_id'], 'resource_id': rid, 'action': 'view'}, token=S)
req('/api/behavior', 'POST', {'user_id': stu['user_id'], 'resource_id': rid, 'action': 'rate', 'value': 5}, token=S)
fa, _, _ = req(f'/api/favorites/{rid}?user_id={stu["user_id"]}', 'POST', token=S)         # 收藏
fb, _, _ = req(f'/api/resources/{rid}', token=S)
results.append((fb.get('favorited') is True, '收藏后 favorited=true', 0, None))
fc, _, _ = req(f'/api/favorites/{rid}', 'DELETE', token=S)                                # 取消
fd, _, _ = req(f'/api/resources/{rid}', token=S)
results.append((fd.get('favorited') is False, '取消后 favorited=false(行为保留)', 0, None))
if was_fav:                                      # 兜底路径：原本已收藏 → 测完复原，不留痕
    req(f'/api/favorites/{rid}', 'POST', token=S)
    chk, _, _ = req(f'/api/resources/{rid}', token=S)
    results.append((chk.get('favorited') is True, '原本已收藏的资源已复原', 0, None))

# ---------- 推荐 ----------
section('推荐引擎')
for algo in ('user_cf', 'item_cf', 'svd'):
    b, _, ms = req(f"/api/recommend/{stu['user_id']}?n=10&algo={algo}", token=S)
    results.append((len(b.get('items', [])) > 0, f'{algo} 推荐 {len(b.get("items", []))} 条 source={b.get("source", "")}', ms, None))
b, _, ms = req(f"/api/recommend/{reg.get('user_id')}?n=10&algo=user_cf", token=SW)
results.append((len(b.get('items', [])) > 0, f'新号冷启动(兴趣) {len(b.get("items", []))} 条', ms, None))

# ---------- 越权 ----------
section('角色越权')
req('/api/admin/stats/dashboard', token=S, expect=403)      # 学生→管理
req('/api/admin/stats/dashboard', token=T, expect=403)      # 教师→管理
req('/api/teacher/resources', 'POST', {'title': 'xx', 'category': '算法', 'type': 'doc',
                                       'difficulty': 3, 'url': '', 'description': ''}, token=S, expect=403)
req('/api/user/notifications', expect=401)

# ---------- 教师 + 管理员审核全链路 ----------
section('教师上传→审核→下架→删除')
up, _, _ = req('/api/teacher/resources', 'POST', {'title': f'巡检测试资源{suffix}', 'category': '算法',
                                                  'type': 'doc', 'difficulty': 3,
                                                  'url': 'https://example.com/sweep',
                                                  'description': '全功能巡检临时资源'}, token=T)
tid = up.get('resource', {}).get('id') or up.get('id')
results.append((bool(tid), f'教师上传 id={tid}(pending)', 0, None))
mr, _, _ = req('/api/teacher/my-resources', token=T)
mine = [x for x in mr.get('items', []) if x['id'] == tid]
results.append((len(mine) == 1, '我的资源可见', 0, None))
req('/api/teacher/resources/' + str(tid), 'PUT', {'title': f'巡检测试资源{suffix}v2', 'category': '算法',
                                                  'type': 'doc', 'difficulty': 3,
                                                  'url': 'https://example.com/sweep',
                                                  'description': '编辑后的描述'}, token=T)
ap, _, _ = req('/api/admin/resources?status=pending&keyword=巡检', token=A)
hit = [x for x in ap.get('items', []) if x['id'] == tid]
results.append((len(hit) == 1, '管理员待审列表命中', 0, None))
req(f'/api/admin/resources/{tid}/status', 'PUT', {'status': 'online'}, token=A)           # 审核上架
st, _, _ = req(f'/api/resources/{rid}', token=S) if False else (None, None, None)
sr, _, _ = req(f'/api/resources?page=1&size=5&keyword=巡检测试资源{suffix}', token=S)
results.append((any(x['id'] == tid for x in sr['items']), '上架后学生检索可见', 0, None))
req(f'/api/admin/resources/{tid}/status', 'PUT', {'status': 'offline'}, token=A)          # 下架
req(f'/api/admin/resources/{tid}', 'DELETE', token=A)                                     # 删除清理

# ---------- 用户管理 ----------
section('用户管理')
us, _, _ = req('/api/admin/users?keyword=sweep' + suffix, token=A)
suid = us['items'][0]['id'] if us.get('items') else None
results.append((suid is not None, '用户检索命中临时号', 0, None))
req(f'/api/admin/users/{suid}/status', 'PUT', {'status': 'disabled'}, token=A)
_, c4, _ = req('/api/auth/login', 'POST', {'username': 'sweep' + suffix, 'password': 'sweep123'}, expect=403)
results.append((c4 == 403, '禁用后登录 403', 0, None))
req(f'/api/admin/users/{suid}/status', 'PUT', {'status': 'active'}, token=A)
req(f'/api/admin/users/{suid}/password', 'PUT', {'new_password': 'newpass123'}, token=A)
_, c5, _ = req('/api/auth/login', 'POST', {'username': 'sweep' + suffix, 'password': 'newpass123'})
results.append((c5 == 200, '重置密码后新密码可登录', 0, None))
req('/api/admin/users/1/status', 'PUT', {'status': 'disabled'}, token=A, expect=400)      # 不能禁自己(admin id=1?)

# ---------- 通知广播 ----------
section('广播')
bc, _, _ = req('/api/admin/notifications/broadcast', 'POST',
               {'title': '【系统自检】巡检公告', 'content': '全功能巡检测试公告，可忽略。'}, token=A)
results.append((bc.get('count', 0) > 0, f'广播送达 {bc.get("count")} 人', 0, None))

# ---------- 汇总 ----------
ok_n = sum(1 for r in results if r[0] is True)
fail_n = sum(1 for r in results if r[0] is False)
slow = [(t, ms) for ok, t, ms, _ in results if ok and ms > 500]
print()
for ok, t, ms, body in results:
    if ok is None:
        print(t)
    else:
        mark = 'PASS' if ok else 'FAIL'
        mstr = f' {ms:6.0f}ms' if ok and ms > 0 else ''
        print(f'[{mark}] {t}{mstr}')
        if not ok and body:
            print('       返回:', json.dumps(body, ensure_ascii=False)[:200])
print(f'\n结论: {ok_n} PASS / {fail_n} FAIL')
if slow:
    print('慢接口(>500ms):')
    for t, ms in sorted(slow, key=lambda x: -x[1]):
        print(f'  {ms:6.0f}ms  {t}')
