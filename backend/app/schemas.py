"""Pydantic 请求模型 —— 接口入参校验"""
from typing import List

from pydantic import BaseModel, Field


class RegisterIn(BaseModel):
    username: str = Field(min_length=2, max_length=50)   # 允许中文名（如"张三"）
    password: str = Field(min_length=6, max_length=64)
    role: str = "student"
    nickname: str = ""
    interests: List[str] = []          # 兴趣类别（冷启动用）
    gender: str = "保密"
    grade: str = ""
    college: str = ""
    sec_question: str = ""             # 密保问题（忘记密码找回用）
    sec_answer: str = ""
    invite_code: str = ""              # 教师注册需填管理员发放的邀请码


class InterestsIn(BaseModel):
    interests: List[str] = Field(max_length=10)


class ProfileIn(BaseModel):
    """个人资料（密码修改走独立的 /change-password 接口）。"""
    nickname: str = Field(min_length=1, max_length=50)
    gender: str = "保密"
    grade: str = ""
    college: str = ""


class StatusIn(BaseModel):
    status: str                  # user: active/disabled；resource: pending/online/offline


class UpgradeTeacherIn(BaseModel):
    """学生凭邀请码升级为教师（保留全部历史数据）。"""
    invite_code: str = Field(min_length=4, max_length=16)


class ChangePwdIn(BaseModel):
    """修改密码（独立接口，与资料编辑解耦）。"""
    old_password: str = Field(min_length=1, max_length=64)
    new_password: str = Field(min_length=6, max_length=64)


class ResetPwdIn(BaseModel):
    # 留空表示"重置为系统默认密码"（见 config.DEFAULT_RESET_PASSWORD）
    new_password: str = Field("", max_length=64)


class BroadcastIn(BaseModel):
    title: str = Field(min_length=2, max_length=100)
    content: str = Field(min_length=1, max_length=500)


class ForgotPwdIn(BaseModel):
    username: str
    answer: str
    new_password: str = Field(min_length=6, max_length=64)


class SecQuestionIn(BaseModel):
    username: str


class SetSecIn(BaseModel):
    question: str = Field(min_length=4, max_length=100)
    answer: str = Field(min_length=1, max_length=64)
    password: str                     # 当前密码校验


class LoginIn(BaseModel):
    username: str
    password: str
    remember: bool = False     # 记住我 7 天；否则会话级 2 小时


class ResourceIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    type: str = Field("doc", pattern=r"^(video|doc|ppt|question|book|course)$")
    category: str = "其他"
    difficulty: int = Field(3, ge=1, le=5)
    description: str = ""
    url: str = Field("", max_length=300, pattern=r"^(https?://\S*)?$")  # 空串或 http(s) 链接
    # 附件信息：由上传接口返回，提交资源时原样带回（file_path 限服务端生成的「十六进制名.扩展名」）
    file_name: str = Field("", max_length=200)
    file_size: int = Field(0, ge=0)
    file_path: str = Field("", max_length=300, pattern=r"^([0-9a-f]{32}\.[A-Za-z0-9]{1,10})?$")


class BehaviorIn(BaseModel):
    user_id: int = 0          # 兼容前端字段；服务端一律以令牌身份为准，忽略此值
    resource_id: int
    action: str               # view / favorite / rate / download
    value: int = Field(0, ge=0, le=5)   # 行为强度（评分 1-5），越界拒绝
