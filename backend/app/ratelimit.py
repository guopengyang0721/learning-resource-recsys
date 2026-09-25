"""登录防暴力破解限流（内存计数实现）
- 同一用户名连续失败 MAX_ATTEMPTS 次 → 锁定 LOCK_SECONDS 秒
- 登录成功或锁定期满自动清零
原型用内存字典即可；生产环境建议 Redis（支持多进程/分布式）。
"""
import time
from collections import defaultdict

MAX_ATTEMPTS = 5
LOCK_SECONDS = 5 * 60                 # 连续失败达阈值后的锁定时长（5 分钟）
MAX_KEYS = 100_000                    # 键数量上限：防止随机用户名刷接口撑爆内存
# 剪枝的"不活跃"判定阈值：独立于锁定时长，且不小于锁定窗口，确保不会误清仍在锁定中的条目
PRUNE_IDLE_SECONDS = max(15 * 60, LOCK_SECONDS)

_attempts: dict = defaultdict(lambda: {"count": 0, "locked_until": 0.0, "last_seen": 0.0})


def _normalize_key(key: str) -> str:
    return key.strip().lower()


def _prune():
    """键数量超限时清理"长期不活跃"条目：距上次访问超过 PRUNE_IDLE_SECONDS 即可回收
    （不看 count 是否为 0——随机用户名刷出来的单次失败条目也要能被清理；
    该阈值不小于锁定窗口，因此被回收的条目锁定必然已到期）。"""
    if len(_attempts) <= MAX_KEYS:
        return
    now = time.time()
    for k in [k for k, v in _attempts.items()
              if now - v.get("last_seen", 0) > PRUNE_IDLE_SECONDS]:
        _attempts.pop(k, None)


def remaining_lock_seconds(key: str) -> int:
    """返回剩余锁定秒数；未锁定返回 0（锁定期满会顺手清零）。"""
    k = _normalize_key(key)
    rec = _attempts.get(k)
    if not rec:
        return 0
    left = rec["locked_until"] - time.time()
    if left > 0:
        return int(left) + 1
    if rec["locked_until"]:            # 锁定期满 → 重置
        _attempts.pop(k, None)
    return 0


def record_failure(key: str) -> int:
    """记录一次失败；达到阈值返回锁定秒数，否则返回 0。"""
    k = _normalize_key(key)
    _prune()
    if remaining_lock_seconds(k):      # 已锁定期间的失败不累计
        return remaining_lock_seconds(k)
    rec = _attempts[k]
    rec["count"] += 1
    rec["last_seen"] = time.time()
    if rec["count"] >= MAX_ATTEMPTS:
        rec["locked_until"] = time.time() + LOCK_SECONDS
        rec["count"] = 0
        return LOCK_SECONDS
    return 0


def record_success(key: str):
    _attempts.pop(_normalize_key(key), None)


# ---- 通用频率限制（滑动窗口）：用于注册等无"失败"语义的接口 ----
_hits: dict = defaultdict(list)
MAX_HIT_KEYS = 10_000


def client_rate_limited(key: str, limit: int, window: float) -> bool:
    """滑动窗口限流：window 秒内同一 key（如客户端 IP）最多 limit 次。
    返回 True 表示已超限（调用方应返回 429）。"""
    now = time.time()
    if len(_hits) > MAX_HIT_KEYS:              # 键过多时清理窗口外的历史记录
        for k in [k for k, v in _hits.items() if not v or now - v[-1] > window]:
            _hits.pop(k, None)
    recent = [t for t in _hits[key] if now - t < window]
    recent.append(now)
    _hits[key] = recent
    return len(recent) > limit
