"""业务服务层 —— 交互数据汇总、物品元数据、推荐引擎训练、兴趣冷启动"""
from collections import Counter
import os

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import UPLOAD_DIR
from app.models import BehaviorLog, Resource, Score, User
from app.recommender import ACTION_WEIGHT, implicit_to_score
from app.recommender import engine as rec_engine

COLD_MIN_INTERACTIONS = 3     # 行为数少于该值视为冷启动用户
COLD_PSEUDO_TOPK = 30         # 每个冷启动用户最多注入的兴趣类伪评分条数


def collect_interactions(db: Session):
    """汇总显式评分 + 隐式行为折算评分，构建交互列表。"""
    best = {}  # (user, resource) -> score（取最大强度）
    for s in db.query(Score).all():
        best[(s.user_id, s.resource_id)] = max(best.get((s.user_id, s.resource_id), 0), s.score)
    agg = db.query(BehaviorLog.user_id, BehaviorLog.resource_id, BehaviorLog.action,
                   func.count(BehaviorLog.id)).group_by(
        BehaviorLog.user_id, BehaviorLog.resource_id, BehaviorLog.action).all()
    for uid, rid, action, cnt in agg:
        if action == "rate":
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
        print(f"[冷启动] 为 {len(cold_users)} 个兴趣用户注入伪评分 {injected} 条")
    return inter


def train_engine(db: Session):
    """离线训练推荐引擎，返回交互记录数。互斥锁保证并发请求不会同时 fit。"""
    inter = collect_interactions(db)
    meta = load_item_meta(db)
    inter = inject_interest_pseudo(db, inter, meta)
    with _train_lock:
        rec_engine.fit(inter, meta)
    return len(inter)


def get_engine():
    return rec_engine


# ---- 脏标记延迟重训：行为变化后不立刻全量重训，合并到冷却期后的第一个请求 ----
import threading
import time as _time

_train_lock = threading.RLock()    # 训练互斥（可重入：maybe_retrain 持锁后再调 train_engine）
_dirty = {"flag": False}
RETRAIN_COOLDOWN = 60              # 距上次训练的最小间隔（秒），冷却期内多次行为合并为一次重训


def mark_dirty():
    """行为发生变化（评分/收藏/删除等改变矩阵数据源）时置脏标记，等待延迟重训。"""
    _dirty["flag"] = True


def maybe_retrain(db: Session):
    """推荐请求入口调用：脏标记存在且已过冷却期时执行一次重训练。

    非阻塞拿锁：已有请求在训练时直接返回 False（本次仍用旧模型，下个请求再补）。
    """
    if not _dirty["flag"]:
        return False
    if _time.time() - rec_engine.trained_at < RETRAIN_COOLDOWN:
        return False               # 冷却期内：先返回当前模型，合并稍后统一重训
    if not _train_lock.acquire(blocking=False):
        return False               # 其他线程正在训练
    try:
        _dirty["flag"] = False     # 拿到锁后再清标记，训练期间新置脏不会被吞
        train_engine(db)
        return True
    finally:
        _train_lock.release()


def remove_resource_file(resource) -> bool:
    """删除资源对应的磁盘文件（资源被删除时调用），返回是否真的删了文件。

    防御点：file_path 只允许是 UPLOAD_DIR 下的纯文件名，禁止路径穿越。
    """
    name = getattr(resource, "file_path", "") or ""
    if not name:
        return False
    if os.path.basename(name) != name:        # 含路径分隔符 → 视为非法，拒绝删除
        return False
    path = os.path.join(UPLOAD_DIR, name)
    try:
        if os.path.isfile(path):
            os.remove(path)
            return True
    except OSError:
        pass
    return False
