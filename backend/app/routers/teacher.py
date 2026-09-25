"""教师工作台路由 —— 我的上传（编辑/删除）、上传新资源（仅本人资源可操作）"""
import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import ALLOWED_UPLOAD_EXT, MAX_UPLOAD_MB, UPLOAD_DIR
from app.db import get_db
from app.models import BehaviorLog, Favorite, Notification, Resource, Score, User
from app.schemas import ResourceIn
from app.security import require_roles
from app.services import mark_dirty, remove_resource_file, remove_upload_file

router = APIRouter(prefix="/api/teacher", tags=["教师工作台"],
                   dependencies=[Depends(require_roles("teacher", "admin"))])


def _delete_resource_cascade(db: Session, resource_id: int):
    """删除资源及其关联评分/收藏/行为记录，并同步删除磁盘上的附件文件。"""
    for m in (Score, Favorite, BehaviorLog):
        db.query(m).filter(m.resource_id == resource_id).delete(synchronize_session=False)
    r = db.get(Resource, resource_id)
    if r:
        db.delete(r)
        mark_dirty()      # 矩阵数据源已变化
        db.commit()       # 先提交成功再删磁盘文件（commit 失败时不丢附件）
        remove_resource_file(r)


@router.post("/resources/upload")
async def upload_file(file: UploadFile = File(...),
                      user: User = Depends(require_roles("teacher", "admin"))):
    """接收教师拖拽/选择上传的资源文件：校验类型与大小，重命名后落盘。

    注意：必须注册在 /resources/{resource_id} 之类参数路由之前，避免路径被吃掉。
    """
    original = os.path.basename(file.filename or "").strip() or "未命名文件"
    ext = os.path.splitext(original)[1].lower()
    if ext not in ALLOWED_UPLOAD_EXT:
        raise HTTPException(400, f"不支持的文件类型「{ext or '未知'}」，请上传文档 / 课件 / 音视频 / 压缩包等常见格式")
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    stored = uuid.uuid4().hex + ext          # 重命名存储：防重名覆盖、防路径穿越
    dest = os.path.join(UPLOAD_DIR, stored)
    limit = MAX_UPLOAD_MB * 1024 * 1024
    size = 0
    try:
        with open(dest, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise HTTPException(400, f"文件超过 {MAX_UPLOAD_MB}MB 上限，请压缩后再上传")
                out.write(chunk)
    except BaseException:
        if os.path.exists(dest):            # 失败清理半截文件
            try:
                os.remove(dest)
            except OSError:
                pass
        raise
    if size < 1024:
        size_txt = f"{size} B"
    elif size < 1024 * 1024:
        size_txt = f"{size / 1024:.0f} KB"
    else:
        size_txt = f"{size / 1024 / 1024:.1f} MB"
    return {"file_name": original, "file_size": size, "file_path": stored,
            "message": f"文件上传成功（{size_txt}）"}


@router.get("/my-resources")
def my_resources(db: Session = Depends(get_db), user: User = Depends(require_roles("teacher", "admin"))):
    """我上传的资源列表（含热度与平均分统计）。"""
    rows = (db.query(Resource, func.avg(Score.score), func.count(Score.id))
            .outerjoin(Score, Score.resource_id == Resource.id)
            .filter(Resource.uploader_id == user.id)
            .group_by(Resource.id)
            .order_by(Resource.id.desc())
            .all())
    return {"items": [{
        "id": r.id, "title": r.title, "type": r.type, "category": r.category,
        "difficulty": r.difficulty, "status": r.status,
        "click_count": r.click_count, "url": r.url or "",
        "description": r.description or "",
        "file_name": r.file_name or "", "file_size": r.file_size or 0,
        "has_file": bool(r.file_path),
        "avg_score": round(float(avg or 0), 2), "ratings": cnt,
        "created_at": r.created_at.strftime("%Y-%m-%d") if r.created_at else "",
    } for r, avg, cnt in rows], "total": len(rows)}


@router.post("/resources")
def upload_resource(data: ResourceIn, db: Session = Depends(get_db),
                    user: User = Depends(require_roles("teacher", "admin"))):
    """上传新资源：教师上传进入待审核，管理员直接上架。"""
    r = Resource(**data.model_dump(), uploader_id=user.id,
                 status="online" if user.role == "admin" else "pending")
    db.add(r)
    db.commit()
    msg = "资源发布成功" if r.status == "online" else "资源已提交，等待管理员审核通过后上架"
    return {"id": r.id, "status": r.status, "message": msg}


@router.put("/resources/{resource_id}")
def update_resource(resource_id: int, data: ResourceIn, db: Session = Depends(get_db),
                    user: User = Depends(require_roles("teacher", "admin"))):
    """编辑自己上传的资源（仅本人可改）。

    审核流一致性：已上架资源被教师修改后置回「待审核」，防止绕过审核直接生效；
    管理员编辑不受此限。
    附件处理：允许随编辑替换附件（file_path 由上传接口返回值写入，格式受 schema 正则约束），
    替换后清理磁盘上的旧附件，避免留下孤儿文件。
    """
    r = db.get(Resource, resource_id)
    if not r or r.uploader_id != user.id:
        raise HTTPException(404, "资源不存在或无权操作")
    old_file = r.file_path
    for k, v in data.model_dump().items():
        setattr(r, k, v)
    replaced = bool(old_file) and old_file != r.file_path
    if r.status == "online" and user.role != "admin":
        r.status = "pending"
        db.add(Notification(user_id=user.id, ntype="review", title="资源已修改，等待重新审核",
                            content=f"你修改了《{r.title}》，修改内容将在管理员重新审核通过后上架。"))
        db.commit()          # 状态回退与通知同一事务
        if replaced:
            remove_upload_file(old_file)
        mark_dirty()
        return {"message": "资源已更新，因修改了已上架内容，需管理员重新审核后上架"}
    db.commit()
    if replaced:
        remove_upload_file(old_file)   # 提交成功后再删旧附件（commit 失败不丢文件）
    mark_dirty()
    return {"message": "资源已更新"}


@router.delete("/resources/{resource_id}")
def delete_resource(resource_id: int, db: Session = Depends(get_db),
                    user: User = Depends(require_roles("teacher", "admin"))):
    """删除自己上传的资源（仅本人可删）。"""
    r = db.get(Resource, resource_id)
    if not r or r.uploader_id != user.id:
        raise HTTPException(404, "资源不存在或无权操作")
    _delete_resource_cascade(db, resource_id)
    return {"message": "资源已删除"}
