"""ORM 数据模型 —— 与论文"表7 核心数据表字段设计"一致"""
from datetime import datetime

from sqlalchemy import (Column, DateTime, Enum, ForeignKey, Integer,
                        String, Text, UniqueConstraint)

from app.db import PK, Base


class User(Base):
    __tablename__ = "user"
    id = Column(PK, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)   # 用户名
    password_hash = Column(String(128), nullable=False)          # 密码哈希
    role = Column(Enum("student", "teacher", "admin", name="role_enum"), default="student")
    nickname = Column(String(50))                                # 昵称
    interests = Column(String(200), default="")                  # 兴趣类别（逗号分隔，冷启动用）
    gender = Column(String(10), default="保密")                   # 性别：男/女/保密
    grade = Column(String(20), default="")                       # 年级
    college = Column(String(50), default="")                     # 学院
    sec_question = Column(String(100), default="")               # 密保问题（忘记密码找回用）
    sec_answer_hash = Column(String(128), default="")            # 密保答案哈希
    status = Column(String(20), default="active")                # 账号状态：active / disabled
    created_at = Column(DateTime, default=datetime.now)


class Resource(Base):
    __tablename__ = "resource"
    id = Column(PK, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)                  # 资源标题
    type = Column(Enum("video", "doc", "ppt", "question", "book", "course", name="res_type_enum"))  # 资源类型
    category = Column(String(50), index=True)                     # 分类/标签
    difficulty = Column(Integer, default=3)                      # 难度等级 1-5
    uploader_id = Column(PK, ForeignKey("user.id"), index=True)   # 上传者
    status = Column(Enum("pending", "online", "offline", name="res_status_enum"),
                    default="online", index=True)                # 上架状态（列表高频过滤）
    click_count = Column(Integer, default=0, index=True)          # 点击数（热度排序）
    description = Column(Text, default="")
    url = Column(String(300), default="")                        # 资源链接（真实课程/文档页）
    file_name = Column(String(200), default="")                  # 上传的原始文件名
    file_size = Column(Integer, default=0)                       # 文件大小（字节）
    file_path = Column(String(300), default="")                  # 服务端存储文件名（重命名后）
    created_at = Column(DateTime, default=datetime.now, index=True)  # 新建时间（时间窗过滤）


class Score(Base):
    __tablename__ = "score"
    id = Column(PK, primary_key=True, autoincrement=True)
    user_id = Column(PK, ForeignKey("user.id"), nullable=False)
    resource_id = Column(PK, ForeignKey("resource.id"), nullable=False, index=True)
    score = Column(Integer, nullable=False)                      # 评分 1-5
    created_at = Column(DateTime, default=datetime.now)
    __table_args__ = (UniqueConstraint("user_id", "resource_id", name="uq_user_resource"),)


class Favorite(Base):
    __tablename__ = "favorite"
    id = Column(PK, primary_key=True, autoincrement=True)
    user_id = Column(PK, ForeignKey("user.id"), nullable=False)
    resource_id = Column(PK, ForeignKey("resource.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.now)
    __table_args__ = (UniqueConstraint("user_id", "resource_id", name="uq_fav_user_resource"),)


class BehaviorLog(Base):
    __tablename__ = "behavior_log"
    id = Column(PK, primary_key=True, autoincrement=True)
    user_id = Column(PK, ForeignKey("user.id"), nullable=False, index=True)
    resource_id = Column(PK, ForeignKey("resource.id"), nullable=False, index=True)
    action = Column(Enum("view", "favorite", "rate", "download", name="action_enum"), nullable=False)
    value = Column(Integer, default=0)                           # 行为强度（评分1-5）
    created_at = Column(DateTime, default=datetime.now)


class Notification(Base):
    __tablename__ = "notification"
    id = Column(PK, primary_key=True, autoincrement=True)
    user_id = Column(PK, ForeignKey("user.id"), nullable=False, index=True)  # 接收者
    title = Column(String(100), nullable=False)
    content = Column(Text, default="")
    ntype = Column(String(20), default="system")                 # welcome / review / system
    is_read = Column(Integer, default=0)                         # 0 未读 / 1 已读
    created_at = Column(DateTime, default=datetime.now)


class TeacherInvite(Base):
    """教师注册邀请码：管理员生成 → 教师注册时填入 → 一次性消费。"""
    __tablename__ = "teacher_invite"
    id = Column(PK, primary_key=True, autoincrement=True)
    code = Column(String(16), nullable=False, unique=True, index=True)
    created_by = Column(PK, ForeignKey("user.id"), nullable=False)   # 生成者（管理员）
    created_at = Column(DateTime, default=datetime.now)
    used_by = Column(PK, ForeignKey("user.id"))                      # 使用者（注册成功的教师）
    used_at = Column(DateTime)
