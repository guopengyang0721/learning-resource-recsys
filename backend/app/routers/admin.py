"""管理后台路由 —— 数据看板 / 资源审核与管理 / 用户管理（仅管理员）"""
import json
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import EVAL_METRICS_PATH
from app.db import get_db
from app.models import BehaviorLog, Favorite, Notification, Resource, Score, TeacherInvite, User
from app.schemas import BroadcastIn, ResetPwdIn, StatusIn
from app.security import hash_pwd, require_admin
from app.services import collect_interactions, get_engine, mark_dirty, remove_resource_file

router = APIRouter(prefix="/api/admin", tags=["管理后台"],
                   dependencies=[Depends(require_admin)])


# ---------- 数据看板 ----------
@router.get("/stats/recommend")
def stats(db: Session = Depends(get_db)):
    eng = get_engine()
    u_cnt = db.query(User).count()
    r_cnt = db.query(Resource).filter(Resource.status == "online").count()
    s_cnt = db.query(Score).count()
    log_cnt = db.query(BehaviorLog).count()
    inter = collect_interactions(db)
    density = len(inter) / max(u_cnt * r_cnt, 1)
    # 库内聚合，避免把整张行为日志表拉进内存
    action_cnt = dict(db.query(BehaviorLog.action, func.count(BehaviorLog.id))
                      .group_by(BehaviorLog.action).all())

    metrics = None
    try:
        with open(EVAL_METRICS_PATH, encoding="utf-8") as f:
            metrics = json.load(f)
    except (OSError, json.JSONDecodeError):      # 文件缺失或内容损坏都不应导致 500
        pass

    return {"users": u_cnt, "resources": r_cnt, "scores": s_cnt, "logs": log_cnt,
            "interactions": len(inter), "matrix_density": round(density * 100, 2),
            "action_count": action_cnt,
            "model_trained_at": datetime.fromtimestamp(eng.trained_at).strftime("%Y-%m-%d %H:%M:%S"),
            "offline_metrics": metrics}


@router.get("/stats/dashboard")
def dashboard(db: Session = Depends(get_db)):
    """数据看板全量数据：核心统计 + 离线指标 + 分类分布 + 行为占比 + 热门 Top10 + 最近流水。"""
    eng = get_engine()
    u_cnt = db.query(User).count()
    r_cnt = db.query(Resource).filter(Resource.status == "online").count()
    s_cnt = db.query(Score).count()
    log_cnt = db.query(BehaviorLog).count()
    inter = collect_interactions(db)
    density = len(inter) / max(u_cnt * r_cnt, 1)
    # 分类分布与行为占比均走库内聚合（原实现把整表资源/日志拉进内存统计）
    cat_dist = {c or "其他": n for c, n in
                db.query(Resource.category, func.count(Resource.id))
                .filter(Resource.status == "online").group_by(Resource.category).all()}
    action_cnt = dict(db.query(BehaviorLog.action, func.count(BehaviorLog.id))
                      .group_by(BehaviorLog.action).all())

    metrics = None
    try:
        with open(EVAL_METRICS_PATH, encoding="utf-8") as f:
            metrics = json.load(f)
    except (OSError, json.JSONDecodeError):
        pass

    top = (db.query(Resource).filter(Resource.status == "online")
           .order_by(Resource.click_count.desc()).limit(10).all())
    top_items = [{"id": r.id, "title": r.title, "category": r.category,
                  "click_count": r.click_count} for r in top]

    logs = (db.query(BehaviorLog, User.nickname, Resource.title)
            .join(User, BehaviorLog.user_id == User.id)
            .join(Resource, BehaviorLog.resource_id == Resource.id)
            .order_by(BehaviorLog.id.desc()).limit(30).all())
    recent = [{"id": b.id, "user": nick, "title": title, "action": b.action,
               "time": b.created_at.strftime("%m-%d %H:%M")}
              for b, nick, title in logs]

    return {"users": u_cnt, "resources": r_cnt, "scores": s_cnt, "logs": log_cnt,
            "interactions": len(inter), "matrix_density": round(density * 100, 2),
            "model_trained_at": datetime.fromtimestamp(eng.trained_at).strftime("%Y-%m-%d %H:%M:%S"),
            "offline_metrics": metrics,
            "category_dist": cat_dist, "action_count": action_cnt,
            "top_resources": top_items, "recent_logs": recent,
            "pending_cnt": db.query(Resource).filter(Resource.status == "pending").count(),
            "disabled_cnt": db.query(User).filter(User.status == "disabled").count()}


@router.get("/stats/trend")
def stats_trend(db: Session = Depends(get_db)):
    """近 7 天趋势：每日新增行为数与活跃用户数（双折线数据源）。"""
    since = datetime.now() - timedelta(days=7)
    rows = (db.query(func.date(BehaviorLog.created_at).label("d"),
                     func.count(BehaviorLog.id).label("cnt"),
                     func.count(func.distinct(BehaviorLog.user_id)).label("users"))
            .filter(BehaviorLog.created_at >= since)
            .group_by("d").all())
    by_day = {str(r.d): (r.cnt, r.users) for r in rows}
    days = []
    for i in range(6, -1, -1):
        d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        cnt, users = by_day.get(d, (0, 0))
        days.append({"date": d[5:], "behaviors": cnt, "users": users})
    return {"days": days}


# ---------- 资源审核与管理 ----------
@router.get("/resources")
def list_all_resources(keyword: str = "", status: str = "",
                       page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=100),
                       db: Session = Depends(get_db)):
    q = (db.query(Resource, User.username)
         .outerjoin(User, Resource.uploader_id == User.id))
    if keyword:
        q = q.filter(Resource.title.contains(keyword))
    if status:
        q = q.filter(Resource.status == status)
    total = q.count()
    rows = q.order_by(Resource.id.desc()).offset((page - 1) * size).limit(size).all()
    return {"total": total, "page": page, "items": [{
        "id": r.id, "title": r.title, "type": r.type, "category": r.category,
        "status": r.status, "click_count": r.click_count,
        "uploader": uname or "-", "difficulty": r.difficulty,
        "created_at": r.created_at.strftime("%Y-%m-%d") if r.created_at else "",
    } for r, uname in rows]}


@router.put("/resources/{resource_id}/status")
def set_resource_status(resource_id: int, data: StatusIn, db: Session = Depends(get_db)):
    """上架 / 下架 / 送审，并向资源上传者发送审核结果通知。"""
    status_name = {"pending": "重新提交审核", "online": "审核通过，已上架",
                   "offline": "未通过审核/已下架"}
    if data.status not in status_name:
        raise HTTPException(400, "非法状态")
    r = db.get(Resource, resource_id)
    if not r:
        raise HTTPException(404, "资源不存在")
    r.status = data.status
    name = status_name[data.status]
    # 审核结果通知上传者（uploader_id 可能为空：上传者已被删除时资源转为匿名）
    if r.uploader_id:
        db.add(Notification(user_id=r.uploader_id, ntype="review",
                            title=f"资源审核结果：{name}",
                            content=f"你上传的《{r.title}》{name}。"))
    db.commit()          # 状态与通知同一事务，避免"改了状态没发通知"
    mark_dirty()         # 可见资源口径变化（上架/下架），待冷却后自动刷新模型
    return {"message": f"《{r.title}》已设为「{name}」", "status": r.status}


# ---------- 推荐模型 ----------
@router.post("/retrain")
def retrain_model(db: Session = Depends(get_db)):
    """手动触发推荐模型全量重训练（前端管理看板「重新训练模型」按钮）。"""
    from app.services import clear_dirty, train_engine
    n = train_engine(db)
    clear_dirty()        # 已全量重训：清掉脏标记，避免随即再触发一次冗余训练
    return {"message": f"推荐模型已重新训练（交互记录 {n} 条）", "interactions": n}


# ---------- 数据导出 CSV ----------
def _csv_cell(v) -> str:
    """单元格转义：引号成对 + 危险前缀（=+-@\t\r）加单引号，防公式注入（Excel 打开导出文件时执行）。"""
    s = str(v)
    if s[:1] in ("=", "+", "-", "@", "\t", "\r"):
        s = "'" + s
    return '"' + s.replace('"', '""') + '"'


def _csv_response(filename: str, header: list, rows) -> Response:
    """CSV 响应：UTF-8 带 BOM（Excel 直接打开不乱码）。

    注意：调用方用 yield_per 分批取行可降低 ORM 对象峰值，但 body 仍是整体拼接，
    超大数据量时应改用 StreamingResponse。
    """
    lines = [",".join(_csv_cell(h) for h in header)]
    lines += [",".join(_csv_cell(v) for v in row) for row in rows]
    body = "\ufeff" + "\n".join(lines)
    return Response(content=body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


@router.get("/export/users")
def export_users(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id).all()
    rows = [(u.id, u.username, u.nickname, u.role, u.status,
             u.gender or "", u.grade or "", u.college or "",
             u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else "")
            for u in users]
    return _csv_response(f"users_{datetime.now():%Y%m%d}.csv",
                         ["ID", "用户名", "昵称", "角色", "状态", "性别", "年级", "学院", "注册时间"],
                         rows)


@router.get("/export/resources")
def export_resources(db: Session = Depends(get_db)):
    scores_agg = {rid: (avg, cnt) for rid, avg, cnt in (
        db.query(Score.resource_id, func.avg(Score.score), func.count(Score.id))
        .group_by(Score.resource_id).all())}
    res = db.query(Resource).order_by(Resource.id).all()
    rows = [(r.id, r.title, r.category, r.type, r.difficulty, r.status,
             r.click_count,
             round(float(scores_agg.get(r.id, (0, 0))[0] or 0), 2),
             scores_agg.get(r.id, (0, 0))[1],
             (r.url or "")[:200],
             r.created_at.strftime("%Y-%m-%d") if r.created_at else "")
            for r in res]
    return _csv_response(f"resources_{datetime.now():%Y%m%d}.csv",
                         ["ID", "标题", "分类", "类型", "难度", "状态", "点击数",
                          "平均分", "评分人数", "链接", "创建日期"],
                         rows)


@router.get("/export/behaviors")
def export_behaviors(db: Session = Depends(get_db)):
    """行为日志量级最大，流式读取避免一次性载入内存。"""
    logs = (db.query(BehaviorLog, User.username, Resource.title)
            .join(User, BehaviorLog.user_id == User.id)
            .join(Resource, BehaviorLog.resource_id == Resource.id)
            .order_by(BehaviorLog.id)
            .yield_per(1000))
    rows = ((b.id, b.user_id, username, b.resource_id, title, b.action,
             b.value, b.created_at.strftime("%Y-%m-%d %H:%M:%S"))
            for b, username, title in logs)
    return _csv_response(f"behaviors_{datetime.now():%Y%m%d}.csv",
                         ["日志ID", "用户ID", "用户名", "资源ID", "资源标题", "行为", "强度", "时间"],
                         rows)


@router.post("/notifications/broadcast")
def broadcast(data: BroadcastIn, db: Session = Depends(get_db)):
    """系统公告：为全体用户创建通知副本。"""
    users = db.query(User.id).filter(User.status == "active").all()
    db.add_all([Notification(user_id=uid, title=data.title.strip()[:100],
                             content=data.content.strip(), ntype="system")
                for (uid,) in users])
    db.commit()
    return {"message": f"公告已发送给 {len(users)} 位用户", "count": len(users)}


@router.delete("/resources/{resource_id}")
def delete_resource(resource_id: int, db: Session = Depends(get_db)):
    """删除资源及其关联评分/收藏/行为记录，并同步删除磁盘附件。"""
    r = db.get(Resource, resource_id)
    if not r:
        raise HTTPException(404, "资源不存在")
    for m in (Score, Favorite, BehaviorLog):
        db.query(m).filter(m.resource_id == resource_id).delete(synchronize_session=False)
    title = r.title
    db.delete(r)
    mark_dirty()          # 矩阵数据源已变化
    db.commit()           # 先提交成功再删磁盘文件（commit 失败时不丢附件）
    remove_resource_file(r)
    return {"message": f"《{title}》已删除"}


# ---------- 用户管理 ----------
@router.get("/users")
def list_users(keyword: str = "",
               page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=100),
               db: Session = Depends(get_db)):
    q = db.query(User)
    if keyword:
        q = q.filter(User.username.contains(keyword) | User.nickname.contains(keyword))
    total = q.count()
    rows = q.order_by(User.id).offset((page - 1) * size).limit(size).all()
    ids = [u.id for u in rows]
    score_cnt = dict(db.query(Score.user_id, func.count(Score.id))
                     .filter(Score.user_id.in_(ids)).group_by(Score.user_id).all()) if ids else {}
    log_cnt = dict(db.query(BehaviorLog.user_id, func.count(BehaviorLog.id))
                   .filter(BehaviorLog.user_id.in_(ids)).group_by(BehaviorLog.user_id).all()) if ids else {}
    fav_cnt = dict(db.query(Favorite.user_id, func.count(Favorite.id))
                   .filter(Favorite.user_id.in_(ids)).group_by(Favorite.user_id).all()) if ids else {}
    return {"total": total, "page": page, "items": [{
        "id": u.id, "username": u.username, "nickname": u.nickname, "role": u.role,
        "status": u.status or "active",
        "interests": (u.interests or "").split(",") if u.interests else [],
        "scores": score_cnt.get(u.id, 0), "logs": log_cnt.get(u.id, 0),
        "favorites": fav_cnt.get(u.id, 0),
        "created_at": u.created_at.strftime("%Y-%m-%d") if u.created_at else "",
    } for u in rows]}


@router.post("/users/invite-codes")
def generate_invite_code(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """生成教师注册邀请码（一次性）。require_admin 已在路由级依赖，此处再取 admin 对象便于记录生成者。"""
    code = secrets.token_hex(6).upper()          # 12 位大写十六进制（48 bit 随机度，抗猜解）
    while db.query(TeacherInvite).filter(TeacherInvite.code == code).count():
        code = secrets.token_hex(6).upper()
    inv = TeacherInvite(code=code, created_by=admin.id)
    db.add(inv)
    db.commit()
    return {"code": inv.code, "message": f"邀请码 {code} 已生成，发给教师后在注册页选择「教师」身份并填写即可"}


@router.get("/users/invite-codes")
def list_invite_codes(db: Session = Depends(get_db)):
    codes = (db.query(TeacherInvite, User.username)
             .outerjoin(User, TeacherInvite.used_by == User.id)
             .order_by(TeacherInvite.id.desc()).limit(50).all())
    return {"items": [{
        "code": inv.code,
        "created_at": inv.created_at.strftime("%Y-%m-%d %H:%M") if inv.created_at else "",
        "used": bool(inv.used_by),
        "used_by": username or "",
        "used_at": inv.used_at.strftime("%Y-%m-%d %H:%M") if inv.used_at else "",
    } for inv, username in codes], "total": len(codes)}


@router.put("/users/{user_id}/status")
def set_user_status(user_id: int, data: StatusIn, db: Session = Depends(get_db),
                    admin: User = Depends(require_admin)):
    """禁用 / 启用账号（不能禁用自己和其他管理员）。"""
    if data.status not in ("active", "disabled"):
        raise HTTPException(400, "非法状态")
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "用户不存在")
    if u.id == admin.id:
        raise HTTPException(400, "不能禁用自己")
    if u.role == "admin" and data.status == "disabled":
        raise HTTPException(400, "不能禁用其他管理员账号")
    u.status = data.status
    db.commit()
    return {"message": f"账号 {u.username} 已{'禁用' if data.status == 'disabled' else '启用'}"}


@router.put("/users/{user_id}/password")
def reset_password(user_id: int, data: ResetPwdIn, db: Session = Depends(get_db),
                   admin: User = Depends(require_admin)):
    """管理员重置用户密码（不能重置其他管理员——防止管理员间账号接管）。"""
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "用户不存在")
    if u.role == "admin" and u.id != admin.id:
        raise HTTPException(400, "不能重置其他管理员账号的密码")
    u.password_hash = hash_pwd(data.new_password)
    db.commit()
    return {"message": f"账号 {u.username} 的密码已重置"}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    """删除用户及其全部关联数据（不能删除自己和其他管理员）。"""
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "用户不存在")
    if u.id == admin.id:
        raise HTTPException(400, "不能删除自己的账号")
    if u.role == "admin":
        raise HTTPException(400, "不能删除管理员账号")
    # 其上传的资源转为匿名保留（置空署名），避免悬空引用
    res_cnt = (db.query(Resource).filter(Resource.uploader_id == user_id)
               .update({Resource.uploader_id: None}, synchronize_session=False))
    # 其用过的邀请码解除绑定（码保持"已使用"状态，避免悬空引用且可追溯）
    db.query(TeacherInvite).filter(TeacherInvite.used_by == user_id).update(
        {TeacherInvite.used_by: None}, synchronize_session=False)
    # 级联清理：评分 / 收藏 / 行为记录 / 通知
    for m in (Score, Favorite, BehaviorLog, Notification):
        db.query(m).filter(m.user_id == user_id).delete(synchronize_session=False)
    mark_dirty()   # 评分矩阵数据源（评分/行为）已变化，置脏标记触发延迟重训
    name = u.username
    db.delete(u)
    db.commit()
    tail = f"；名下 {res_cnt} 条资源已转为匿名保留" if res_cnt else ""
    return {"message": f"账号 {name} 及其关联数据已删除{tail}", "resources_kept": res_cnt}
