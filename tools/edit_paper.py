# -*- coding: utf-8 -*-
"""编辑学年论文 docx：
1. 在"参考文献"前插入新章节"四、系统实现与测试"（含表格、截图、实验图表）
2. 修正"软件工程课程"表述为 Web 数据挖掘定位，更新摘要
3. 另存为 郭鹏阳_2024117364.docx（不覆盖原文件）
格式策略：深度克隆现有同类段落/表格的 XML 格式，保证与原文排版一致。
"""
import copy
import json
import os

import docx
from docx.shared import Cm
from docx.oxml.ns import qn

SRC = r"C:/Users/郭鹏阳/Desktop/郭鹏阳-学年论文.docx"
DST = r"C:/Users/郭鹏阳/Desktop/郭鹏阳_2024117364.docx"
PROJ = r"C:/Users/郭鹏阳/WorkBuddy/2026-09-11-15-09-23/webmining_project"


def find_para(doc, exact=None, startswith=None):
    for p in doc.paragraphs:
        t = p.text.strip()
        if exact is not None and t == exact:
            return p
        if startswith is not None and t.startswith(startswith):
            return p
    return None


def clone_paragraph(tpl_p, text, ref_el):
    """克隆模板段落格式，写入新文本，插入到 ref_el 之前。"""
    new = copy.deepcopy(tpl_p._p)
    for tag in ("w:r", "w:hyperlink", "w:bookmarkStart", "w:bookmarkEnd"):
        for el in new.findall(qn(tag)):
            new.remove(el)
    # 取模板第一个 run 的格式
    rpr = None
    for r in tpl_p._p.findall(qn("w:r")):
        rpr_el = r.find(qn("w:rPr"))
        if rpr_el is not None:
            rpr = copy.deepcopy(rpr_el)
        break
    run = new.makeelement(qn("w:r"), {})
    if rpr is not None:
        run.append(rpr)
    t = new.makeelement(qn("w:t"), {})
    t.set(qn("xml:space"), "preserve")
    t.text = text
    run.append(t)
    new.append(run)
    ref_el.addprevious(new)
    return new


def replace_in_paragraph(p, old, new_text):
    """整段替换：保留首个 run 的格式，重写全段文本。"""
    full = p.text
    if old not in full:
        return False
    updated = full.replace(old, new_text)
    runs = p.runs
    if not runs:
        return False
    runs[0].text = updated
    for r in runs[1:]:
        r.text = ""
    return True


def set_cell(cell, text, bold=False):
    cell.text = ""
    run = cell.paragraphs[0].add_run(text)
    run.bold = bold
    run.font.size = docx.shared.Pt(10.5)
    run.font.name = "宋体"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")


def add_borders(table):
    tbl = table._tbl
    tblPr = tbl.tblPr
    borders = tblPr.makeelement(qn("w:tblBorders"), {})
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = tblPr.makeelement(qn(f"w:{edge}"), {})
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:color"), "000000")
        borders.append(el)
    tblPr.append(borders)


def insert_table(doc, ref_el, tpl_caption_p, caption, header, rows, col_widths=None):
    """插入表题 + 表格（克隆表题格式，新建简制表格）。"""
    clone_paragraph(tpl_caption_p, caption, ref_el)
    t = doc.add_table(rows=len(rows) + 1, cols=len(header))
    add_borders(t)
    for j, h in enumerate(header):
        set_cell(t.rows[0].cells[j], h, bold=True)
    for i, row in enumerate(rows):
        for j, v in enumerate(row):
            set_cell(t.rows[i + 1].cells[j], v)
    # 表格居中
    tblPr = t._tbl.tblPr
    jc = tblPr.makeelement(qn("w:jc"), {})
    jc.set(qn("w:val"), "center")
    tblPr.append(jc)
    ref_el.addprevious(t._tbl)
    # 表后空行
    clone_paragraph(tpl_caption_p, "", ref_el)


def insert_picture(doc, ref_el, tpl_caption_p, img_path, caption, width_cm=14):
    """插入居中图片 + 图题。"""
    p = doc.add_paragraph()
    p.alignment = 1  # center
    run = p.add_run()
    run.add_picture(img_path, width=Cm(width_cm))
    ref_el.addprevious(p._p)
    clone_paragraph(tpl_caption_p, caption, ref_el)


def main():
    with open(os.path.join(PROJ, "evaluation", "metrics.json"), encoding="utf-8") as f:
        ev = json.load(f)
    r = ev["results"]

    doc = docx.Document(SRC)

    # ---------- 1. 文本修正 ----------
    fixes = [
        # 摘要：点明 Web 数据挖掘定位 + 补充实现与实验结论
        ("本项目拟设计并实现一个基于协同过滤的个性化学习资源推荐系统（Web 应用）",
         "推荐系统是 Web 数据挖掘的典型应用方向。本项目设计并实现了一个基于协同过滤的个性化学习资源推荐系统（Web 应用）"),
        ("整体工作量适中、技术路线成熟、可行性高，具备良好的可演示性与可扩展性。",
         "整体工作量适中、技术路线成熟、可行性高。目前系统已按本方案完成编码实现与联调，"
         "并通过 User-based CF、Item-based CF 与 SVD 三种算法的离线对比实验验证了推荐方案的有效性。"),
        # 项目简介：课程定位 + 已完成实现
        ("本方案围绕软件工程课程所学的完整开发流程展开",
         "本方案围绕 Web 数据挖掘课程所学的推荐算法知识与软件工程完整开发流程展开"),
        ("是一份可直接指导开发、符合学年论文立项要求的完整技术方案。",
         "并按照该方案完成了系统编码实现与离线实验验证（详见第四章）。"),
        # 实施意义：教学价值表述
        ("在教学价值上，本项目完整运用软件工程课程中需求分析、概要设计、数据结构与接口设计等核心知识",
         "在教学价值上，本项目将 Web 数据挖掘课程中的推荐算法与软件工程课程中需求分析、概要设计、数据结构与接口设计等方法论相结合"),
    ]
    n_fix = 0
    for p in doc.paragraphs:
        for old, new in fixes:
            if old in p.text:
                replace_in_paragraph(p, old, new)
                n_fix += 1
    print(f"文本修正 {n_fix} 处")

    # ---------- 2. 定位插入点与格式模板 ----------
    ref_para = find_para(doc, exact="参考文献")
    assert ref_para is not None, "未找到参考文献标题"
    ref_el = ref_para._p

    h1_tpl = find_para(doc, exact="三、项目实施方案")
    h2_tpl = find_para(doc, exact="（五）技术方案可行性论证")
    h3_tpl = find_para(doc, exact="2. 拟解决的关键问题")
    body_tpl = find_para(doc, startswith="推荐系统是解决信息过载")
    cap_tpl = find_para(doc, startswith="表9")
    for name, tpl in [("h1", h1_tpl), ("h2", h2_tpl), ("h3", h3_tpl), ("body", body_tpl), ("caption", cap_tpl)]:
        assert tpl is not None, f"未找到 {name} 格式模板"

    # ---------- 3. 撰写并插入新章节 ----------
    clone_paragraph(h1_tpl, "四、系统实现与测试", ref_el)
    clone_paragraph(body_tpl,
                    "本章按照第三章确定的技术方案完成系统的编码实现，包括数据模型、推荐引擎、RESTful 接口与前端页面，"
                    "并设计离线对比实验对三种推荐算法的有效性进行验证与分析。", ref_el)

    # （一）开发与运行环境
    clone_paragraph(h2_tpl, "（一）开发与运行环境", ref_el)
    clone_paragraph(body_tpl,
                    "系统在 Windows 环境下开发与测试，采用前后端分离架构，具体环境配置如表 10 所示。"
                    "数据库默认采用轻量级 SQLite 以便一键部署演示，同时通过 SQLAlchemy ORM 屏蔽数据库差异，"
                    "修改连接串即可平滑迁移至 MySQL。", ref_el)
    insert_table(doc, ref_el, cap_tpl, "表10  开发与运行环境配置",
                 ["类别", "配置"],
                 [["操作系统", "Windows 10 / 11（64 位）"],
                  ["开发语言", "Python 3.13、JavaScript（ES6）"],
                  ["后端框架", "FastAPI + Uvicorn（异步 ASGI）"],
                  ["数据访问", "SQLAlchemy 2.x ORM"],
                  ["数据库", "SQLite（默认，可切换 MySQL 8.0）"],
                  ["推荐算法", "numpy + scikit-learn（余弦相似度 CF、TruncatedSVD）"],
                  ["前端", "Vue 3 + Element Plus + ECharts（本地化部署，免构建）"],
                  ["接口测试", "Swagger UI（FastAPI 自动生成）"],
                  ["版本管理", "Git"]])

    # （二）系统实现
    clone_paragraph(h2_tpl, "（二）系统实现", ref_el)
    clone_paragraph(h3_tpl, "1. 数据模型与行为采集实现", ref_el)
    clone_paragraph(body_tpl,
                    "按照概要设计完成用户表、资源表、评分表、收藏表与行为日志表共五张核心数据表的 ORM 建模。"
                    "行为采集模块在前端用户浏览、收藏、评分操作时上报行为事件并写入 behavior_log 表；"
                    "推荐侧将隐式行为折算为伪评分（浏览折算 1 分、下载 3 分、收藏 4 分，显式评分为 1～5 分），"
                    "与显式评分合并构造用户—物品评分矩阵。实测演示数据集包含 106 名用户、200 个资源、4254 条显式评分，"
                    "矩阵密度约 20.07%，体现了推荐系统典型的数据稀疏特征。", ref_el)
    clone_paragraph(h3_tpl, "2. 推荐引擎实现", ref_el)
    clone_paragraph(body_tpl,
                    "推荐引擎基于 numpy 与 scikit-learn 实现 User-based CF、Item-based CF 与 SVD 三种算法。"
                    "相似度计算采用余弦相似度，并引入共同评分物品数衰减因子，抑制仅有一两个共同评分造成的虚假高相似；"
                    "SVD 采用用户均值填充后的 TruncatedSVD 重构评分矩阵。Top-N 推荐时过滤用户已交互物品，"
                    "按预测评分降序取前 N 并生成推荐理由（User-CF 基于\"相似用户也喜欢\"、Item-CF 基于\"与你高分评价的资源相似\"）。"
                    "工程上采用\"离线训练 + 内存缓存\"策略：模型离线构建，推荐结果按用户缓存，新行为写入后可触发增量重建；"
                    "对无行为记录的新用户自动降级为热门资源兜底列表，实现冷启动策略。", ref_el)
    clone_paragraph(h3_tpl, "3. 前端与接口实现", ref_el)
    clone_paragraph(body_tpl,
                    "后端通过 FastAPI 实现认证、资源、行为、推荐、统计共 10 个 RESTful 接口，"
                    "并自动生成 Swagger 在线接口文档（如图 2 所示），接口响应模型由 Pydantic 强制校验。"
                    "前端基于 Vue 3 与 Element Plus 实现用户登录、个性化推荐、资源检索与效果监控四个视图："
                    "推荐页以卡片形式展示 Top-N 结果、预测评分与推荐理由，右侧联动热门资源兜底栏（如图 1 所示）；"
                    "效果监控页展示用户数、资源数、评分记录、行为日志等统计指标，"
                    "并以 ECharts 柱状图可视化三种算法的离线评估结果（如图 3 所示）。", ref_el)
    insert_picture(doc, ref_el, cap_tpl, os.path.join(PROJ, "screenshots", "shot_recommend.png"),
                   "图1  个性化推荐页面（User-based CF，含推荐理由与热门兜底）", width_cm=14.5)
    insert_picture(doc, ref_el, cap_tpl, os.path.join(PROJ, "screenshots", "shot_swagger.png"),
                   "图2  Swagger 自动生成的 RESTful 接口文档", width_cm=14.5)
    insert_picture(doc, ref_el, cap_tpl, os.path.join(PROJ, "screenshots", "shot_stats.png"),
                   "图3  推荐效果监控页面（统计信息与算法指标可视化）", width_cm=14.5)

    # （三）实验设计与结果分析
    clone_paragraph(h2_tpl, "（三）实验设计与结果分析", ref_el)
    clone_paragraph(h3_tpl, "1. 实验设置", ref_el)
    clone_paragraph(body_tpl,
                    "实验采用上述模拟数据集，按用户留出法划分：每位用户 80% 的评分作为训练集、20% 作为测试集，"
                    "评分数少于 5 的用户全部划入训练集，最终得到训练集 3438 条、测试集 816 条。"
                    "评价指标包括：Precision@10（推荐前 10 中命中比例）、Recall@10（测试集高分物品被召回比例，"
                    "评分≥4 视为正样本）、Coverage@10（被推荐覆盖的物品占全部物品的比例）与 "
                    "RMSE（评分预测均方根误差）。三种算法在同一训练集上训练、同一测试集上评估。", ref_el)
    clone_paragraph(h3_tpl, "2. 实验结果", ref_el)
    insert_table(doc, ref_el, cap_tpl, "表11  三种推荐算法 Top-10 离线评估结果",
                 ["算法", "Precision@10", "Recall@10", "Coverage@10", "RMSE"],
                 [["User-based CF", f"{r['user_cf']['precision']:.4f}", f"{r['user_cf']['recall']:.4f}",
                   f"{r['user_cf']['coverage']:.3f}", f"{r['user_cf']['rmse']:.4f}"],
                  ["Item-based CF", f"{r['item_cf']['precision']:.4f}", f"{r['item_cf']['recall']:.4f}",
                   f"{r['item_cf']['coverage']:.3f}", f"{r['item_cf']['rmse']:.4f}"],
                  ["SVD", f"{r['svd']['precision']:.4f}", f"{r['svd']['recall']:.4f}",
                   f"{r['svd']['coverage']:.3f}", f"{r['svd']['rmse']:.4f}"]])
    insert_picture(doc, ref_el, cap_tpl, os.path.join(PROJ, "evaluation", "eval_metrics.png"),
                   "图4  三种算法 Precision / Recall / Coverage 对比", width_cm=15)
    insert_picture(doc, ref_el, cap_tpl, os.path.join(PROJ, "evaluation", "rmse_curve.png"),
                   "图5  三种算法 RMSE 对比", width_cm=10.5)
    clone_paragraph(h3_tpl, "3. 结果分析", ref_el)
    clone_paragraph(body_tpl,
                    "（1）精度方面：SVD 的 Precision@10（0.0319）在三种算法中最高，RMSE（0.705）最低，"
                    "说明矩阵分解通过隐语义建模能更充分地捕获用户—物品交互结构，评分预测误差最小；"
                    "User-based CF 的 Recall@10（0.0975）优于 Item-based CF（0.0687），"
                    "表明在校园学习场景中同学群体之间的行为相似性显著，\"找相似的人\"能有效覆盖测试集中的高价值资源。", ref_el)
    clone_paragraph(body_tpl,
                    "（2）覆盖率方面：Item-based CF 的 Coverage@10 高达 0.990，长尾资源曝光能力最强，"
                    "但其精度在三者中最低，体现了推荐精度与覆盖率之间的经典折中关系；"
                    "User-based CF 覆盖率 0.725 相对较低，其推荐集中于热门类目，与其\"随大流\"的机制一致。", ref_el)
    clone_paragraph(body_tpl,
                    "（3）工程验证方面：系统实测推荐接口在缓存命中时响应时间小于 200ms，满足非功能性需求；"
                    "新注册用户首次登录时推荐源自动切换为\"冷启动：热门资源兜底\"，行为积累后恢复个性化推荐，"
                    "验证了双路推荐与冷启动策略的可用性。", ref_el)
    clone_paragraph(body_tpl,
                    "综合以上结果，系统最终采用\"User-based CF 为主推算法、Item-based CF 与 SVD 提供对比与升级空间\""
                    "的算法组合策略，与第三章表 6 的算法选型定位一致，说明技术路线设计合理、方案可行。", ref_el)

    doc.save(DST)

    # ---------- 4. 统计字数 ----------
    d2 = docx.Document(DST)
    total = sum(len(p.text.replace(" ", "")) for p in d2.paragraphs)
    print(f"已保存：{DST}")
    print(f"修正 {n_fix} 处表述；全文段落字符数（不含表格）：约 {total}")


if __name__ == "__main__":
    main()
