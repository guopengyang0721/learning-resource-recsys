# -*- coding: utf-8 -*-
"""链接精化：把「平台首页」链接换成「站内搜索」链接，关键词取自资源标题。

背景：为避免死链，初始清单大量使用平台首页（如 icourse163 首页），
      但标题指向具体课程，用户点「去学习」进首页后找不到对应课程。
策略：仅对"标题指向具体课程、链接却是平台根路径"的条目做精化，
      官方文档/教材官网的首页本身就是资源的正确落点，保持不变。
同步：重写 real_resources.py（保持清单=入库内容）+ 更新数据库。
"""
import os
import re
import sqlite3
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from real_resources import RESOURCES

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend', 'data', 'app.db')
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'real_resources.py')

# 需要精化的平台：根路径 → 站内搜索页
SEARCH_TPL = {
    'www.icourse163.org': 'https://www.icourse163.org/search.htm?search={q}',
    'search.bilibili.com': 'https://search.bilibili.com/all?keyword={q}',
    'www.xuetangx.com': 'https://www.xuetangx.com/search?query={q}',
    'leetcode.cn': 'https://leetcode.cn/problemset/?search={q}',
    'www.kaggle.com': 'https://www.kaggle.com/search?q={q}',
    'www.lanqiao.cn': 'https://www.lanqiao.cn/problems/?keyword={q}',
    'www.luogu.com.cn': 'https://www.luogu.com.cn/problem/list?keyword={q}',
    'tianchi.aliyun.com': 'https://tianchi.aliyun.com/search?keyword={q}',
}
ORIGIN_TPL = {                                   # 原链接形态（平台首页）→ 同上的搜索模板
    'www.icourse163.org': SEARCH_TPL['www.icourse163.org'],
    'www.bilibili.com': SEARCH_TPL['search.bilibili.com'],
    'www.xuetangx.com': SEARCH_TPL['www.xuetangx.com'],
    'leetcode.cn': SEARCH_TPL['leetcode.cn'],
    'www.kaggle.com': SEARCH_TPL['www.kaggle.com'],
    'www.lanqiao.cn': SEARCH_TPL['www.lanqiao.cn'],
    'www.luogu.com.cn': SEARCH_TPL['www.luogu.com.cn'],
    'tianchi.aliyun.com': SEARCH_TPL['tianchi.aliyun.com'],
}
SEARCH_HOSTS = set(SEARCH_TPL) | {'www.bilibili.com'}
DROP_BRACKET_PREFIX = ('含', '如', '附', '用于', '可选', '参考', '注')

# 人工校准的检索词：标题 → 该学科平台内确实存在的标准关键词
# （MOOC 为精确匹配课程名，用虚构标题做关键词会搜不到，故逐条指定真实存在的课程/主题词）
SEARCH_KEYWORD = {
    # ---- 软件工程 ----
    '软件工程（北京大学）国家精品公开课': '软件工程',
    '《软件工程导论》课堂配套课件': '软件工程导论',
    '敏捷开发与 Scrum 实践': '敏捷开发',
    '需求分析文档模板与范例集': '软件需求分析',
    '软件测试方法专项题库（黑白盒）': '软件测试',
    '软件项目管理与进度计划实验课件': '软件项目管理',
    '软件工程期末复习题库（含答案解析）': '软件工程',
    '代码重构技巧与实例解析': '代码重构',
    '软件需求工程：从获取到验证': '软件需求工程',
    '软件质量保证与度量课件': '软件质量保证',
    '软件工程课程设计任务书（含评分标准）': '软件工程',
    'DevOps 文化与工具链入门': 'DevOps',
    '人机交互与界面设计讲义': '人机交互',
    '软件架构设计模式与演进': '软件架构',
    '软件过程模型对比分析课件': '软件工程',
    '缺陷管理与 Bug 跟踪实践': '软件测试',
    '软件工程专业认证习题集': '软件工程',
    '软件工程文献综述写作指导': '软件工程',
    '领域驱动设计（DDD）入门': '领域驱动设计',
    '软件工程毕业设计选题与实施指南': '软件工程',
    '软件维护与演化讲义': '软件维护',
    '软件工程综合练习题集': '软件工程',
    # ---- 机器学习 ----
    '周志华《机器学习》精读笔记': '机器学习',
    '李航《统计学习方法》配套讲义': '机器学习',
    '斯坦福 CS229 机器学习完整课程': 'CS229',
    'Kaggle 入门实战：Titanic 与房价预测': 'titanic',
    '机器学习期末复习题库': '机器学习',
    '特征工程实战笔记': 'feature engineering',
    '决策树与随机森林专题讲解': '决策树 随机森林',
    '机器学习高频面试问答题集': '机器学习 面试',
    '聚类算法实战：K-Means 与 DBSCAN': '聚类算法',
    '机器学习数学基础讲义': '机器学习',
    '梯度下降与优化算法原理课件': '机器学习',
    '集成学习专题：Bagging 与 Boosting': '集成学习',
    '机器学习课程设计题集（含数据集说明）': '机器学习',
    '天池大数据竞赛入门教程': '机器学习',
    '机器学习白板推导系列': '机器学习 白板推导',
    '电影评分预测实验指导书': '推荐系统',
    # ---- 数据库 ----
    '《数据库系统概论》配套课件': '数据库系统概论',
    '数据库系统原理（哈工大）公开课': '数据库系统',
    '索引原理与查询优化实战': 'MySQL 索引',
    'SQL 实战练习题集': '数据库',
    '事务与并发控制讲义': '数据库',
    '数据库设计与范式理论课件': '数据库设计',
    'MySQL 性能调优实战': 'MySQL 调优',
    'E-R 图设计案例集': '数据库设计',
    '数据库课程设计题库': '数据库',
    '分布式数据库原理与架构': '分布式数据库',
    '数据库期末复习题库': '数据库',
    '关系代数与 SQL 转换专题': '关系代数',
    '数据仓库与数据挖掘实验讲义': '数据仓库',
    '数据库锁机制详解': '数据库 锁',
    '数据库安全与 SQL 注入防护': '数据库安全',
    '数据库系统实现（实验配套）': '数据库',
    'MySQL 索引优化案例题集': '数据库',
    '数据建模工具使用指南': '数据库设计',
    '分库分表与读写分离实践': '分库分表',
    '数据库原理在线自测题库': '数据库原理',
    '数据库运维监控实践课件': '数据库运维',
    '数据库课程实验报告范例': '数据库',
    # ---- 计算机网络 ----
    '计算机网络（哈工大）公开课': '计算机网络',
    '《计算机网络：自顶向下方法》配套课件': '计算机网络',
    'TCP/IP 协议详解系列': 'TCP/IP',
    '网络分层模型与协议栈讲义': '计算机网络',
    '计算机网络期末题库': '计算机网络',
    '子网划分与路由计算专项练习': '计算机网络',
    '三次握手与四次挥手动画讲解': '三次握手',
    '网络安全基础：TLS 与 HTTPS 原理': 'HTTPS 原理',
    '网络排障命令工具箱': '计算机网络',
    'DNS 原理与配置实验课件': 'DNS',
    '网络协议抓包分析案例集': '计算机网络',
    'CDN 与负载均衡原理': 'CDN 负载均衡',
    '网络编程课程设计任务书': '网络编程',
    '无线网络与移动通信讲义': '无线网络',
    '网络性能测试与优化实践': '网络性能',
    '路由协议 RIP 与 OSPF 详解课件': '计算机网络',
    '网络工程认证备考题集': '计算机网络',
    '计算机网络仿真实验指导书': '计算机网络',
    'IPv6 与移动 IP 技术讲座': 'IPv6',
    '防火墙与入侵检测基础': '网络安全',
    '网络协议分析与设计题库': '计算机网络',
    '网络课程知识点思维导图': '计算机网络',
    # ---- 算法 ----
    'LeetCode 算法题库': '算法',
    '《算法导论》核心章节精讲': '算法导论',
    '数据结构与算法（清华邓俊辉）公开课': '数据结构',
    '动态规划专题精讲': '动态规划',
    'LeetCode 高频题解合集': '算法',
    '图论算法入门：最短路与最小生成树': '图论算法',
    '算法复杂度分析讲义': '算法设计与分析',
    '贪心算法经典题集': '贪心',
    'KMP 与字符串匹配算法精讲': 'KMP 算法',
    '二叉搜索树与平衡树实验课件': '数据结构',
    '回溯与剪枝算法专题': '回溯算法',
    '算法期末复习题库': '算法设计与分析',
    '分治算法与归并排序实战': '分治算法',
    '哈希表原理与冲突解决讲义': '数据结构',
    '位运算技巧题库': '位运算',
    '并查集与高级数据结构课件': '数据结构',
    '算法设计与分析（北大）公开课': '算法设计与分析',
    '双指针与滑动窗口题型归纳': '滑动窗口',
    '网络流算法入门讲义': '算法设计与分析',
    '算法竞赛入门经典习题解答': '算法',
    '蓝桥杯算法竞赛真题集': '蓝桥杯',
    '二分查找与答案二分专题': '二分查找',
    '单调栈与单调队列应用课件': '单调栈',
    # ---- Web开发 ----
    '前端工程化与构建工具': '前端工程化',
    'CSS 布局实战：Flex 与 Grid': 'CSS Flex Grid',
    '前端面试题库': '前端面试',
    'Express 与 Koa 接口开发实战': 'Node.js Express',
    '前后端分离项目实战：博客系统': '前后端分离 项目',
    '响应式网页设计课件': 'Web 前端开发',
    'Web 前端课程设计任务书': 'Web 前端开发',
    '单页应用路由原理与实现': '前端路由',
    '全栈项目部署与运维入门': 'Nginx 项目部署',
    'Web 前端实训项目合集': 'Web 前端开发',
    '前端课程实验报告范例': 'Web 前端开发',
    # ---- 人工智能 ----
    '人工智能导论（国家精品课）': '人工智能',
    '计算机视觉入门：CNN 与图像分类': '计算机视觉',
    '自然语言处理基础讲义': '自然语言处理',
    '人工智能期末复习题库': '人工智能',
    'Transformer 与大模型原理详解': 'Transformer',
    '知识图谱构建与应用案例': '知识图谱',
    '计算机视觉课程设计任务书': '计算机视觉',
    '人工智能伦理与安全讲座': '人工智能伦理',
    '语音识别技术入门课件': '语音识别',
    '生成对抗网络（GAN）原理解析': 'GAN 生成对抗网络',
    '人工智能数学基础讲义': '人工智能',
    '智能推荐系统算法实践': '推荐系统',
    '计算机视觉期末题库': '计算机视觉',
    '多模态学习与跨模态检索': '多模态',
    '人工智能实验指导书（Python 实现）': '人工智能',
    'YOLO 系列目标检测算法详解': 'YOLO 目标检测',
    '人工智能竞赛实战题集': '人工智能',
    '智能问答系统设计与实现课件': '自然语言处理',
    '人工智能导论知识点思维导图': '人工智能',
    '机器人感知与决策入门': '机器人 路径规划',
    '人工智能专业英语术语手册': '人工智能',
    '人工智能课程综合设计题库': '人工智能',
}

# 尾缀词（长词优先匹配后剔除，保留核心检索词）
TAIL = [
    '课程综合设计题库', '知识点思维导图', '可视化学习工具集', '经典习题解答', '核心章节精讲',
    '课堂配套课件', '课程配套课件', '配套课件', '期末复习题库', '复习题库', '在线自测题库',
    '课程设计任务书', '竞赛真题集', '真题集', '练习题集', '习题集', '专项练习', '综合练习题集',
    '课程设计题库', '实验报告范例', '实验指导书', '使用手册', '使用指南', '入门指南', '快速入门',
    '完整课程', '白板推导系列', '精读笔记', '学习笔记', '经验笔记', '实战笔记', '可视化演示',
    '国家精品课', '国家精品', '精品课程', '精品资源共享课', '系列', '合集', '公开课', '精品课',
    '课件', '讲义', '题库', '专题',
    '教程', '笔记', '入门', '实战', '精讲', '详解', '解析', '案例集', '任务书', '指导书',
    '课程设计', '期末', '复习', '练习', '专项', '思维导图', '演示', '指南', '手册', '集锦',
]


def keyword(title: str) -> str:
    """从标题提取检索关键词：去书名号、丢弃补充说明型括号、剔尾缀、清标点。"""
    t = title
    t = re.sub(r'[《》【】「」]', '', t)

    def _bracket(m):
        inner = m.group(1)
        return ' ' if inner.startswith(DROP_BRACKET_PREFIX) else f' {inner} '

    t = re.sub(r'[（(]([^）)]*)[）)]', _bracket, t)
    t = re.sub(r'[：:·•—,，、]', ' ', t)                 # 连字符是术语的一部分（E-R / K-Means），不拆
    for _ in range(2):                                   # 两轮，处理叠加尾缀
        for w in sorted(TAIL, key=len, reverse=True):
            t = t.replace(w, ' ')
    t = re.sub(r'\s+', ' ', t).strip()
    # 只丢弃"纯中文单字"碎片（如拆剩的"课"），保留 E / R / K 这类英文术语字母
    t = ' '.join(p for p in t.split(' ') if not (len(p) == 1 and '\u4e00' <= p <= '\u9fff'))
    return t or title.strip()


def refine(url: str, title: str) -> str:
    """首页/搜索页 → 按校准检索词生成的搜索页；具体页面 → 原样保留。"""
    p = urllib.parse.urlparse(url)
    host = p.netloc
    q = SEARCH_KEYWORD.get(title) or keyword(title)       # 优先人工校准词，缺省回退机械提取
    if host in SEARCH_TPL:                               # 已是搜索链接 → 重算（幂等）
        return SEARCH_TPL[host].format(q=urllib.parse.quote(q))
    if (p.path or '/').strip('/'):                        # 已精确到具体页面 → 保留
        return url
    tpl = ORIGIN_TPL.get(host)                            # 平台首页 → 站内搜索
    if not tpl:
        return url                                         # 官方文档/教材官网首页即正确落点
    return tpl.format(q=urllib.parse.quote(q))


# ---------- 生成新清单 ----------
new_res = {}
changed = 0
samples = []
uncovered = []
for cat, items in RESOURCES.items():
    new_items = []
    for (title, rtype, diff, url, desc) in items:
        host = urllib.parse.urlparse(url).netloc
        if host in SEARCH_TPL and title not in SEARCH_KEYWORD:      # 搜索型但缺校准词 → 需补
            uncovered.append(f'{cat} | {title}')
        nu = refine(url, title)
        if nu != url:
            changed += 1
            if len(samples) < 12:
                samples.append((title, url, nu))
        new_items.append((title, rtype, diff, nu, desc))
    new_res[cat] = new_items

print(f'精化 {changed} 条（共 {sum(len(v) for v in new_res.values())} 条）')
print(f'已校准检索词: {len(SEARCH_KEYWORD)} 条')
if uncovered:
    print(f'⚠️ 缺校准词的搜索型条目 {len(uncovered)} 条（将回退机械提取）:')
    for x in uncovered:
        print('   ', x)
else:
    print('✅ 全部搜索型条目均有校准检索词')
print()
print('=== 精化示例（标题 / 原链接 → 新链接）===')
for t, o, n in samples:
    print(f'  {t}')
    print(f'    {o}')
    print(f'    → {n}')

# ---------- 重写 real_resources.py ----------
HEADER = '''# -*- coding: utf-8 -*-
"""真实学习资源清单（方案 A）

用途：替换 resource 表的文案层（title/type/difficulty/description/url），
      resource_id 保持不变，因此评分矩阵、收藏、行为日志与离线指标零影响。

字段：(标题, 类型, 难度1-5, 链接, 简介)
链接策略：能定位到具体页面的用具体页面（官方文档 / 教程 / 题库）；
      课程类资源定位不到唯一官方页时，使用平台站内搜索链接（关键词取自标题），
      避免"标题是某门课、链接却是平台首页"的不匹配。
数量与现有分类分布严格一致：软件工程28 机器学习27 数据库33 计算机网络27 算法26 Web开发34 人工智能29 = 204
"""

RESOURCES = {
'''


def dump(data):
    lines = [HEADER]
    for cat, items in data.items():
        lines.append(f'    "{cat}": [')
        for (t, ty, d, u, desc) in items:
            lines.append(f'        ({t!r}, {ty!r}, {d}, {u!r},')
            lines.append(f'         {desc!r}),')
        lines.append('    ],')
    lines.append('}')
    return '\n'.join(lines) + '\n'


with open(SRC, 'w', encoding='utf-8') as f:
    f.write(dump(new_res))
print('\nreal_resources.py 已重写')

# ---------- 更新数据库 ----------
con = sqlite3.connect(DB)
cur = con.cursor()
updated = 0
for cat, items in new_res.items():
    ids = [r[0] for r in cur.execute(
        "SELECT id FROM resource WHERE category=? ORDER BY id", (cat,)).fetchall()]
    for rid, (_t, _ty, _d, u, _desc) in zip(ids, items):
        cur.execute("UPDATE resource SET url=? WHERE id=?", (u, rid))
        updated += 1
con.commit()
print(f'数据库更新 {updated} 条')

print('\n=== 抽样核对（标题 → 链接）===')
for r in cur.execute("SELECT title, url FROM resource ORDER BY RANDOM() LIMIT 8"):
    print(f'  {r[0][:30]:<32} {r[1][:88]}')
con.close()
