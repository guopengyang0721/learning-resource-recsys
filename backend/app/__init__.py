"""应用工厂 —— 创建 FastAPI 实例、装配路由与静态资源"""
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import FRONTEND_DIR, UPLOAD_DIR
from app.db import SessionLocal, init_db
from app.routers import admin, auth, behavior, recommend, resources, teacher, user
from app.services import train_engine

logger = logging.getLogger(__name__)


def _cleanup_orphan_uploads(max_age_hours: float = 24.0):
    """清理孤儿上传文件：磁盘上存在、但没有任何资源引用、且超过 max_age_hours 的文件。

    教师「先传文件再提交资源」的流程中，中途放弃会留下无引用文件，这里在启动时兜底回收。
    """
    if not os.path.isdir(UPLOAD_DIR):
        return
    referenced = set()
    db = SessionLocal()
    try:
        from app.models import Resource
        referenced = {r.file_path for r in db.query(Resource.file_path).all() if r.file_path}
    finally:
        db.close()
    cutoff = time.time() - max_age_hours * 3600
    removed = 0
    for fn in os.listdir(UPLOAD_DIR):
        p = os.path.join(UPLOAD_DIR, fn)
        if fn in referenced or not os.path.isfile(p):
            continue
        if os.path.getmtime(p) < cutoff:
            try:
                os.remove(p)
                removed += 1
            except OSError:
                pass
    if removed:
        logger.info("清理孤儿上传文件 %d 个", removed)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- 启动：建表 + 种子数据 + 引擎训练 + 孤儿文件清理 ----
    init_db()
    from seed_data import run as seed_run
    seed_run()
    db = SessionLocal()
    try:
        n = train_engine(db)
        logger.info("推荐引擎训练完成，交互记录 %d 条", n)
    finally:
        db.close()
    _cleanup_orphan_uploads()
    yield
    # ---- 关闭：暂无需要释放的资源 ----


def create_app() -> FastAPI:
    app = FastAPI(
        title="个性化学习资源推荐系统 API", version="2.0.0",
        description="基于协同过滤（User-CF / Item-CF）与 SVD 隐语义模型的个性化学习资源推荐系统，"
                    "提供资源检索、行为采集、个性化推荐、教师上传与审核、管理后台等接口。",
        lifespan=lifespan,
    )
    # 前端与 API 同源部署（StaticFiles 挂载），浏览器不触发跨域；
    # CORS 中间件仅为"前后端分开部署"的开发场景保留，且只放行本机来源
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(CORSMiddleware,
                       allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
                       allow_methods=["*"], allow_headers=["*"],
                       expose_headers=["X-Renewed-Token"])

    # 滑动过期：鉴权依赖续签的新令牌通过响应头下发给前端
    @app.middleware("http")
    async def renew_token_header(request, call_next):
        response = await call_next(request)
        token = getattr(request.state, "renewed_token", None)
        if token:
            response.headers["X-Renewed-Token"] = token
        # 静态资源强制 revalidate（ETag 未变则 304，开销极小）：
        # 否则启发式缓存会让浏览器在改版后仍使用旧 JS，出现"改了代码界面没变"的假 bug
        if not request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    app.include_router(auth.router)
    app.include_router(resources.router)
    app.include_router(behavior.router)
    app.include_router(recommend.router)
    app.include_router(user.router)
    app.include_router(teacher.router)
    app.include_router(admin.router)

    # 健康检查（运维探针）
    from datetime import datetime
    from app.services import get_engine

    @app.get("/api/health")
    def health():
        eng = get_engine()
        return {"status": "ok",
                "engine_trained_at": datetime.fromtimestamp(eng.trained_at).strftime("%Y-%m-%d %H:%M:%S")
                                     if eng.trained_at else None}

    if os.path.isdir(FRONTEND_DIR):
        app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

        # 前端 History 路由回退：/login 等非 API 的 GET 404 一律返回 index.html
        from fastapi.responses import FileResponse
        index_html = os.path.join(FRONTEND_DIR, "index.html")

        @app.exception_handler(404)
        async def spa_fallback(request, exc):
            if request.method == "GET" and not request.url.path.startswith("/api"):
                if os.path.exists(index_html):
                    return FileResponse(index_html)
            detail = getattr(exc, "detail", "Not Found")
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": detail}, status_code=404)

    return app
