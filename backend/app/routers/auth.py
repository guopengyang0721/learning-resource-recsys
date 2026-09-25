"""用户认证路由 —— 注册 / 登录 / 登录态校验"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import REMEMBER_TTL, SESSION_TTL
from app.db import get_db
from app.models import Notification, TeacherInvite, User
from app.ratelimit import (LOCK_SECONDS, client_rate_limited, record_failure,
                           record_success, remaining_lock_seconds)
from app.schemas import (ForgotPwdIn, LoginIn, RegisterIn, SecQuestionIn,
                         SetSecIn)
from app.security import (get_current_user, hash_pwd, make_token, needs_rehash,
                          verify_pwd, verify_token)

router = APIRouter(prefix="/api/auth", tags=["用户管理"])

# 注册接口限流：防脚本批量注册灌数据、防对邀请码做暴力尝试
REGISTER_LIMIT, REGISTER_WINDOW = 10, 60.0     # 每 IP 每分钟最多 10 次注册请求
LOCK_MINUTES = max(LOCK_SECONDS // 60, 1)      # 锁定分钟数（供提示文案使用，随配置自动同步）


@router.post("/register")
def register(data: RegisterIn, request: Request, db: Session = Depends(get_db)):
    from sqlalchemy.exc import IntegrityError
    client = request.client.host if request.client else "unknown"
    if client_rate_limited(f"register:{client}", REGISTER_LIMIT, REGISTER_WINDOW):
        raise HTTPException(429, "注册请求过于频繁，请稍后再试")
    if db.query(User).filter(User.username == data.username).count() > 0:
        raise HTTPException(409, "用户名已存在")
    # 角色：学生自助注册；教师需一次性邀请码（管理员生成）；admin 永远不可注册
    role = "teacher" if data.role == "teacher" else "student"
    invite = None
    if role == "teacher":
        code = (data.invite_code or "").strip().upper()
        if not code:
            raise HTTPException(400, "教师注册需要填写邀请码，请向管理员获取")
        invite = db.query(TeacherInvite).filter(TeacherInvite.code == code).first()
        if not invite:
            raise HTTPException(400, "邀请码无效，请核对后重试")
        if invite.used_by:
            raise HTTPException(400, "该邀请码已被使用，请联系管理员重新发放")
    interests = ",".join(dict.fromkeys(data.interests))[:200]   # 去重并截断
    u = User(username=data.username, password_hash=hash_pwd(data.password),
             role=role,
             nickname=data.nickname or data.username, interests=interests,
             gender=data.gender if data.gender in ("男", "女", "保密") else "保密",
             grade=data.grade[:20], college=data.college[:50],
             # 密保问题与答案必须成对存储：只存问题不存答案会让"找回"永远失败
             sec_question=data.sec_question.strip()[:100] if data.sec_answer.strip() else "",
             sec_answer_hash=hash_pwd(data.sec_answer.strip().lower()) if data.sec_answer.strip() else "")
    db.add(u)
    try:
        db.flush()                  # 取到 u.id；并发同名注册时在此撞唯一约束
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "用户名已存在，请换一个用户名")
    if invite:                      # 原子消费邀请码：仅当仍未使用时更新，并发下只有一个成功
        rc = (db.query(TeacherInvite)
              .filter(TeacherInvite.id == invite.id, TeacherInvite.used_by.is_(None))
              .update({"used_by": u.id, "used_at": datetime.now()}, synchronize_session=False))
        if rc != 1:
            db.rollback()
            raise HTTPException(400, "该邀请码已被使用，请联系管理员重新发放")
    db.add(Notification(user_id=u.id, title="欢迎使用个性化学习资源推荐系统",
                        content="完善兴趣标签可获得更精准的冷启动推荐；浏览、收藏、评分都会让推荐越来越懂你。",
                        ntype="welcome"))
    db.commit()                     # 用户与欢迎通知同一事务，避免半成功
    return {"user_id": u.id, "username": u.username, "role": u.role, "nickname": u.nickname,
            "gender": u.gender, "grade": u.grade, "college": u.college,
            "has_sec_question": bool(u.sec_question),
            "interests": data.interests, "token": make_token(u.id, u.role)}


@router.post("/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    # 防暴力破解：连续失败 MAX_ATTEMPTS 次锁定 LOCK_MINUTES 分钟
    lock_left = remaining_lock_seconds(data.username)
    if lock_left:
        raise HTTPException(429, f"密码错误次数过多，账号已锁定，请约 {max(lock_left // 60, 1)} 分钟后再试")
    u = db.query(User).filter(User.username == data.username).first()
    # 加盐哈希无法用等值查询比对，先取用户再校验（兼容历史无盐 SHA-256）
    if not u or not verify_pwd(data.password, u.password_hash):
        locked = record_failure(data.username)
        msg = "用户名或密码错误"
        if locked:
            msg += f"，错误次数过多已锁定 {LOCK_MINUTES} 分钟"
        raise HTTPException(400, msg)
    if u.status == "disabled":
        raise HTTPException(403, "账号已被禁用，请联系管理员")
    if needs_rehash(u.password_hash):      # 旧格式哈希在成功登录时顺手升级
        u.password_hash = hash_pwd(data.password)
        db.commit()
    record_success(data.username)
    remember = bool(getattr(data, "remember", False))
    ttl = REMEMBER_TTL if remember else SESSION_TTL
    return {"user_id": u.id, "username": u.username, "role": u.role, "status": u.status,
            "nickname": u.nickname, "gender": u.gender or "保密", "grade": u.grade or "",
            "college": u.college or "", "has_sec_question": bool(u.sec_question),
            "interests": (u.interests or "").split(",") if u.interests else [],
            "remember": remember, "expires_in": ttl,
            "token": make_token(u.id, u.role, ttl=ttl, remember=remember)}


@router.get("/verify")
def verify(user: User = Depends(get_current_user)):
    """前端启动时校验本地登录态是否有效。"""
    return {"user_id": user.id, "username": user.username, "role": user.role, "status": user.status,
            "nickname": user.nickname, "gender": user.gender or "保密", "grade": user.grade or "",
            "college": user.college or "", "has_sec_question": bool(user.sec_question),
            "interests": (user.interests or "").split(",") if user.interests else []}


@router.post("/sec-question")
def get_sec_question(data: SecQuestionIn, db: Session = Depends(get_db)):
    """忘记密码第一步：按用户名获取密保问题（只返回问题，不泄露答案）。"""
    u = db.query(User).filter(User.username == data.username).first()
    if not u or not u.sec_question:
        # 不区分"用户不存在"与"未设置密保"，避免用户名枚举
        raise HTTPException(404, "该用户名不存在或未设置密保问题")
    return {"username": u.username, "question": u.sec_question}


@router.post("/forgot-password")
def forgot_password(data: ForgotPwdIn, db: Session = Depends(get_db)):
    """忘记密码第二步：校验密保答案，通过后重置密码（同样防暴力猜测）。"""
    lock_key = "fp:" + data.username
    lock_left = remaining_lock_seconds(lock_key)
    if lock_left:
        raise HTTPException(429, f"密保答案错误次数过多，请约 {max(lock_left // 60, 1)} 分钟后再试")
    u = db.query(User).filter(User.username == data.username).first()
    if not u or not u.sec_question or not verify_pwd(data.answer.strip().lower(), u.sec_answer_hash):
        locked = record_failure(lock_key)
        msg = "密保答案错误"
        if locked:
            msg += f"，错误次数过多已锁定 {LOCK_MINUTES} 分钟"
        raise HTTPException(400, msg)
    u.password_hash = hash_pwd(data.new_password)
    db.commit()
    record_success(lock_key)
    return {"message": "密码已重置，请使用新密码登录"}
