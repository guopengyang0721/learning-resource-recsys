"""行为采集路由 —— 浏览 / 收藏 / 评分 / 下载行为上报"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import BehaviorLog, Favorite, Resource, Score, User
from app.schemas import BehaviorIn
from app.security import get_current_user
from app.services import mark_dirty

VALID_ACTIONS = ("view", "favorite", "rate", "download")

router = APIRouter(tags=["行为采集"], dependencies=[Depends(get_current_user)])


@router.post("/api/behavior")
def report_behavior(data: BehaviorIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """上报浏览/评分/收藏行为。身份一律取自登录令牌，忽略请求体中的 user_id（防冒充）。"""
    if data.action not in VALID_ACTIONS:
        raise HTTPException(400, "不支持的行为类型")
    if data.action == "rate" and not (1 <= data.value <= 5):
        raise HTTPException(400, "评分行为的分值必须为 1~5")   # 避免"记了行为却无评分"的脏数据
    r = db.get(Resource, data.resource_id)
    if not r:
        raise HTTPException(404, "资源不存在")
    db.add(BehaviorLog(user_id=user.id, resource_id=data.resource_id,
                       action=data.action, value=data.value))
    if data.action == "view":
        # SQL 原子自增：避免"读-改-写"在并发下丢计数
        db.query(Resource).filter(Resource.id == data.resource_id).update(
            {Resource.click_count: func.coalesce(Resource.click_count, 0) + 1},
            synchronize_session=False)
    if data.action == "rate" and 1 <= data.value <= 5:
        exists = db.query(Score).filter_by(user_id=user.id,
                                           resource_id=data.resource_id).first()
        if exists:
            exists.score = data.value
        else:
            db.add(Score(user_id=user.id, resource_id=data.resource_id, score=data.value))
    mark_dirty()                     # 行为矩阵已变化：置脏标记，冷却期后的推荐请求会自动重训
    db.commit()
    return {"message": "行为已记录"}


@router.post("/api/favorites/{resource_id}")
def add_favorite(resource_id: int, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """收藏资源。身份取自令牌（不接收 user_id 参数），并校验资源存在。"""
    if not db.get(Resource, resource_id):
        raise HTTPException(404, "资源不存在")
    if db.query(Favorite).filter_by(user_id=user.id, resource_id=resource_id).count():
        return {"message": "已收藏"}
    db.add(Favorite(user_id=user.id, resource_id=resource_id))
    db.add(BehaviorLog(user_id=user.id, resource_id=resource_id, action="favorite", value=4))
    mark_dirty()
    db.commit()
    return {"message": "收藏成功"}


@router.delete("/api/favorites/{resource_id}")
def remove_favorite(resource_id: int, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """取消收藏（身份取自令牌；只移除收藏关系，保留行为记录供推荐使用）。"""
    fav = db.query(Favorite).filter_by(user_id=user.id, resource_id=resource_id).first()
    if not fav:
        raise HTTPException(404, "该资源不在收藏中")
    db.delete(fav)
    db.commit()
    return {"message": "已取消收藏"}
