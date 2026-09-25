"""业务服务层 —— 交互数据汇总、物品元数据、推荐引擎训练、兴趣冷启动"""
import logging
from collections import Counter
import os

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import UPLOAD_DIR

logger = logging.getLogger(__name__)
from app.models import BehaviorLog, Resource, Score, User
from app.recommender import ACTION_WEIGHT, implicit_to_score
from app.recommender import engine as rec_engine

COLD_MIN_INTERACTIONS = 3     # 行为数少于该值视为冷启动用户
COLD_PSEUDO_TOPK = 30         # 每个冷启动用户最多注入的兴趣类伪评分条数


def collect_interactions(db: Session):
    """汇总显式评分 + 隐式行为折算评分，构建交互列表。

    只纳入在线（online）资源的交互：下架/待审核资源不应进入推荐矩阵，
    否则其历史评分仍会把它们推上推荐列表，出现空白标题的「幽灵推荐」。
    """
    online_ids = {rid for (rid,) in db.query(Resource.id).filter(Resource.status == "online")}
    best = {}  # (user, resource) -> score（取最大强度）
    for s in db.query(Score).all():
        if s.resource_id not in online_ids:
            continue
        best[(s.user_id, s.resource_id)] = max(best.get((s.user_id, s.resource_id), 0), s.score)
    agg = db.query(BehaviorLog.user_id, BehaviorLog.resource_id, BehaviorLog.action,
                   func.count(BehaviorLog.id)).group_by(
        BehaviorLog.user_id, BehaviorLog.resource_id, BehaviorLog.action).all()
    for uid, rid, action, cnt in agg:
        if rid not in online_ids or action == "rate":
            continue
        raw = (ACTION_WEIGHT.get(action, 1) or 1) * cnt
        score = implicit_to_score(raw)
        key = (uid, rid)
        if score > best.get(key, 0):
            best[key] = score
    return [{"user_id": k[0], "resource_id": k[1], "score": v} for k, v in best.items()]


def load_item_meta(db: Session):
    """在线资源的元数据（推荐理由生成用）。"""
    return {r.id: {"title": r.title, "category": r.category, "type": r.type,
                   "difficulty": r.difficulty}
            for r in db.query(Resource).filter(Resource.status == "online")}


def inject_interest_pseudo(db: Session, inter: list, meta: dict) -> list:
    """兴趣标签冷启动：为"行为数少且填了兴趣类别"的用户注入伪评分。

    原理：冷启动用户对其兴趣类别下的热门资源赋予 4.0~4.5 的伪评分，
    使协同过滤能立刻找到"同兴趣的老用户"近邻，实现个性化冷启动推荐；
    真实行为积累（>= COLD_MIN_INTERACTIONS 条）后不再注入，自然过渡。
    """
    cnt_by_user = Counter(i["user_id"] for i in inter)
    item_pop = Counter(i["resource_id"] for i in inter)
    existing = {(i["user_id"], i["resource_id"]) for i in inter}

    cold_users = db.query(User).filter(User.interests.isnot(None), User.interests != "").all()
    injected = 0
    for u in cold_users:
        if cnt_by_user.get(u.id, 0) >= COLD_MIN_INTERACTIONS:
            continue                                    # 已有足够真实行为，不注入
        cats = {c.strip() for c in u.interests.split(",") if c.strip()}
        cand = sorted((rid for rid, m in meta.items() if m.get("category") in cats),
                      key=lambda rid: -item_pop.get(rid, 0))[:COLD_PSEUDO_TOPK]
        for rid in cand:
            if (u.id, rid) in existing:
                continue
            score = 4.0 + min(item_pop.get(rid, 0), 20) / 20 * 0.5   # 4.0~4.5，热门微加成
            inter.append({"user_id": u.id, "resource_id": rid, "score": round(score, 2)})
            existing.add((u.id, rid))
            injected += 1
    if injected:
        logger.info("冷启动：为 %d 个兴趣用户注入伪评分 %d 条", len(cold_users), injected)
    return inter


def train_engine(db: Session):
    """离线训练推荐引擎，返回交互记录数。互斥锁保证并发请求不会同时 fit。"""
    inter = collect_interactions(db)
    meta = load_item_meta(db)
    inter = inject_interest_pseudo(db, inter, meta)
    rec_engine.fit(inter, meta)      # fit 内部持引擎锁，与预测互斥
    return len(inter)


def get_engine():
    return rec_engine


# ---- 脏标记延迟重训：行为变化后不立刻全量重训，合并到冷却期后的第一个请求 ----
import time as _time

_dirty = {"flag": False}
RETRAIN_COOLDOWN = 60              # 距上次训练的最小间隔（秒），冷却期内多次行为合并为一次重训


def mark_dirty():
    """行为发生变化（评分/收藏/删除等改变矩阵数据源）时置脏标记，等待延迟重训。"""
    _dirty["flag"] = True


def clear_dirty():
    """手动重训后清除脏标记，避免紧接着的推荐请求再触发一次冗余训练。"""
    _dirty["flag"] = False


def cooldown_elapsed() -> bool:
    """距上次训练是否已超过冷却期（供冷启动兜底重训做节流，防止被高频请求刷成全量训练）。"""
    return rec_engine.trained_at == 0 or (_time.time() - rec_engine.trained_at) >= RETRAIN_COOLDOWN


def maybe_retrain(db: Session):
    """推荐请求入口调用：脏标记存在且已过冷却期时执行一次重训练。

    非阻塞拿锁：已有请求在训练/预测时直接返回 False（本次仍用旧模型，下个请求再补）。
    """
    if not _dirty["flag"]:
        return False
    if _time.time() - rec_engine.trained_at < RETRAIN_COOLDOWN:
        return False               # 冷却期内：先返回当前模型，合并稍后统一重训
    if not rec_engine._lock.acquire(blocking=False):
        return False               # 其他线程正在训练/读取
    try:
        _dirty["flag"] = False     # 拿到锁后再清标记，训练期间新置脏不会被吞
        train_engine(db)
        return True
    finally:
        rec_engine._lock.release()


def remove_upload_file(stored_name: str) -> bool:
    """按存储文件名删除 UPLOAD_DIR 下的附件，返回是否真的删了文件。

    防御点：只接受纯文件名，含路径分隔符一律拒绝（防路径穿越）。
    """
    if not stored_name or os.path.basename(stored_name) != stored_name:
        return False
    path = os.path.join(UPLOAD_DIR, stored_name)
    try:
        if os.path.isfile(path):
            os.remove(path)
            return True
    except OSError:
        pass
    return False


def remove_resource_file(resource) -> bool:
    """删除资源对应的磁盘文件（资源被删除/换附件时调用），返回是否真的删了文件。"""
    return remove_upload_file(getattr(resource, "file_path", "") or "")
