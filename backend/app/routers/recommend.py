"""个性化推荐路由 —— Top-N 推荐（含冷启动兜底）/ 热门资源

注意：/api/recommend/hot 为字面量路径，必须注册在 /{user_id} 之前，
否则 "hot" 会被当作 int 解析失败导致 422。
"""
from datetime import datetime
from itertools import combinations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.security import get_current_user
from app.services import cooldown_elapsed, get_engine, mark_dirty, maybe_retrain, train_engine

router = APIRouter(prefix="/api/recommend", tags=["个性化推荐"])

VALID_ALGOS = ("user_cf", "item_cf", "svd")
ALGO_NAME = {"user_cf": "User-CF 协同过滤", "item_cf": "Item-CF 协同过滤", "svd": "SVD 隐语义模型"}


@router.get("/hot")
def hot(limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    eng = get_engine()
    if eng.popularity is None:
        train_engine(db)
    return {"items": eng.hot_resources(limit=limit), "total": limit}


@router.get("/compare")
def compare(n: int = Query(8, ge=1, le=20), db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    """三种算法并排对比（同一用户）：各算法 Top-N + 两两重合度，用于比较不同算法的推荐差异。

    注意：字面量路径必须注册在 /{user_id} 之前，否则 "compare" 会被当作 int 解析失败。
    """
    eng = get_engine()
    if eng.matrix is None or not eng.is_user_known(user.id):
        u = db.get(User, user.id)
        # 冷启动兜底重训：加冷却节流，避免"有兴趣但无法进入矩阵"的用户反复触发全量训练
        if u and (u.interests or "").strip() and cooldown_elapsed():
            train_engine(db)
    else:
        maybe_retrain(db)          # 与 /{user_id} 口径一致：脏标记到期时先重训再对比
    eng = get_engine()
    known = eng.is_user_known(user.id)

    out, errors = {}, {}
    for algo in VALID_ALGOS:
        try:
            if known:
                out[algo] = eng.recommend(user.id, n=n, algo=algo)
            else:
                out[algo] = eng.hot_resources(limit=n)
        except Exception as e:                      # 如 SVD 未训练成功，单列失败不影响其他列
            out[algo] = []
            errors[algo] = f"该算法暂不可用（{type(e).__name__}）"

    # 两两重合度：按资源 ID 求交集大小
    idsets = {a: {(it.get('resource_id') or it.get('id')) for it in out[a]} for a in VALID_ALGOS}
    overlap = {f"{a}|{b}": len(idsets[a] & idsets[b]) for a, b in combinations(VALID_ALGOS, 2)}

    return {"known": known, "n": n,
            "algos": {a: {"name": ALGO_NAME[a], "items": out[a], "error": errors.get(a)}
                      for a in VALID_ALGOS},
            "overlap": overlap,
            "unique_count": len(idsets['user_cf'] | idsets['item_cf'] | idsets['svd']),
            "model_time": datetime.fromtimestamp(eng.trained_at).strftime("%Y-%m-%d %H:%M:%S")}


@router.get("/{user_id}")
def recommend(user_id: int, n: int = Query(10, ge=1, le=50), algo: str = "user_cf",
              refresh: int = 0, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    # 越权保护：只能查看自己的推荐（管理员可查看任意用户，便于排查）
    if user_id != user.id and user.role != "admin":
        raise HTTPException(403, "只能查看自己的推荐结果")
    if algo not in VALID_ALGOS:
        raise HTTPException(400, f"不支持的推荐算法，可选：{'/'.join(VALID_ALGOS)}")
    eng = get_engine()
    if refresh:
        # refresh 触发全库重训练（含 SVD），成本高——仅管理员可主动触发，防止被滥用为 DoS
        if user.role != "admin":
            raise HTTPException(403, "强制刷新模型仅管理员可用")
        train_engine(db)
    elif eng.matrix is None:
        train_engine(db)
    else:
        # 行为变化后的延迟重训：冷却期后的第一个推荐请求自动合并重训一次
        maybe_retrain(db)
    if not eng.is_user_known(user_id):
        # 新注册的兴趣用户：引擎尚未见过该用户时自动重训练，使其首屏即个性化。
        # 冷却节流：若引擎刚训练过仍不认识该用户（如兴趣类别下无资源），不再重复全量训练。
        u = db.get(User, user_id)
        if u and (u.interests or "").strip() and cooldown_elapsed():
            train_engine(db)
    eng = get_engine()
    if eng.is_user_known(user_id):
        try:
            items = eng.recommend(user_id, n=n, algo=algo)
        except Exception:                            # 如 SVD 模型异常，退化为热门兜底而非 500
            items = eng.hot_resources(limit=n)
            source = "推荐模型暂不可用，已退化为热门资源"
            return {"user_id": user_id, "algo": algo, "source": source,
                    "model_time": datetime.fromtimestamp(eng.trained_at).strftime("%Y-%m-%d %H:%M:%S"),
                    "items": items, "total": len(items)}
        source = f"个性化推荐（{algo}）"
    else:
        items = eng.hot_resources(limit=n)   # 冷启动兜底
        source = "冷启动：热门资源兜底"
    return {"user_id": user_id, "algo": algo, "source": source,
            "model_time": datetime.fromtimestamp(eng.trained_at).strftime("%Y-%m-%d %H:%M:%S"),
            "items": items, "total": len(items)}
