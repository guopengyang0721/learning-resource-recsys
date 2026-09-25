"""构造演示数据集：模拟用户-资源-行为数据（对应论文"尚缺少的条件及解决方法"）。
生成约 100 用户 × 200 资源、含类别偏好的稀疏评分数据。
"""
import logging
import random
from datetime import datetime, timedelta

from app.db import SessionLocal, init_db
from app.models import BehaviorLog, Favorite, Notification, Resource, Score, TeacherInvite, User
from app.security import hash_pwd

logger = logging.getLogger(__name__)          # 统一使用加盐哈希实现，避免多份不一致

random.seed(42)

CATEGORIES = ["软件工程", "机器学习", "数据库", "计算机网络", "算法", "Web开发", "人工智能"]
TYPES = ["video", "doc", "ppt", "question", "book", "course"]
TYPE_NAME = {"video": "视频", "doc": "文档", "ppt": "课件", "question": "题库",
             "book": "书籍", "course": "系列课"}


def run(drop=False):
    init_db()
    db = SessionLocal()
    try:
        if drop:
            # 外键已启用（PRAGMA foreign_keys=ON）：必须先删子表再删父表
            db.query(BehaviorLog).delete()
            db.query(Favorite).delete()
            db.query(Score).delete()
            db.query(Notification).delete()
            db.query(TeacherInvite).delete()
            db.query(Resource).delete()
            db.query(User).delete()
            db.commit()
        if db.query(User).count() > 0:
            logger.info("数据已存在，跳过种子生成（如需重建请使用 --rebuild）")
            return

        now = datetime.now()
        # ---- 用户 ----
        users = [User(username="admin", password_hash=hash_pwd("admin123"), role="admin", nickname="管理员")]
        for i in range(1, 101):  # 100 名学生
            users.append(User(username=f"student{i:03d}", password_hash=hash_pwd("123456"),
                              role="student", nickname=f"同学{i:03d}"))
        for i in range(1, 6):    # 5 名教师
            users.append(User(username=f"teacher{i:02d}", password_hash=hash_pwd("123456"),
                              role="teacher", nickname=f"教师{i:02d}"))
        db.add_all(users)
        db.commit()

        # ---- 资源 ----
        resources = []
        for i in range(1, 201):
            cat = random.choice(CATEGORIES)
            t = random.choice(TYPES)
            pop = random.paretovariate(1.2)  # 少数热门、多数普通
            resources.append(Resource(
                title=f"{cat}-{TYPE_NAME[t]}{i:03d}-{random.choice(['基础', '进阶', '实战', '精讲', '案例'])}",
                type=t, category=cat,
                difficulty=random.randint(1, 5),
                uploader_id=random.choice([u.id for u in users if u.role == "teacher"]),
                status="online",
                click_count=int(pop * 30),
                description=f"《{cat}》方向的{TYPE_NAME[t]}类学习资源，难度等级 {random.randint(1, 5)}。",
                created_at=now - timedelta(days=random.randint(1, 365)),
            ))
        db.add_all(resources)
        db.commit()

        # ---- 行为与评分（每位用户有 1-2 个偏好类别 + 热门度加成）----
        res_ids = [r.id for r in resources]
        cat_of = {r.id: r.category for r in resources}
        pop_of = {r.id: r.click_count for r in resources}

        scores, favs, logs = [], [], []
        for u in users:
            if u.role != "student":
                continue
            prefs = random.sample(CATEGORIES, random.randint(1, 2))
            n_rate = random.randint(25, 60)
            for rid in random.sample(res_ids, n_rate):
                base = 3.0
                if cat_of[rid] in prefs:
                    base += random.uniform(0.6, 1.8)     # 偏好类别评分更高
                base += min(pop_of[rid], 200) / 400.0    # 热门加成
                s = max(1, min(5, round(base + random.gauss(0, 0.4))))
                scores.append(Score(user_id=u.id, resource_id=rid, score=s,
                                    created_at=now - timedelta(days=random.randint(0, 180))))
                logs.append(BehaviorLog(user_id=u.id, resource_id=rid, action="rate",
                                        value=s, created_at=now - timedelta(days=random.randint(0, 180))))
                if random.random() < 0.35:               # 部分收藏
                    favs.append(Favorite(user_id=u.id, resource_id=rid,
                                         created_at=now - timedelta(days=random.randint(0, 180))))
                    logs.append(BehaviorLog(user_id=u.id, resource_id=rid, action="favorite",
                                            value=4, created_at=now - timedelta(days=random.randint(0, 180))))
                if random.random() < 0.6:                # 浏览记录
                    logs.append(BehaviorLog(user_id=u.id, resource_id=rid, action="view",
                                            value=1, created_at=now - timedelta(days=random.randint(0, 180))))
        db.add_all(scores)
        db.add_all(favs)
        db.commit()
        # 日志量大，分批写入
        for i in range(0, len(logs), 2000):
            db.add_all(logs[i:i + 2000])
            db.commit()
        logger.info("种子数据完成：用户 %d，资源 %d，评分 %d，收藏 %d，日志 %d",
                    db.query(User).count(), db.query(Resource).count(), db.query(Score).count(),
                    db.query(Favorite).count(), db.query(BehaviorLog).count())
    finally:
        db.close()


if __name__ == "__main__":
    import sys
    run(drop="--rebuild" in sys.argv)
