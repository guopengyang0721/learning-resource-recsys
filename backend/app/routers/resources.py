"""资源管理路由 —— 列表检索 / 详情 / 相似推荐 / 文件下载（资源上传由 teacher 路由负责）"""
import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import UPLOAD_DIR
from app.db import get_db
from app.models import BehaviorLog, Favorite, Resource, Score, User
from app.security import get_current_user
from app.services import get_engine, mark_dirty, train_engine

VALID_TYPES = ("video", "doc", "ppt", "question", "book", "course")
VALID_DAYS = (0, 7, 30, 180)

router = APIRouter(prefix="/api/resources", tags=["资源管理"],
                   dependencies=[Depends(get_current_user)])


@router.get("")
def list_resources(keyword: str = "", category: str = "", difficulty: int = 0,
                   type: str = "", sort: str = "hot", days: int = 0,
                   page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=100),
                   db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """资源检索筛选：
    - type: 资源类型多选，逗号分隔（video,doc,ppt,question,book,course）
    - sort: hot 热度最高（默认）/ rating 评分最高 / new 最新上传 / difficulty 难度升序
    - days: 上传时间范围（0 全部 / 7 / 30 / 180 天）
    """
    q = db.query(Resource).filter(Resource.status == "online")
    if keyword:
        q = q.filter(Resource.title.contains(keyword) | Resource.description.contains(keyword))
    if category:
        q = q.filter(Resource.category == category)
    if difficulty:
        q = q.filter(Resource.difficulty == difficulty)
    types = [t.strip() for t in (type or "").split(",") if t.strip() in VALID_TYPES]
    if types:
        q = q.filter(Resource.type.in_(types))
    if days in VALID_DAYS and days > 0:
        q = q.filter(Resource.created_at >= datetime.now() - timedelta(days=days))

    # 排序：rating 需联表聚合平均分（无评分按 0 计）
    if sort == "rating":
        q = (q.outerjoin(Score, Score.resource_id == Resource.id)
              .group_by(Resource.id)
              .order_by(func.coalesce(func.avg(Score.score), 0).desc(),
                        Resource.click_count.desc()))
    elif sort == "new":
        q = q.order_by(Resource.created_at.desc())
    elif sort == "difficulty":
        q = q.order_by(Resource.difficulty.asc(), Resource.click_count.desc())
    else:  # hot（默认）
        q = q.order_by(Resource.click_count.desc())

    total = q.count()
    rows = q.offset((page - 1) * size).limit(size).all()
    # 当前用户收藏标记（前端据此显示"已收藏"）
    ids = [r.id for r in rows]
    fav_ids = set()
    if ids:
        fav_ids = {f.resource_id for f in db.query(Favorite).filter(
            Favorite.user_id == user.id, Favorite.resource_id.in_(ids)).all()}
    return {"total": total, "page": page, "items": [
        {"id": r.id, "title": r.title, "type": r.type, "category": r.category,
         "difficulty": r.difficulty, "click_count": r.click_count, "description": r.description,
         "favorited": r.id in fav_ids}
        for r in rows]}


@router.get("/{resource_id}")
def resource_detail(resource_id: int, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    r = db.get(Resource, resource_id)
    if not r:
        raise HTTPException(404, "资源不存在")
    # 与列表口径一致：待审核/已下架资源不对外（管理员与上传者本人可看）
    if r.status != "online" and user.role != "admin" and r.uploader_id != user.id:
        raise HTTPException(404, "资源不存在")
    avg = db.query(func.avg(Score.score)).filter(Score.resource_id == resource_id).scalar()
    favorited = db.query(Favorite).filter_by(user_id=user.id, resource_id=resource_id).count() > 0
    return {"id": r.id, "title": r.title, "type": r.type, "category": r.category,
            "difficulty": r.difficulty, "click_count": r.click_count,
            "description": r.description, "url": r.url or "", "avg_score": round(float(avg or 0), 2),
            "file_name": r.file_name or "", "file_size": r.file_size or 0,
            "has_file": bool(r.file_path),
            "favorited": favorited}


@router.get("/{resource_id}/download")
def download_resource(resource_id: int, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """下载资源附件（教师上传的文件），并记一条 download 行为用于推荐。"""
    r = db.get(Resource, resource_id)
    if not r:
        raise HTTPException(404, "资源不存在")
    # 与列表口径一致：待审核/已下架资源的附件不对外
    if r.status != "online" and user.role != "admin" and r.uploader_id != user.id:
        raise HTTPException(404, "资源不存在")
    name = r.file_path or ""
    if not name or os.path.basename(name) != name:      # 无附件或非法路径
        raise HTTPException(404, "该资源没有可下载的附件")
    path = os.path.join(UPLOAD_DIR, name)
    if not os.path.isfile(path):
        raise HTTPException(404, "附件文件已丢失，请联系上传者重新上传")
    db.add(BehaviorLog(user_id=user.id, resource_id=resource_id, action="download"))
    # SQL 原子自增：避免"读-改-写"在并发下丢计数
    db.query(Resource).filter(Resource.id == resource_id).update(
        {Resource.click_count: func.coalesce(Resource.click_count, 0) + 1},
        synchronize_session=False)
    mark_dirty()                     # download 行为参与推荐折算（权重 3），矩阵已变化
    db.commit()
    return FileResponse(path, filename=r.file_name or name, media_type="application/octet-stream")


@router.get("/{resource_id}/similar")
def similar_resources(resource_id: int, n: int = 5, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """"看了又看"：基于 Item-CF 的相似资源推荐。"""
    eng = get_engine()
    if eng.item_sim is None:
        train_engine(db)
    r = db.get(Resource, resource_id)
    if not r:
        raise HTTPException(404, "资源不存在")
    # 与详情口径一致：待审核/已下架资源不对外（避免经 base_title 探测）
    if r.status != "online" and user.role != "admin" and r.uploader_id != user.id:
        raise HTTPException(404, "资源不存在")
    items = eng.similar_items(resource_id, n=n)
    return {"base_id": resource_id, "base_title": r.title,
            "items": items, "total": len(items)}
