"""数据库连接与会话管理（SQLAlchemy）"""
import logging
from sqlalchemy import BigInteger, Integer, create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DATABASE_URL

logger = logging.getLogger(__name__)

_IS_SQLITE = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL, echo=False, future=True,
    # SQLite：允许跨线程使用 + 写锁最长等待 15s（避免并发写入直接抛 database is locked）
    connect_args={"check_same_thread": False, "timeout": 15} if _IS_SQLITE else {},
)

if _IS_SQLITE:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _):
        """每个新连接开启外键约束：悬空引用在数据库层报错，而非静默写入脏数据。"""
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base = declarative_base()

# SQLite 要求 INTEGER PRIMARY KEY 才自增；MySQL 下仍为 BIGINT
PK = BigInteger().with_variant(Integer, "sqlite")


def init_db():
    """建表（幂等），并对旧库做轻量列迁移。"""
    from app import models   # noqa: F401  确保 ORM 模型已注册
    Base.metadata.create_all(engine)
    from sqlalchemy import text
    with engine.begin() as conn:
        if _IS_SQLITE:
            # WAL 模式：读不阻塞写、写不阻塞读（持久化设置，执行一次即可）
            try:
                conn.execute(text("PRAGMA journal_mode=WAL"))
            except Exception:
                pass
        # v2~v7 迁移：新增列（"duplicate column name" 属正常幂等跳过；其他异常留痕便于排查）
        v_migrations = (
            "ALTER TABLE user ADD COLUMN interests VARCHAR(200) DEFAULT ''",
            "ALTER TABLE user ADD COLUMN status VARCHAR(20) DEFAULT 'active'",
            "ALTER TABLE user ADD COLUMN gender VARCHAR(10) DEFAULT '保密'",
            "ALTER TABLE user ADD COLUMN grade VARCHAR(20) DEFAULT ''",
            "ALTER TABLE user ADD COLUMN college VARCHAR(50) DEFAULT ''",
            "ALTER TABLE user ADD COLUMN sec_question VARCHAR(100) DEFAULT ''",
            "ALTER TABLE user ADD COLUMN sec_answer_hash VARCHAR(128) DEFAULT ''",
            "ALTER TABLE resource ADD COLUMN url VARCHAR(300) DEFAULT ''",
            "ALTER TABLE resource ADD COLUMN file_name VARCHAR(200) DEFAULT ''",
            "ALTER TABLE resource ADD COLUMN file_size INTEGER DEFAULT 0",
            "ALTER TABLE resource ADD COLUMN file_path VARCHAR(300) DEFAULT ''",
        )
        for ddl in v_migrations:
            try:
                conn.execute(text(ddl))
            except Exception as e:
                if "duplicate column" not in str(e).lower():
                    logger.warning("迁移跳过：%s", e)
        # v8 迁移：为高频过滤/排序字段补索引（CREATE INDEX IF NOT EXISTS 幂等，旧库同样生效）
        for ddl in (
            "CREATE INDEX IF NOT EXISTS ix_behavior_log_user_id ON behavior_log (user_id)",
            "CREATE INDEX IF NOT EXISTS ix_behavior_log_resource_id ON behavior_log (resource_id)",
            "CREATE INDEX IF NOT EXISTS ix_behavior_log_created_at ON behavior_log (created_at)",
            "CREATE INDEX IF NOT EXISTS ix_score_resource_id ON score (resource_id)",
            "CREATE INDEX IF NOT EXISTS ix_favorite_resource_id ON favorite (resource_id)",
            "CREATE INDEX IF NOT EXISTS ix_notification_user_id ON notification (user_id)",
            "CREATE INDEX IF NOT EXISTS ix_resource_status ON resource (status)",
            "CREATE INDEX IF NOT EXISTS ix_resource_category ON resource (category)",
            "CREATE INDEX IF NOT EXISTS ix_resource_click_count ON resource (click_count)",
            "CREATE INDEX IF NOT EXISTS ix_resource_created_at ON resource (created_at)",
            "CREATE INDEX IF NOT EXISTS ix_resource_uploader_id ON resource (uploader_id)",
        ):
            try:
                conn.execute(text(ddl))
            except Exception as e:
                # 幂等迁移失败需留痕（可能掩盖 database is locked / 磁盘满等真实故障）
                logger.warning("迁移跳过：%s", e)


def get_db():
    """FastAPI 依赖：请求级数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
