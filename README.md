# 个性化学习资源推荐系统（原型）

一个面向高校学习场景的个性化学习资源推荐系统。系统采集学生浏览、收藏、评分、下载等行为，
基于协同过滤（User-based / Item-based CF）与 SVD 隐语义模型生成 Top-N 资源推荐，
并用三级冷启动策略（兴趣标签伪评分 → 行为积累过渡 → 协同过滤，热门资源兜底）解决新用户无历史行为的问题。

## 核心功能

- **个性化推荐**：User-CF / Item-CF / SVD 三种算法可切换，输出预测评分与自然语言推荐理由（如"17 位与你口味最相似的同学都看过该资源"），支持三算法结果并排对比与重合度分析
- **冷启动**：新用户凭注册时选择的兴趣标签即可获得个性化首屏，行为不足时自动回退热门资源兜底
- **资源检索与详情**：关键词 + 分类 / 类型 / 难度多维筛选，详情页含评分、收藏、附件下载与"看了又看"相似推荐
- **个人中心**：浏览足迹、收藏夹、学习周报（近 7 天行为趋势）与用户画像雷达图
- **教师端**：上传资源（支持附件拖拽上传）与维护，已上架资源修改后自动回到待审核状态
- **管理后台**：数据看板、资源审核与上下架、用户管理、教师邀请码发放、CSV 数据导出
- **推荐模型自动更新**：行为变化后置脏标记，冷却期结束由首个请求触发增量重训练，无需人工干预

## 技术栈

- 后端：Python 3.10+ / FastAPI / SQLAlchemy（默认 SQLite，可切换 MySQL）
- 推荐算法：numpy + scikit-learn（余弦相似度协同过滤、TruncatedSVD 矩阵分解）
- 前端：Vue 3 + Element Plus + ECharts（本地 vendored，免 npm 构建）
- 部署：uvicorn 单进程启动，前端静态文件由后端同源托管，无需额外 Web 服务器

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
│   ├── seed_data.py         # 模拟数据集生成（约 120 用户 × 200 资源 + 评分 / 行为日志）
│   ├── app/
│   │   ├── config.py        # 全局配置（数据库 URL、密钥、路径）
│   │   ├── db.py            # SQLAlchemy 引擎 / 会话 / 建表
│   │   ├── models.py        # ORM 模型（user/resource/score/favorite/behavior_log）
│   │   ├── security.py      # 密码哈希、HMAC 登录令牌
│   │   ├── schemas.py       # Pydantic 请求模型（入参校验）
│   │   ├── services.py      # 业务服务（交互汇总、引擎训练）
│   │   ├── recommender.py   # 推荐引擎（User-CF / Item-CF / SVD + 冷启动 + 缓存）
│   │   └── routers/         # 路由层：auth / user / resources / behavior / recommend / teacher / admin
│   └── data/app.db          # SQLite 数据库（自动生成）
├── frontend/
│   ├── index.html           # 页面外壳与库加载器
│   ├── css/style.css        # 全局样式（登录页 / 主界面）
│   ├── js/
│   │   ├── api.js           # 后端接口调用封装
│   │   ├── store.js         # 全局状态与业务动作（单一数据源）
│   │   ├── app.js           # 根组件装配与路由参数
│   │   └── components/      # 视图组件（11 个）：登录 / 推荐 / 检索 / 详情 /
│   │                        #   个人中心 / 教师工作台 / 管理后台等
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
│   ├── capture_screens.py   #   批量生成界面截图（输出到 screenshots/）
│   └── archive/             #   开发过程中的一次性调试脚本（留档）
└── requirements.txt
```

## 主要接口（完整清单见 `/docs`）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/auth/register | 用户注册（教师身份需管理员发放的邀请码） |
| POST | /api/auth/login | 登录，返回 HMAC 签名令牌（默认 2 小时，勾选"记住我"为 7 天） |
| GET | /api/resources | 资源列表 / 检索：关键词、分类、类型、难度、排序、分页 |
| GET | /api/resources/{id} | 资源详情（平均分、收藏状态、附件信息） |
| GET | /api/resources/{id}/download | 下载资源附件 |
| GET | /api/resources/{id}/similar | "看了又看"相似资源（Item-CF） |
| POST | /api/behavior | 行为上报（浏览 / 收藏 / 评分 / 下载） |
| POST/DELETE | /api/favorites/{resource_id} | 收藏 / 取消收藏 |
| GET | /api/recommend/{user_id} | 个性化推荐 Top-N（algo=user_cf / item_cf / svd） |
| GET | /api/recommend/hot | 热门资源（冷启动兜底） |
| GET | /api/recommend/compare | 三种算法的推荐结果并排对比与重合度 |
| GET | /api/user/weekly | 学习周报（近 7 天行为趋势与构成） |
| GET | /api/user/portrait | 用户画像（行为分布与兴趣覆盖） |
| POST | /api/teacher/resources | 教师上传资源（进入待审核） |
| POST | /api/teacher/resources/upload | 上传资源附件文件 |
| GET | /api/admin/stats/dashboard | 管理看板统计 |
| PUT | /api/admin/resources/{id}/status | 资源审核 / 上下架 |
| POST | /api/admin/retrain | 手动触发推荐模型重训练 |

## 切换 MySQL（可选）

```bash
set DATABASE_URL=mysql+pymysql://root:password@localhost:3306/learn_rec?charset=utf8mb4
```
