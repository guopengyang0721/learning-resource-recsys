# 个性化学习资源推荐系统（原型）

Web 数据挖掘课程学年论文配套原型系统：基于协同过滤（User-based / Item-based CF）与 SVD 隐语义模型的个性化学习资源 Top-N 推荐，三级冷启动策略（兴趣标签伪评分 → 行为积累过渡 → 协同过滤；热门资源兜底）、行为采集、资源详情与相似推荐（"看了又看"）、个人中心（浏览足迹/收藏）、JWT 接口鉴权与管理后台。

## 技术栈

- 后端：Python 3.10+ / FastAPI / SQLAlchemy（默认 SQLite，可切换 MySQL）
- 推荐算法：numpy + scikit-learn（余弦相似度协同过滤、TruncatedSVD 矩阵分解）
- 前端：Vue 3 + Element Plus + ECharts（本地 vendored，免 npm 构建）
- 开发/部署：Git / Docker 可选

## 快速启动

```bash
# 1. 安装依赖（建议虚拟环境）
pip install -r requirements.txt

# 2. 启动系统（首次启动自动建库、生成演示数据并训练模型）
cd backend
python main.py

# 3. 浏览器访问
#    前端页面   http://127.0.0.1:8000/
#    接口文档   http://127.0.0.1:8000/docs   （Swagger 自动生成）
```

## 演示账号

| 角色 | 账号 | 密码 |
|---|---|---|
| 学生（个性化推荐） | student001 ~ student100 | 123456 |
| 教师 | teacher01 ~ teacher05 | 123456 |
| 管理员 | admin | admin123 |

> 登录页不提供快捷登录入口，请用上述账号在登录表单中正常登录。首次使用建议以 `student001` 体验个性化推荐，以 `teacher01` 体验资源上传与审核流程，以 `admin` 查看数据看板与用户管理。

## 离线评估实验

```bash
# 在项目根目录执行，评估 User-CF / Item-CF / SVD
python evaluate.py
```

输出 `evaluation/` 目录：`metrics.json`（指标）、`eval_metrics.png`（Precision/Recall/Coverage 对比图）、`rmse_curve.png`（RMSE 对比图）。

## 自动化测试

```bash
# API 全量回归（91 项：鉴权边界、角色越权、审核流、并发与安全用例）
python tools/test_full_sweep.py

# 无头浏览器 UI 巡检（三种角色遍历全部页签，校验渲染与 JS 错误；自动拉起浏览器）
python tools/test_ui_sweep.py
```

两个脚本默认针对本机 `http://127.0.0.1:8000`。UI 巡检脚本通过 `?autologin=1&user=student|teacher|admin` 参数免去重复填表——该参数**仅在 127.0.0.1 / localhost 访问时生效**，部署到其他主机后自动失效。浏览器 profile 存放在系统临时目录（`tools/start_browser.py` 负责启动），不会写入项目。

## 部署注意事项

| 项 | 说明 |
|---|---|
| SECRET_KEY | 未配置环境变量时使用内置默认值（仅供本地运行），实际部署必须设置 `SECRET_KEY` |
| CORS | 当前仅放行本机两个来源；前后端分开部署时按需追加域名 |
| 数据库 | 默认 SQLite（`backend/data/app.db`）；数据量增长后可切 PostgreSQL（修改 `DATABASE_URL`） |
| 测试入口 | `?autologin` 参数与 `tools/` 下的巡检脚本为本地开发测试用途，正式部署可移除 |
| 演示账号 | 种子账号密码为公开演示用途，部署后应立即修改管理员密码 |

## 目录结构

```
├── backend/
│   ├── main.py              # 启动入口（薄壳，业务在 app/ 包）
│   ├── seed_data.py         # 模拟数据集生成（100 用户 × 200 资源）
│   ├── app/
│   │   ├── config.py        # 全局配置（数据库 URL、密钥、路径）
│   │   ├── db.py            # SQLAlchemy 引擎 / 会话 / 建表
│   │   ├── models.py        # ORM 模型（user/resource/score/favorite/behavior_log）
│   │   ├── security.py      # 密码哈希、HMAC 登录令牌
│   │   ├── schemas.py       # Pydantic 请求模型（入参校验）
│   │   ├── services.py      # 业务服务（交互汇总、引擎训练）
│   │   ├── recommender.py   # 推荐引擎（User-CF / Item-CF / SVD + 冷启动 + 缓存）
│   │   └── routers/         # 路由层：auth / resources / behavior / recommend / admin
│   └── data/app.db          # SQLite 数据库（自动生成）
├── frontend/
│   ├── index.html           # 页面外壳与库加载器
│   ├── css/style.css        # 全局样式（登录页 / 主界面）
│   ├── js/
│   │   ├── api.js           # 后端接口调用封装
│   │   ├── store.js         # 全局状态与业务动作（单一数据源）
│   │   ├── app.js           # 根组件装配与路由参数
│   │   └── components/      # 视图组件：LoginView / HeaderBar /
│   │                        #   RecommendView / ResourcesView / StatsView
│   ├── assets/bg.png        # 登录页背景插画
│   └── vendor/              # Vue3、Element Plus、ECharts 本地化文件
├── evaluation/              # 离线评估结果（运行 evaluate.py 后生成）
├── evaluate.py              # 离线评估实验脚本
├── tools/                   # 开发测试与数据维护脚本
│   ├── test_full_sweep.py   #   API 全量回归（91 项）
│   ├── test_ui_sweep.py     #   无头浏览器 UI 巡检
│   ├── start_browser.py     #   启动无头浏览器（CDP）
│   ├── test_bruteforce.py   #   登录防爆破验证
│   ├── test_security_fixes.py / test_token_expiry.py   # 安全用例
│   ├── real_resources.py / import_real_resources.py / refine_links.py  # 真实资源数据
│   ├── check_all_links.py   #   资源链接可达性巡检
│   └── archive/             #   开发过程中的一次性调试脚本（留档）
└── requirements.txt
```

## 主要接口（详见 /docs）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/auth/register | 用户注册 |
| POST | /api/auth/login | 登录，返回 JWT |
| GET | /api/resources | 资源列表 / 检索 |
| GET | /api/resources/{id} | 资源详情 |
| POST | /api/resources | 资源上传（教师） |
| POST | /api/behavior | 行为上报（浏览/收藏/评分/下载） |
| POST | /api/favorites/{resource_id} | 收藏 |
| GET | /api/recommend/{user_id} | 个性化推荐 Top-N（支持 algo=user_cf/item_cf/svd） |
| GET | /api/recommend/hot | 热门资源（冷启动兜底） |
| GET | /api/admin/stats/recommend | 推荐效果统计 |

## 切换 MySQL（可选）

```bash
set DATABASE_URL=mysql+pymysql://root:password@localhost:3306/learn_rec?charset=utf8mb4
```
