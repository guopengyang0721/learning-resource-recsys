"""全局配置 —— 数据库连接、密钥、路径"""
import logging
import os

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # backend/
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")
EVAL_METRICS_PATH = os.path.join(BASE_DIR, "..", "evaluation", "metrics.json")

# 运行时数据目录（数据库与上传附件）。仓库不包含该目录，首次运行在此自动创建——
# 否则 SQLite 会因父目录不存在而报 "unable to open database file"。
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# 如需切换 MySQL：设置环境变量 DATABASE_URL，例如
# mysql+pymysql://root:password@localhost:3306/learn_rec?charset=utf8mb4
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///" + os.path.join(DATA_DIR, "app.db"))

# 令牌签名密钥：优先读环境变量 SECRET_KEY；未配置时回退到内置默认值仅供本地运行
SECRET_KEY = os.environ.get("SECRET_KEY", "nwu-webmining-2026")
if not os.environ.get("SECRET_KEY"):
    logger.warning("未设置环境变量 SECRET_KEY，正在使用内置默认密钥（仅供本地运行；部署前请务必配置）")
SESSION_TTL = 2 * 3600                  # 会话级令牌有效期：2 小时（不勾"记住我"）
REMEMBER_TTL = 7 * 24 * 3600            # 记住我令牌有效期：7 天

# 管理员重置用户密码时使用的默认密码（管理后台「重置密码」弹窗会预填该值，可直接确认）
# 注：重置后的账号使用同一初始密码，适用于本地/教学环境；正式部署建议改为逐个设定
DEFAULT_RESET_PASSWORD = os.environ.get("DEFAULT_RESET_PASSWORD", "123456")

# 资源文件上传（教师拖拽上传）
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")             # 存储目录（与库同盘，便于整体打包/迁移）
os.makedirs(UPLOAD_DIR, exist_ok=True)                     # 首次运行自动创建
MAX_UPLOAD_MB = 50                                          # 单文件上限（MB）
ALLOWED_UPLOAD_EXT = {                                      # 允许的文件类型白名单
    ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
    ".txt", ".md", ".csv", ".zip", ".rar", ".7z",
    ".mp4", ".mp3", ".wav", ".png", ".jpg", ".jpeg", ".gif",
}
