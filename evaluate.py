"""离线评估实验 —— 三种推荐算法对比（对应论文"实验设计与结果分析"）
算法：User-based CF / Item-based CF / SVD
指标：Precision@10、Recall@10、Coverage@10、RMSE
方法：按用户留出法（每个用户 80% 训练 / 20% 测试，仅保留评分数 >=5 的用户）
输出：evaluation/metrics.json、evaluation/eval_metrics.png、evaluation/rmse_curve.png
"""
import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))
from app.db import SessionLocal                    # noqa: E402
from app.models import Resource, Score             # noqa: E402
from app.recommender import RecommendationEngine   # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "evaluation")
os.makedirs(OUT_DIR, exist_ok=True)

N = 10
MIN_RATINGS = 5
SEED = 42


def load_matrix():
    """从数据库加载评分，并按用户划分训练/测试集。"""
    db = SessionLocal()
    try:
        scores = [(s.user_id, s.resource_id, s.score) for s in db.query(Score).all()]
        meta = {r.id: {"title": r.title, "category": r.category, "type": r.type}
                for r in db.query(Resource).all()}
    finally:
        db.close()

    by_user = defaultdict(list)
    for u, i, s in scores:
        by_user[u].append((i, s))

    rng = np.random.default_rng(SEED)
    train, test = [], []
    for u, items in by_user.items():
        if len(items) < MIN_RATINGS:
            train.extend((u, i, s) for i, s in items)   # 小用户全部进训练集
            continue
        items = sorted(items)
        idx = rng.permutation(len(items))
        k = max(1, int(len(items) * 0.2))
        test_ids = set(items[j][0] for j in idx[:k])
        for i, s in items:
            (test if i in test_ids else train).append((u, i, s))
    return train, test, meta


def build_engine(interactions, meta):
    eng = RecommendationEngine()
    eng.fit([{"user_id": u, "resource_id": i, "score": s} for u, i, s in interactions], meta)
    return eng


def evaluate_algo(name, predict_fn, eng, train, test, all_items):
    """predict_fn(u_row, i_col) -> 预测分"""
    # ---- Top-N 指标 ----
    test_by_user = defaultdict(set)
    for u, i, s in test:
        if s >= 4:                       # 测试集正样本：高分(>=4)视为"喜欢"
            test_by_user[u].add(i)
    eval_users = [u for u, s in test_by_user.items() if s]

    p_list, r_list, recommended = [], [], set()
    for u in eval_users:
        u_row = eng.user_index.get(u)
        if u_row is None:
            continue
        interacted = set(np.where(eng.matrix[u_row] > 0)[0])
        preds = []
        for c in range(eng.matrix.shape[1]):
            if c not in interacted:
                preds.append((c, predict_fn(u_row, c)))
        preds.sort(key=lambda x: -x[1])
        top = [eng.index_item[c] for c, _ in preds[:N]]
        recommended.update(top)
        hits = len(set(top) & test_by_user[u])
        p_list.append(hits / N)
        r_list.append(hits / len(test_by_user[u]))

    coverage = len(recommended) / len(all_items)
    precision = float(np.mean(p_list)) if p_list else 0.0
    recall = float(np.mean(r_list)) if r_list else 0.0

    # ---- RMSE（覆盖测试集全部评分）----
    # 预测失败（算法无法覆盖该用户/物品，或预测值 <= 0）时以训练集全局均分代入，
    # 不丢弃样本：否则"只对能预测准的样本算误差"会使指标虚好。
    global_mean = float(np.mean([s for _, _, s in train])) if train else 3.0
    errs, filled = [], 0
    for u, i, s in test:
        u_row, i_col = eng.user_index.get(u), eng.item_index.get(i)
        if u_row is None or i_col is None:
            p = global_mean
            filled += 1
        else:
            p = predict_fn(u_row, i_col)
            if p <= 0:
                p = global_mean
                filled += 1
        errs.append((p - s) ** 2)
    rmse = float(np.sqrt(np.mean(errs))) if errs else 0.0

    return {"precision": round(precision, 4), "recall": round(recall, 4),
            "coverage": round(coverage, 4), "rmse": round(rmse, 4),
            "rmse_samples": len(errs), "rmse_filled": filled,
            "eval_users": len(eval_users)}


def main():
    print("加载数据并划分训练/测试集 ...")
    train, test, meta = load_matrix()
    all_items = set(meta.keys())
    print(f"训练集 {len(train)} 条，测试集 {len(test)} 条，物品 {len(all_items)} 个")

    print("训练推荐引擎 ...")
    eng = build_engine(train, meta)

    results = {}
    print("评估 User-based CF ...")
    results["user_cf"] = evaluate_algo("user_cf", eng.predict_user_cf, eng, train, test, all_items)
    print("评估 Item-based CF ...")
    results["item_cf"] = evaluate_algo("item_cf", eng.predict_item_cf, eng, train, test, all_items)
    print("评估 SVD ...")
    results["svd"] = evaluate_algo("svd", lambda ur, ic: float(eng.svd_pred[ur, ic]),
                                   eng, train, test, all_items)

    with open(os.path.join(OUT_DIR, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump({"n_train": len(train), "n_test": len(test), "n_items": len(all_items),
                   "top_n": N, "results": results}, f, ensure_ascii=False, indent=2)

    # ---- 绘图 ----
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei"]
    plt.rcParams["axes.unicode_minus"] = False

    algos = ["user_cf", "item_cf", "svd"]
    labels = ["User-based CF", "Item-based CF", "SVD"]

    # 图1：Top-N 指标对比
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    metrics = [("precision", "Precision@10"), ("recall", "Recall@10"), ("coverage", "Coverage@10")]
    for ax, (key, title) in zip(axes, metrics):
        vals = [results[a][key] for a in algos]
        bars = ax.bar(labels, vals, color=["#409eff", "#67c23a", "#e6a23c"], width=0.55)
        ax.set_title(title, fontsize=13)
        ax.set_ylim(0, max(vals) * 1.35 + 0.02)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.3f}",
                    ha="center", va="bottom", fontsize=10)
        ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "eval_metrics.png"), dpi=150)
    plt.close(fig)

    # 图2：RMSE 对比
    fig, ax = plt.subplots(figsize=(6, 4))
    vals = [results[a]["rmse"] for a in algos]
    bars = ax.bar(labels, vals, color=["#409eff", "#67c23a", "#e6a23c"], width=0.5)
    ax.set_title("三种算法 RMSE 对比（越低越好）", fontsize=13)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.3f}", ha="center", va="bottom", fontsize=10)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "rmse_curve.png"), dpi=150)
    plt.close(fig)

    print(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"结果已写入 {OUT_DIR}")


if __name__ == "__main__":
    main()
