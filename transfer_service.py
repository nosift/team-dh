"""
按月到期自动转移到新 Team

- 不改变现有兑换逻辑，只在后台到期后尝试给用户发送“新 Team 邀请”
- 默认关闭（AUTO_TRANSFER_ENABLED=false），避免对现有部署产生影响
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from datetime import datetime, timedelta

from database import db
from logger import log
import config
from team_service import invite_single_email, get_invite_status_for_email, remove_member_by_email, get_member_info_for_email
from redemption_service import RedemptionService
from date_utils import add_months_same_day


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    v = raw.strip().lower()
    if v in {"1", "true", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _expires_at_for_new_term(now: datetime) -> datetime:
    term_months = int(os.getenv("AUTO_TRANSFER_TERM_MONTHS", "1") or 1)
    term_months = max(1, min(24, term_months))
    return add_months_same_day(now, term_months)


def _pick_next_team(*, current_account_id: str | None, current_team_name: str | None, email: str) -> list[dict]:
    """
    生成候选 Team 列表（按优先顺序）。
    优先“当前 Team 的下一个 Team”，再 round-robin。
    """
    teams = [t for t in (config.TEAMS or []) if (t.get("auth_token") or "").strip() and (t.get("account_id") or "").strip()]
    if len(teams) <= 1:
        return []

    def idx_of() -> int | None:
        if current_account_id:
            for i, t in enumerate(teams):
                if (t.get("account_id") or "") == current_account_id:
                    return i
        if current_team_name:
            for i, t in enumerate(teams):
                if (t.get("name") or "") == current_team_name:
                    return i
        return None

    cur_idx = idx_of()
    start = (cur_idx + 1) if cur_idx is not None else (abs(hash(email)) % len(teams))
    ordered: list[dict] = []
    for i in range(len(teams)):
        t = teams[(start + i) % len(teams)]
        if current_account_id and (t.get("account_id") or "") == current_account_id:
            continue
        if current_team_name and (t.get("name") or "") == current_team_name:
            continue
        ordered.append(t)
    return ordered


def _next_attempt_time(attempts: int) -> datetime:
    # 5m, 10m, 20m, 40m ... 最多 24h
    base = 300
    secs = min(24 * 3600, base * (2 ** max(0, min(12, int(attempts or 0)))))
    return datetime.now() + timedelta(seconds=secs)


def run_transfer_once(*, limit: int = 20) -> int:
    """
    执行一轮“到期自动转移”，返回成功转移人数。
    """
    lock_by = uuid.uuid4().hex
    if not db.acquire_lock("auto_transfer_monthly", lock_by=lock_by, lock_seconds=90):
        return 0

    moved = 0
    try:
        # 先同步“实际加入时间”（以 invite accepted 的时间为准）
        _sync_joined_leases(limit=50)

        due = db.list_due_member_leases(limit=limit)
        if not due:
            return 0

        for lease in due:
            moved += 1 if _process_transfer_for_lease(lease) else 0

        return moved
    finally:
        db.release_lock("auto_transfer_monthly", lock_by=lock_by)


def _sync_joined_leases(*, limit: int = 50):
    """
    将 member_leases 中 awaiting_join 的记录，尽量同步为“已加入”的真实时间。
    以当前 Team 的 invites 中 accepted/completed 的时间字段为准。
    """
    lock_by = uuid.uuid4().hex
    if not db.acquire_lock("auto_transfer_join_sync", lock_by=lock_by, lock_seconds=60):
        return

    try:
        rows = db.list_member_leases_awaiting_join(limit=limit)
        if not rows:
            return

        for lease in rows:
            email = (lease.get("email") or "").strip().lower()
            team_name = lease.get("team_name")
            if not email or not team_name:
                continue

            team_cfg = config.resolve_team(team_name) or {}
            if not team_cfg:
                continue

            inv = get_invite_status_for_email(team_cfg, email)
            join_at = None

            # 1) 优先从 invites 找 accepted/completed 的时间
            if inv.get("found"):
                status = (inv.get("status") or "").strip().lower()
                if status in {"accepted", "completed", "done"}:
                    ts = inv.get("timestamp")
                    if isinstance(ts, str) and ts:
                        try:
                            join_at = datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
                        except Exception:
                            join_at = None

            # 2) 若 invites 不可用/不包含 accepted，则从 members 列表兜底：只要已在成员列表，即视为已加入
            if not join_at:
                mi = get_member_info_for_email(team_cfg, email)
                if mi.get("found"):
                    ts = mi.get("joined_at")
                    if isinstance(ts, str) and ts:
                        try:
                            join_at = datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
                        except Exception:
                            join_at = None
                    if not join_at:
                        # 成员列表没有明确加入时间字段时，用当前时间近似（并在事件中标注）
                        join_at = datetime.now()
                        db.add_member_lease_event(
                            email=email,
                            action="joined_fallback",
                            from_team=team_name,
                            to_team=None,
                            message="成员列表未提供加入时间字段，使用当前时间近似 join_at",
                        )

            if not join_at:
                continue

            expires_at = _expires_at_for_new_term(join_at)
            db.update_member_lease_joined(email=email, join_at=join_at, expires_at=expires_at, from_team=team_name)
    finally:
        db.release_lock("auto_transfer_join_sync", lock_by=lock_by)


def sync_joined_leases_once(*, limit: int = 50) -> int:
    """
    管理后台手动触发：同步 awaiting_join 的 join_at。
    返回本次成功同步的条数（粗略统计）。
    """
    before = 0
    after = 0
    try:
        rows = db.list_member_leases_awaiting_join(limit=limit)
        before = len(rows)
    except Exception:
        before = 0

    _sync_joined_leases(limit=limit)

    try:
        rows2 = db.list_member_leases_awaiting_join(limit=limit)
        after = len(rows2)
    except Exception:
        after = before

    synced = max(0, before - after)
    return synced


def run_transfer_for_email(email: str) -> dict:
    """
    管理后台手动触发：只执行指定邮箱的一次到期转移（不强制到期）。
    返回：{success, moved, message}
    """
    target = (email or "").strip().lower()
    if not target:
        return {"success": False, "moved": 0, "message": "email 不能为空"}

    # 先尽力同步该邮箱的 join_at
    try:
        _sync_joined_leases(limit=80)
    except Exception:
        pass

    lease = db.get_member_lease(target)
    if not lease:
        return {"success": False, "moved": 0, "message": "租约不存在"}

    ok = _process_transfer_for_lease(lease, only_if_due=True)
    return {"success": True, "moved": 1 if ok else 0, "message": ("已转移" if ok else "未到期或转移失败（请看事件/错误）")}


def _process_transfer_for_lease(lease: dict, *, only_if_due: bool = True) -> bool:
    email = (lease.get("email") or "").strip().lower()
    if not email:
        return False

    # 未同步 join_at 不参与到期转移
    if (lease.get("status") or "").strip() == "awaiting_join":
        return False

    if only_if_due:
        try:
            exp = lease.get("expires_at")
            if isinstance(exp, str) and exp:
                exp_dt = datetime.fromisoformat(exp)
                if exp_dt > datetime.now():
                    return False
        except Exception:
            # 若解析失败，保守起见不转移
            return False

    if not db.mark_member_lease_transferring(email):
        return False

    current_team_name = lease.get("team_name")
    current_account_id = lease.get("team_account_id")

    candidates = _pick_next_team(
        current_account_id=current_account_id,
        current_team_name=current_team_name,
        email=email,
    )

    if not candidates:
        msg = "没有可用的新 Team（请至少配置 2 个 Team）"
        db.update_member_lease_transfer_failure(email=email, message=msg, next_attempt_at=_next_attempt_time(int(lease.get("attempts") or 0)))
        db.add_member_lease_event(email=email, action="transfer_failed", from_team=current_team_name, to_team=None, message=msg)
        return False

    transferred = False
    last_err = ""

    kick_old = (
        _env_bool("AUTO_TRANSFER_AUTO_LEAVE_OLD_TEAM", False)
        or _env_bool("AUTO_TRANSFER_KICK_OLD_TEAM", False)
    )
    kicked_old = False

    for t in candidates:
        team_name = t.get("name") or ""
        account_id = t.get("account_id") or ""

        if kick_old and (not kicked_old) and current_team_name:
            old_cfg = config.resolve_team(current_team_name) or {}
            if not old_cfg:
                last_err = f"旧 Team 配置不存在: {current_team_name}"
                break
            ok_kick, kick_msg = remove_member_by_email(old_cfg, email)
            if not ok_kick:
                last_err = f"退出旧 Team 失败: {kick_msg}"
                db.add_member_lease_event(email=email, action="leave_old_failed", from_team=current_team_name, to_team=None, message=kick_msg)
                break
            kicked_old = True
            db.add_member_lease_event(email=email, action="left_old_team", from_team=current_team_name, to_team=None, message="已退出旧 Team")

        seat_check = RedemptionService._check_team_seats(team_name)
        if not seat_check.get("available"):
            last_err = seat_check.get("message") or "无可用席位"
            continue

        ok, msg = invite_single_email(email, t)
        if ok:
            now = datetime.now()
            expires_at = _expires_at_for_new_term(now)
            db.update_member_lease_transfer_success(
                email=email,
                new_team_name=team_name,
                new_team_account_id=account_id,
                start_at=now,
                expires_at=expires_at,
            )
            db.add_member_lease_event(
                email=email,
                action="transferred",
                from_team=current_team_name,
                to_team=team_name,
                message="自动转移：已发送新 Team 邀请，等待接受；到期日将以实际加入时间为准自动修正",
            )
            log.info(f"自动转移成功: {email} -> {team_name}", icon="success")
            transferred = True
            break
        last_err = msg or "邀请失败"

    if not transferred:
        attempts = int(lease.get("attempts") or 0) + 1
        next_at = _next_attempt_time(attempts)
        msg = last_err or "无可用 Team/邀请失败"
        db.update_member_lease_transfer_failure(email=email, message=msg, next_attempt_at=next_at)
        db.add_member_lease_event(email=email, action="transfer_failed", from_team=current_team_name, to_team=None, message=msg)
        return False

    return True


_worker_started = False


def start_transfer_worker():
    """
    启动后台线程（每个进程会启动一次；多 worker 通过 DB 锁确保只有一个实际执行）。
    """
    global _worker_started
    if _worker_started:
        return
    _worker_started = True

    if not _env_bool("AUTO_TRANSFER_ENABLED", False):
        log.info("AUTO_TRANSFER_ENABLED=false，自动转移功能未启用", icon="info")
        return

    poll_seconds = int(os.getenv("AUTO_TRANSFER_POLL_SECONDS", "300") or 300)
    poll_seconds = max(30, poll_seconds)

    def loop():
        log.info(f"自动转移线程已启动（每 {poll_seconds}s 检查一次）", icon="start")
        while True:
            try:
                moved = run_transfer_once(limit=20)
                if moved:
                    log.info(f"本轮自动转移完成: {moved} 人", icon="team")
            except Exception as e:
                log.warning(f"自动转移任务异常: {e}")
            time.sleep(poll_seconds)

    t = threading.Thread(target=loop, name="auto-transfer", daemon=True)
    t.start()
