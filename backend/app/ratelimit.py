"""登录防暴力破解限流（内存计数实现）
- 同一用户名连续失败 MAX_ATTEMPTS 次 → 锁定 LOCK_SECONDS 秒
- 登录成功或锁定期满自动清零
原型用内存字典即可；生产环境建议 Redis（支持多进程/分布式）。
"""
import time
from collections import defaultdict

MAX_ATTEMPTS = 5
LOCK_SECONDS = 15 * 60
MAX_KEYS = 100_000                    # 键数量上限：防止随机用户名刷接口撑爆内存

_attempts: dict = defaultdict(lambda: {"count": 0, "locked_until": 0.0, "last_seen": 0.0})


def _normalize_key(key: str) -> str:
    return key.strip().lower()


def _prune():
    """键数量超限时清理"长期不活跃"条目：距上次访问超过 LOCK_SECONDS 即可回收
    （不看 count 是否为 0——随机用户名刷出来的单次失败条目也要能被清理）。"""
    if len(_attempts) <= MAX_KEYS:
        return
    now = time.time()
    for k in [k for k, v in _attempts.items()
              if now - v.get("last_seen", 0) > LOCK_SECONDS]:
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
