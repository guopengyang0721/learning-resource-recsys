"""个性化学习资源推荐系统 —— 启动入口

接口设计与论文"表8 主要 RESTful 接口设计"一致，业务代码位于 app/ 包：
    app/config.py      全局配置（数据库、密钥、路径）
    app/db.py          SQLAlchemy 连接与会话
    app/models.py      ORM 数据模型（5 张核心表）
    app/security.py    密码哈希与登录令牌
    app/schemas.py     Pydantic 请求模型
    app/services.py    业务服务（交互汇总、引擎训练）
    app/recommender.py 推荐引擎（User-CF / Item-CF / SVD + 冷启动）
    app/routers/       路由层（auth / resources / behavior / recommend / admin）

启动：python main.py  （或 uvicorn main:app --reload --port 8000）
"""
import os

import uvicorn

from app import create_app

app = create_app()

if __name__ == "__main__":
    # 部署到 Render / Railway 等平台时，必须监听 0.0.0.0 并读取平台下发的 PORT
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
