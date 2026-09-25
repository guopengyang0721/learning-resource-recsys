"""个人中心路由 —— 浏览历史 / 我的收藏（身份取自登录令牌，不信任前端传参）"""
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (ACTION_NAME, BehaviorLog, Favorite, Notification,
                        Resource, TeacherInvite, User)
from app.ratelimit import (LOCK_SECONDS, record_failure, record_success,
                           remaining_lock_seconds)
from app.schemas import ChangePwdIn, InterestsIn, ProfileIn, SetSecIn, UpgradeTeacherIn
from app.security import get_current_user, hash_pwd, make_token, verify_pwd
from app.services import RETRAIN_COOLDOWN, get_engine, mark_dirty, train_engine

router = APIRouter(prefix="/api/user", tags=["个人中心"])


@router.get("/interests")
def get_interests(user: User = Depends(get_current_user)):
    return {"interests": (user.interests or "").split(",") if user.interests else []}


@router.put("/interests")
def update_interests(data: InterestsIn, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """更新兴趣类别并重训练。距上次训练不足冷却期时置脏标记，由后续请求延迟重训。"""
    user.interests = ",".join(dict.fromkeys(data.interests))[:200]
    db.commit()
    if time.time() - get_engine().trained_at >= RETRAIN_COOLDOWN:
        n = train_engine(db)
        return {"message": "兴趣已更新，推荐已重新训练", "interests": data.interests, "interactions": n}
    mark_dirty()
    return {"message": "兴趣已更新，推荐将稍后自动刷新", "interests": data.interests}


@router.put("/profile")
def update_profile(data: ProfileIn, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """修改个人资料：昵称/性别/年级/学院。密码修改走独立的 /change-password 接口。"""
    user.nickname = data.nickname.strip() or user.nickname
    user.gender = data.gender if data.gender in ("男", "女", "保密") else user.gender
    user.grade = data.grade.strip()[:20]
    user.college = data.college.strip()[:50]
    db.commit()
    return {"message": "资料已更新",
            "nickname": user.nickname, "gender": user.gender,
            "grade": user.grade, "college": user.college}


@router.put("/security-question")
def set_security_question(data: SetSecIn, db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)):
    """设置/修改密保问题（需当前密码校验），用于忘记密码自助找回。"""
    if not verify_pwd(data.password, user.password_hash):
        raise HTTPException(400, "当前密码错误，无法设置密保问题")
    user.sec_question = data.question.strip()[:100]
    user.sec_answer_hash = hash_pwd(data.answer.strip().lower())
    db.commit()
    return {"message": "密保问题已设置，忘记密码时可用其自助找回"}


# ---------- 消息通知 ----------
@router.get("/notifications")
def my_notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """最近 30 条通知列表；未读数单独 COUNT 全量统计（不受列表截断影响）。"""
    rows = (db.query(Notification).filter(Notification.user_id == user.id)
            .order_by(Notification.id.desc()).limit(30).all())
    unread = (db.query(func.count(Notification.id))
              .filter(Notification.user_id == user.id, Notification.is_read == 0)
              .scalar() or 0)
    return {"items": [{
        "id": n.id, "title": n.title, "content": n.content, "ntype": n.ntype,
        "is_read": n.is_read,
        "time": n.created_at.strftime("%m-%d %H:%M") if n.created_at else "",
    } for n in rows], "unread": int(unread), "total": len(rows)}


# ---------- 修改密码 ----------
@router.post("/change-password")
def change_password(data: ChangePwdIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """修改密码（独立于资料编辑）：验证旧密码 → 更新。令牌不依赖密码，改后仍有效。

    旧密码试错同样限流（以用户 ID 为键），防止持有过期令牌的攻击者暴力猜测。
    """
    lock_left = remaining_lock_seconds(f"uid:{user.id}")
    if lock_left:
        raise HTTPException(429, f"尝试次数过多，请约 {max(lock_left // 60, 1)} 分钟后再试")
    if not verify_pwd(data.old_password, user.password_hash):
        locked = record_failure(f"uid:{user.id}")
        msg = "旧密码错误"
        if locked:
            msg += f"，错误次数过多已锁定 {max(LOCK_SECONDS // 60, 1)} 分钟"
        raise HTTPException(400, msg)
    record_success(f"uid:{user.id}")
    if data.old_password == data.new_password:
        raise HTTPException(400, "新密码不能与旧密码相同")
    user.password_hash = hash_pwd(data.new_password)
    db.commit()
    return {"message": "密码已修改，下次登录请使用新密码"}


# ---------- 身份升级 ----------
@router.post("/upgrade-to-teacher")
def upgrade_to_teacher(data: UpgradeTeacherIn, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    """学生凭一次性邀请码升级为教师：只改 role 字段，评分/收藏/行为等历史数据全部保留。"""
    if user.role != "student":
        raise HTTPException(400, "当前账号已是教师/管理员，无需升级")
    code = data.invite_code.strip().upper()
    invite = db.query(TeacherInvite).filter(TeacherInvite.code == code).first()
    if not invite:
        raise HTTPException(400, "邀请码无效，请核对后重试")
    # 原子消费：仅当仍未使用时更新，并发下只有一个请求成功
    rc = (db.query(TeacherInvite)
          .filter(TeacherInvite.id == invite.id, TeacherInvite.used_by.is_(None))
          .update({"used_by": user.id, "used_at": datetime.now()}, synchronize_session=False))
    if rc != 1:
        raise HTTPException(400, "该邀请码已被使用，请联系管理员重新发放")
    user.role = "teacher"
    db.add(Notification(user_id=user.id, ntype="system", title="已升级为教师身份",
                        content="恭喜！你现在可以在教师工作台上传和管理资源了，历史学习数据均已保留。"))
    db.commit()
    return {"user_id": user.id, "username": user.username, "role": user.role,
            "status": user.status, "nickname": user.nickname, "gender": user.gender or "保密",
            "grade": user.grade or "", "college": user.college or "",
            "has_sec_question": bool(user.sec_question),
            "interests": (user.interests or "").split(",") if user.interests else [],
            "token": make_token(user.id, user.role),      # 令牌内含 role，升级后必须换发
            "message": "升级成功！你已成为教师，可以使用教师工作台了"}


@router.post("/notifications/{nid}/read")
def mark_notification(nid: int, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    n = db.get(Notification, nid)
    if not n or n.user_id != user.id:
        raise HTTPException(404, "通知不存在")
    n.is_read = 1
    db.commit()
    return {"message": "已标记已读"}


@router.post("/notifications/read-all")
def read_all_notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.query(Notification).filter(Notification.user_id == user.id,
                                  Notification.is_read == 0).update({Notification.is_read: 1})
    db.commit()
    return {"message": "全部已读"}


# ---------- 学习画像 ----------
@router.get("/portrait")
def portrait(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """学习画像：当前用户行为按资源类别的分布（雷达图数据源）。"""
    rows = (db.query(Resource.category, func.count(BehaviorLog.id))
            .join(Resource, BehaviorLog.resource_id == Resource.id)
            .filter(BehaviorLog.user_id == user.id)
            .group_by(Resource.category).all())
    counts = {c or "其他": n for c, n in rows}
    return {"distribution": counts, "total": sum(counts.values())}


@router.get("/weekly")
def weekly(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """个人学习周报：近 7 天行为统计 + 每日趋势 + 分类覆盖。"""
    now = datetime.now()                 # 全函数统一取一次，避免午夜瞬间日期错位
    since = now - timedelta(days=7)
    recent = (db.query(BehaviorLog)
              .filter(BehaviorLog.user_id == user.id, BehaviorLog.created_at >= since).all())
    by_action = {a: sum(1 for b in recent if b.action == a) for a in ACTION_NAME}
    by_day = {b.created_at.strftime("%m-%d"): 0 for b in recent}
    for b in recent:
        by_day[b.created_at.strftime("%m-%d")] += 1
    daily = [{"date": (now - timedelta(days=i)).strftime("%m-%d"),
              "count": by_day.get((now - timedelta(days=i)).strftime("%m-%d"), 0)}
             for i in range(6, -1, -1)]
    cat_rows = (db.query(Resource.category, func.count(BehaviorLog.id))
                .join(Resource, BehaviorLog.resource_id == Resource.id)
                .filter(BehaviorLog.user_id == user.id, BehaviorLog.created_at >= since)
                .group_by(Resource.category).all())
    cats = {c or "其他": n for c, n in cat_rows}
    top_cat = max(cats.items(), key=lambda kv: kv[1])[0] if cats else ""
    return {"total": len(recent),
            "view": by_action.get("view", 0), "favorite": by_action.get("favorite", 0),
            "rate": by_action.get("rate", 0), "download": by_action.get("download", 0),
            "categories": len(cats), "top_category": top_cat,
            "top_category_count": max(cats.values()) if cats else 0,
            "daily": daily}


@router.get("/history")
def my_history(limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """当前用户的最近行为记录（浏览足迹）。"""
    rows = (db.query(BehaviorLog, Resource.title, Resource.category)
            .join(Resource, BehaviorLog.resource_id == Resource.id)
            .filter(BehaviorLog.user_id == user.id)
            .order_by(BehaviorLog.id.desc())
            .limit(limit).all())
    return {"items": [{
        "id": b.id, "resource_id": b.resource_id, "title": title, "category": cat,
        "action": b.action, "action_name": ACTION_NAME.get(b.action, b.action),
        "value": b.value, "time": b.created_at.strftime("%Y-%m-%d %H:%M"),
    } for b, title, cat in rows], "total": len(rows)}


@router.delete("/history/{log_id}")
def remove_history(log_id: int, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """删除自己的一条行为记录（只能删自己的）。"""
    b = db.get(BehaviorLog, log_id)
    if not b or b.user_id != user.id:
        raise HTTPException(404, "记录不存在")
    db.delete(b)
    db.commit()
    return {"message": "记录已删除"}


@router.get("/favorites")
def my_favorites(page: int = Query(1, ge=1), size: int = Query(6, ge=1, le=100),
                 sort: str = Query("time"),
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """我的收藏列表（分页 + 排序）。sort 可选 time（收藏时间，默认）/ category（分类）/ title（标题）。"""
    q = (db.query(Favorite, Resource)
         .join(Resource, Favorite.resource_id == Resource.id)
         .filter(Favorite.user_id == user.id))
    if sort == "time":
        q = q.order_by(Favorite.id.desc())
    elif sort == "category":
        q = q.order_by(Resource.category.asc(), Favorite.id.desc())
    elif sort == "title":
        q = q.order_by(Resource.title.asc())
    else:
        raise HTTPException(400, "不支持的排序方式，可选：time / category / title")
    total = q.count()
    rows = q.offset((page - 1) * size).limit(size).all()
    return {"items": [{
        "resource_id": r.id, "title": r.title, "category": r.category,
        "type": r.type, "difficulty": r.difficulty,
        "time": f.created_at.strftime("%Y-%m-%d %H:%M"),
    } for f, r in rows], "total": total, "page": page, "size": size}
