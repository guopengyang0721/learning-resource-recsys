# 个性化学习资源推荐系统 —— 本地运行说明

## 目录结构

```
webmining_project/
├── backend/            后端（FastAPI + SQLAlchemy + 协同过滤引擎）
│   ├── main.py         ★ 启动入口（运行这个文件）
│   ├── app/            业务代码（routers/ 路由、recommender.py 推荐引擎等）
│   ├── data/app.db     SQLite 数据库（首次启动自动建表 + 灌种子数据）
│   ├── seed_data.py    种子数据脚本（由启动流程自动调用）
│   └── uploads/        教师上传的附件
├── frontend/           前端（Vue3 + Element Plus，无需构建，后端直接托管）
├── tools/              离线评估、测试与巡检脚本（非系统本体）
└── requirements.txt    依赖清单
```

## 运行步骤（PyCharm）

1. **打开项目**：File → Open → 选择 `webmining_project` 目录
2. **配置解释器**：Settings → Project → Python Interpreter → 新建 venv（Python 3.10+）
3. **装依赖**：终端执行
   ```
   pip install -r requirements.txt
   ```
4. **启动**：运行 `backend/main.py`
5. **访问**：浏览器打开 http://127.0.0.1:8000

## 演示账号

| 角色 | 用户名 | 密码 |
|---|---|---|
| 管理员 | admin | admin123 |
| 教师 | teacher01 | 123456 |
| 学生 | student001 | 123456 |

（更多种子账号：student002~100、teacher02~05，密码均为 123456）

## 说明

- 首次启动会自动建表并生成约 120 个用户、204 条真实资源、8 千余条行为数据，稍等几秒即可。
- 数据库就是普通文件 `backend/data/app.db`，删掉它重启即恢复全新种子状态。
- 修改后端代码需重启 `main.py`；前端 JS/CSS 刷新浏览器即可（已禁用缓存）。
- 端口占用报错时：`netstat -ano | findstr :8000` 找到 PID，`taskkill /F /PID <pid>` 释放。
- 行为日志只增不减：当前量级（数千条）完全无碍；若长期运行至数十万条，可在数据库中
  执行 `DELETE FROM behavior_log WHERE created_at < '起始日期'` 归档旧数据（保留近 180 天即可，
  推荐矩阵用的是评分与汇总行为）。
