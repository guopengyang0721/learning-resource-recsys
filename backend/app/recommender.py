"""推荐引擎 —— 协同过滤（User-based / Item-based）+ SVD 矩阵分解 + 热门兜底
基于 numpy / scikit-learn 实现，包含：
1. 隐式行为折算评分（浏览=1、下载=3、收藏=4、显式评分=1~5）
2. 用户-物品评分矩阵构建
3. User-based CF / Item-based CF（余弦相似度）
4. SVD 隐语义模型（TruncatedSVD，均值填充）
5. 冷启动：新用户热门资源兜底；模型更新：离线训练 + 内存缓存
"""
import threading
import time
from collections import OrderedDict

import numpy as np

# 隐式行为 → 评分折算系数
ACTION_WEIGHT = {"view": 1, "download": 3, "favorite": 4}

IMPLICIT_MIN, IMPLICIT_MAX = 1.0, 4.0   # 隐式评分区间
EXPLICIT_MAX = 5.0                      # 显式评分上限


def _locked(method):
    """方法级读写锁：fit 与 recommend/hot/similar 互斥，避免训练期间的半更新读。"""
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapper


def implicit_to_score(raw):
    """将隐式行为强度折算到 [1,4] 区间的伪评分。"""
    if raw <= 0:
        return 0.0
    return IMPLICIT_MIN + (min(raw, 10) - 1) / 9.0 * (IMPLICIT_MAX - IMPLICIT_MIN)


class RecommendationEngine:
    """推荐引擎：离线训练 + 在线缓存。"""

    def __init__(self):
        self._lock = threading.RLock()   # 训练/预测互斥锁（可重入）
        self.user_index = {}        # user_id -> row
        self.item_index = {}        # resource_id -> col
        self.index_user = {}
        self.index_item = {}
        self.matrix = None          # 用户-物品评分矩阵（稀疏，0 表示未评分）
        self.item_meta = {}         # resource_id -> {title, category, ...}
        self.user_sim = None
        self.item_sim = None
        self.svd_pred = None
        self.trained_at = 0.0
        self.popularity = None      # 物品热度（兜底与冷启动用）
        self._pred_cache = OrderedDict()   # 预测结果缓存（LRU：容量满淘汰最旧，替代整清）

    # ---------- 数据准备 ----------
    @_locked
    def fit(self, interactions, item_meta):
        """interactions: list[dict(user_id, resource_id, score)]
        item_meta: dict(resource_id -> dict(title, category, ...))"""
        self.item_meta = item_meta
        users = sorted({i["user_id"] for i in interactions})
        items = sorted({i["resource_id"] for i in interactions})
        self.user_index = {u: r for r, u in enumerate(users)}
        self.item_index = {i: c for c, i in enumerate(items)}
        self.index_user = {r: u for u, r in self.user_index.items()}
        self.index_item = {c: i for i, c in self.item_index.items()}

        n_u, n_i = len(users), len(items)
        m = np.zeros((n_u, n_i), dtype=np.float32)
        for it in interactions:
            m[self.user_index[it["user_id"]], self.item_index[it["resource_id"]]] = it["score"]
        self.matrix = m

        # 物品热度：评分人数 × 平均分加权
        cnt = (m > 0).sum(axis=0)
        avg = np.divide(m.sum(axis=0), np.maximum(cnt, 1))
        self.popularity = cnt * 0.6 + avg * 8.0

        self._train_user_cf()
        self._train_item_cf()
        self._train_svd()
        self.trained_at = time.time()
        self._pred_cache.clear()

    # ---------- 算法 ----------
    def _train_user_cf(self):
        """User-based CF：用户间余弦相似度（仅在共同评分物品上计算）。"""
        m = self.matrix
        norm = np.linalg.norm(m, axis=1, keepdims=True)
        normed = m / np.maximum(norm, 1e-9)
        # 未评分位置不参与相似度：用掩码修正
        mask = (m > 0).astype(np.float32)
        dot = normed @ normed.T
        overlap = mask @ mask.T
        # 余弦相似度（共同物品数过少的用户对衰减）
        sim = dot / np.maximum(overlap, 1e-9) * np.minimum(overlap, 5) / 5.0
        np.fill_diagonal(sim, 0)
        self.user_sim = sim.astype(np.float32)

    def _train_item_cf(self):
        """Item-based CF：物品间余弦相似度。"""
        m = self.matrix.T
        norm = np.linalg.norm(m, axis=1, keepdims=True)
        normed = m / np.maximum(norm, 1e-9)
        mask = (m > 0).astype(np.float32)
        dot = normed @ normed.T
        overlap = mask @ mask.T
        sim = dot / np.maximum(overlap, 1e-9) * np.minimum(overlap, 5) / 5.0
        np.fill_diagonal(sim, 0)
        self.item_sim = sim.astype(np.float32)

    def _train_svd(self, k=20):
        """SVD 隐语义模型：均值填充 + TruncatedSVD 重构。"""
        from sklearn.decomposition import TruncatedSVD
        m = self.matrix
        mean = np.divide(m.sum(axis=1), np.maximum((m > 0).sum(axis=1), 1)).reshape(-1, 1)
        filled = np.where(m > 0, m, mean.astype(np.float32))
        k = int(min(k, max(2, min(m.shape) - 1)))
        svd = TruncatedSVD(n_components=k, random_state=42)
        self.svd_pred = svd.fit_transform(filled) @ svd.components_

    # ---------- 预测 ----------
    def predict_user_cf(self, u_row, i_col, topk=20):
        sim = self.user_sim[u_row].copy()
        sim[u_row] = 0
        idx = np.argsort(sim)[::-1][:topk]
        num, den = 0.0, 0.0
        for r in idx:
            s = self.matrix[r, i_col]
            if s > 0 and sim[r] > 0:
                num += sim[r] * s
                den += sim[r]
        return num / den if den > 1e-9 else 0.0

    def predict_item_cf(self, u_row, i_col, topk=20):
        rated = np.where(self.matrix[u_row] > 0)[0]
        if len(rated) == 0:
            return 0.0
        sim = self.item_sim[i_col, rated]
        weights = self.matrix[u_row, rated]
        order = np.argsort(sim)[::-1][:topk]
        num = float((sim[order] * weights[order]).sum())
        den = float(np.abs(sim[order]).sum())
        return num / den if den > 1e-9 else 0.0

    def _topn_by(self, scores_fn, u_id, n):
        """通用 Top-N：对用户未交互物品预测评分并取前 N。"""
        u_row = self.user_index.get(u_id)
        if u_row is None:
            return []
        interacted = set(np.where(self.matrix[u_row] > 0)[0])
        preds = []
        for c in range(self.matrix.shape[1]):
            if c in interacted:
                continue
            p = scores_fn(u_row, c)
            if p > 0:
                preds.append((c, p))
        preds.sort(key=lambda x: -x[1])
        return preds[:n]

    @_locked
    def recommend(self, u_id, n=10, algo="user_cf"):
        """个性化 Top-N 推荐（带数据驱动解释），LRU 内存缓存。"""
        cache_key = (u_id, n, algo)
        if cache_key in self._pred_cache:
            self._pred_cache.move_to_end(cache_key)      # 命中即提到最新，LRU 淘汰不被误伤
            return self._pred_cache[cache_key]

        if algo == "user_cf":
            fn = lambda ur, ic: self.predict_user_cf(ur, ic)
        elif algo == "item_cf":
            fn = lambda ur, ic: self.predict_item_cf(ur, ic)
        else:  # svd
            fn = lambda ur, ic: float(self.svd_pred[ur, ic])

        preds = self._topn_by(fn, u_id, n)
        u_row = self.user_index.get(u_id)
        results = []
        for col, score in preds:
            rid = self.index_item[col]
            results.append({
                "resource_id": int(rid),
                "title": self.item_meta.get(rid, {}).get("title", ""),
                "category": self.item_meta.get(rid, {}).get("category", ""),
                "type": self.item_meta.get(rid, {}).get("type", ""),
                "score": round(float(min(score, EXPLICIT_MAX)), 2),
                "reason": self._explain(u_row, col, algo, float(score)) if u_row is not None
                          else "全站热门资源（冷启动推荐）",
            })
        if len(self._pred_cache) > 500:
            self._pred_cache.popitem(last=False)         # 容量满：淘汰最旧（LRU）
        self._pred_cache[cache_key] = results
        return results

    def _explain(self, u_row, col, algo, score):
        """数据驱动的推荐解释：从相似度矩阵中提取真实依据，而非模板文案。"""
        if algo == "user_cf":
            sim = self.user_sim[u_row].copy()
            sim[u_row] = 0
            idx = np.argsort(sim)[::-1][:20]          # 与该用户最相似的前 20 人
            raters = [r for r in idx if self.matrix[r, col] > 0 and sim[r] > 0]
            if raters:
                avg = float(np.mean([self.matrix[r, col] for r in raters]))
                return (f"{len(raters)} 位与你口味最相似的同学都看过该资源，"
                        f"他们的平均评分 {avg:.1f}")
            return "与你行为模式相似的同学喜欢该类资源"
        if algo == "item_cf":
            rated = np.where(self.matrix[u_row] > 0)[0]
            if len(rated):
                sims = self.item_sim[col, rated]
                order = np.argsort(sims)[::-1][:20]
                best_col = rated[order[0]]
                best_sim = float(sims[order[0]])
                if best_sim > 0.01:
                    best_title = self.item_meta.get(self.index_item[best_col], {}).get("title", "")
                    return f"因为你看过《{best_title}》，本资源与其行为相似度 {best_sim:.2f}"
            return "该资源与你已交互过的资源行为相似"
        return f"隐语义模型基于你的历史行为预测偏好评分 {score:.1f}"

    @_locked
    def similar_items(self, resource_id, n=5):
        """基于 Item-CF 的相似资源（"看了又看"）：与指定资源行为最相似的其他资源。"""
        col = self.item_index.get(resource_id)
        if col is None or self.item_sim is None:
            return []
        base_title = self.item_meta.get(resource_id, {}).get("title", "")
        sims = self.item_sim[col].copy()
        order = np.argsort(sims)[::-1]
        out = []
        for c in order:
            if c == col or sims[c] <= 0.01:
                continue
            rid = self.index_item[c]
            meta = self.item_meta.get(rid, {})
            out.append({
                "resource_id": int(rid),
                "title": meta.get("title", ""),
                "category": meta.get("category", ""),
                "type": meta.get("type", ""),
                "sim": round(float(sims[c]), 3),
                "reason": f"看过《{base_title}》的人也看过这条资源",
            })
            if len(out) >= n:
                break
        return out

    @_locked
    def hot_resources(self, limit=10):
        """热门资源（冷启动兜底）。"""
        if self.popularity is None:
            return []
        order = np.argsort(self.popularity)[::-1][:limit]
        out = []
        for c in order:
            rid = self.index_item[c]
            out.append({
                "resource_id": int(rid),
                "title": self.item_meta.get(rid, {}).get("title", ""),
                "category": self.item_meta.get(rid, {}).get("category", ""),
                "type": self.item_meta.get(rid, {}).get("type", ""),
                "hot": round(float(self.popularity[c]), 1),
                "reason": "全站热门资源（冷启动推荐）",
            })
        return out

    def is_user_known(self, u_id):
        return u_id in self.user_index


# 全局单例
engine = RecommendationEngine()
