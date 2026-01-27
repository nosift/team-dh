"""
按月到期自动转移到新 Team

- 不改变现有兑换逻辑，只在后台到期后尝试给用户发送"新 Team 邀请"
- 默认关闭（AUTO_TRANSFER_ENABLED=false），避免对现有部署产生影响
- 优化：事务保护、重试限制、改进席位检查
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
from config import env_bool
from team_service import invite_single_email, get_invite_status_for_email, remove_member_by_email, get_member_info_for_email, batch_invite_to_team, get_team_stats
from redemption_service import RedemptionService
from date_utils import add_months_same_day, parse_datetime_loose


# 最大重试次数（超过后标记为 failed）
MAX_TRANSFER_ATTEMPTS = int(os.getenv("MAX_TRANSFER_ATTEMPTS", "10"))


def _expires_at_for_new_term(now: datetime) -> datetime:
    term_months = int(os.getenv("AUTO_TRANSFER_TERM_MONTHS", "1") or 1)
    term_months = max(1, min(24, term_months))
    return add_months_same_day(now, term_months)


def _pick_next_team(*, current_account_id: str | None, current_team_name: str | None, email: str) -> list[dict]:
    """
    生成候选 Team 列表（按优先顺序）。
    优化：按可用席位比例排序，优先选择空闲 Team。
    """
    teams = [t for t in (config.TEAMS or []) if (t.get("auth_token") or "").strip() and (t.get("account_id") or "").strip()]
    if len(teams) <= 1:
        return []

    # 过滤掉当前 Team
    candidates = []
    for t in teams:
        if current_account_id and (t.get("account_id") or "") == current_account_id:
            continue
        if current_team_name and (t.get("name") or "") == current_team_name:
            continue
        candidates.append(t)

    if not candidates:
        return []

    # 获取每个 Team 的席位信息并排序
    team_with_stats = []
    for t in candidates:
        team_name = t.get("name") or ""
        try:
            stats = get_team_stats(team_name)
            total = stats.get("total", 0)
            used = stats.get("used", 0)
            pending = stats.get("pending", 0)
            available = total - used - pending

            # 计算可用席位比例（用于排序）
            if total > 0:
                availability_ratio = available / total
            else:
                availability_ratio = 0

            team_with_stats.append({
                "team": t,
                "available": available,
                "ratio": availability_ratio,
                "total": total
            })
        except Exception as e:
            log.warning(f"获取 Team {team_name} 席位信息失败: {e}")
            # 失败的 Team 放到最后
            team_with_stats.append({
                "team": t,
                "available": 0,
                "ratio": 0,
                "total": 0
            })

    # 按可用席位比例降序排序（比例高的优先）
    team_with_stats.sort(key=lambda x: (x["ratio"], x["available"]), reverse=True)

    # 返回排序后的 Team 列表
    return [item["team"] for item in team_with_stats]


def _next_attempt_time(attempts: int) -> datetime:
    # 5m, 10m, 20m, 40m ... 最多 24h
    base = 300
    secs = min(24 * 3600, base * (2 ** max(0, min(12, int(attempts or 0)))))
    return datetime.now() + timedelta(seconds=secs)


def _defer_join_sync_seconds(reason: str) -> int:
    # 让自动同步不会刷屏：不同原因采用不同延迟（手动“同步加入时间”会强制忽略 next_attempt_at）
    if reason in {"member_no_time"}:
        return 24 * 3600
    if reason in {"invite_not_accepted"}:
        return 20 * 60
    if reason in {"invite_error", "member_error"}:
        return 60 * 60
    if reason in {"not_joined"}:
        return 30 * 60
    return 30 * 60


def _defer_join_sync(*, lease: dict, message: str, reason: str):
    try:
        email = (lease.get("email") or "").strip().lower()
        if not email:
            return
        delay = _defer_join_sync_seconds(reason)
        next_at = datetime.now() + timedelta(seconds=delay)
        db.defer_member_lease_join_sync(email=email, next_attempt_at=next_at, last_error=message)
    except Exception:
        pass


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
        _sync_joined_leases(limit=50, include_not_due=False, record_events=False)

        due = db.list_due_member_leases(limit=limit)
        if not due:
            return 0

        for lease in due:
            moved += 1 if _process_transfer_for_lease(lease) else 0

        return moved
    finally:
        db.release_lock("auto_transfer_monthly", lock_by=lock_by)


def _sync_joined_leases(*, limit: int = 50, include_not_due: bool = False, record_events: bool = True):
    """
    将 member_leases 中 pending 的记录，尽量同步为"已加入"的真实时间。
    以当前 Team 的 invites 中 accepted/completed 的时间字段为准。
    """
    lock_by = uuid.uuid4().hex
    if not db.acquire_lock("auto_transfer_join_sync", lock_by=lock_by, lock_seconds=60):
        return 0, 0

    checked = 0
    synced = 0
    invite_errors = 0
    invite_not_accepted = 0
    member_errors = 0
    member_no_time = 0
    not_joined = 0
    skipped = 0
    try:
        rows = db.list_member_leases_pending_join_with_due(limit=limit, include_not_due=include_not_due)
        if not rows:
            return {
                "checked": 0,
                "synced": 0,
                "invite_errors": 0,
                "invite_not_accepted": 0,
                "member_errors": 0,
                "member_no_time": 0,
                "not_joined": 0,
                "skipped": 0,
            }

        for lease in rows:
            email = (lease.get("email") or "").strip().lower()
            team_name = lease.get("team_name")
            if not email or not team_name:
                skipped += 1
                continue
            checked += 1

            team_cfg = config.resolve_team(team_name) or {}
            if not team_cfg:
                if record_events:
                    db.add_member_lease_event(
                        email=email,
                        action="sync_skip",
                        from_team=team_name,
                        to_team=None,
                        message="Team 配置不存在，无法同步 join_at",
                    )
                skipped += 1
                continue

            try:
                inv = get_invite_status_for_email(team_cfg, email)
            except Exception as e:
                inv = {"found": False, "error": str(e)}
            join_at = None

            # 1) 优先从 invites 找 accepted/completed 的时间
            if inv.get("found"):
                status = (inv.get("status") or "").strip().lower()
                if status in {"accepted", "completed", "done"}:
                    ts = inv.get("timestamp")
                    if isinstance(ts, str) and ts:
                        try:
                            join_at = parse_datetime_loose(ts)
                        except Exception:
                            join_at = None
                else:
                    invite_not_accepted += 1
                    if not include_not_due:
                        _defer_join_sync(lease=lease, message=f"invites 状态={status or 'unknown'}，未达到 accepted/completed", reason="invite_not_accepted")
                    if record_events:
                        db.add_member_lease_event(
                            email=email,
                            action="sync_invite_status",
                            from_team=team_name,
                            to_team=None,
                            message=f"invites 状态={status or 'unknown'}，未达到 accepted/completed",
                        )
            elif inv.get("error"):
                invite_errors += 1
                if not include_not_due:
                    _defer_join_sync(lease=lease, message=f"拉取 invites 失败：{inv.get('error')}", reason="invite_error")
                if record_events:
                    db.add_member_lease_event(
                        email=email,
                        action="sync_invite_error",
                        from_team=team_name,
                        to_team=None,
                        message=f"拉取 invites 失败：{inv.get('error')}",
                    )

            # 2) 若 invites 不可用/不包含 accepted，则从 members 列表兜底：只要已在成员列表，即视为已加入
            if not join_at:
                try:
                    mi = get_member_info_for_email(team_cfg, email)
                except Exception as e:
                    mi = {"found": False, "error": str(e)}
                if mi.get("found"):
                    ts = mi.get("joined_at")
                    if isinstance(ts, str) and ts:
                        try:
                            join_at = parse_datetime_loose(ts)
                        except Exception:
                            join_at = None
                    if not join_at:
                        allow_approx = env_bool("AUTO_TRANSFER_ALLOW_APPROX_JOIN_AT", False)
                        if allow_approx:
                            # 成员列表没有明确加入时间字段时，用当前时间近似（并在事件中标注）
                            join_at = datetime.now()
                            if record_events:
                                db.add_member_lease_event(
                                    email=email,
                                    action="joined_fallback",
                                    from_team=team_name,
                                    to_team=None,
                                    message="成员列表未提供加入时间字段，已使用当前时间近似 join_at（AUTO_TRANSFER_ALLOW_APPROX_JOIN_AT=true）",
                                )
                        else:
                            member_no_time += 1
                            if not include_not_due:
                                _defer_join_sync(lease=lease, message="成员列表未提供加入时间字段，未写入 joined_at（保持 pending；可手动录入 joined_at / 在后台点'近似加入' / 或开启 AUTO_TRANSFER_ALLOW_APPROX_JOIN_AT）", reason="member_no_time")
                            if record_events:
                                db.add_member_lease_event(
                                    email=email,
                                    action="sync_member_no_time",
                                    from_team=team_name,
                                    to_team=None,
                                    message="成员列表未提供加入时间字段，未写入 joined_at（保持 pending；可手动录入 joined_at / 在后台点'近似加入' / 或开启 AUTO_TRANSFER_ALLOW_APPROX_JOIN_AT）",
                                )
                            continue
                elif mi.get("error"):
                    member_errors += 1
                    if not include_not_due:
                        _defer_join_sync(lease=lease, message=f"拉取 members 失败：{mi.get('error')}", reason="member_error")
                    if record_events:
                        db.add_member_lease_event(
                            email=email,
                            action="sync_member_error",
                            from_team=team_name,
                            to_team=None,
                            message=f"拉取 members 失败：{mi.get('error')}",
                        )

            if not join_at:
                not_joined += 1
                if not include_not_due:
                    _defer_join_sync(lease=lease, message="未在 invites(accepted/completed) 或 members 中找到已加入证据", reason="not_joined")
                if record_events:
                    db.add_member_lease_event(
                        email=email,
                        action="sync_not_joined",
                        from_team=team_name,
                        to_team=None,
                        message="未在 invites(accepted/completed) 或 members 中找到已加入证据",
                    )
                continue

            expires_at = _expires_at_for_new_term(join_at)
            db.update_member_lease_joined(email=email, joined_at=join_at, expires_at=expires_at, from_team=team_name)
            synced += 1
        return {
            "checked": checked,
            "synced": synced,
            "invite_errors": invite_errors,
            "invite_not_accepted": invite_not_accepted,
            "member_errors": member_errors,
            "member_no_time": member_no_time,
            "not_joined": not_joined,
            "skipped": skipped,
        }
    finally:
        db.release_lock("auto_transfer_join_sync", lock_by=lock_by)


def _sync_joined_lease_for_email(email: str, *, record_events: bool = True) -> dict:
    """
    只同步指定邮箱（避免 run_transfer_for_email 时扫全表导致卡顿）。
    返回：{checked, synced, reason}
    """
    target = (email or "").strip().lower()
    if not target:
        return {"checked": 0, "synced": 0, "reason": "empty_email"}

    lease = db.get_member_lease(target)
    if not lease:
        return {"checked": 0, "synced": 0, "reason": "lease_not_found"}

    if (lease.get("status") or "").strip() != "pending":
        return {"checked": 0, "synced": 0, "reason": "not_pending"}

    team_name = (lease.get("team_name") or "").strip()
    team_cfg = config.resolve_team(team_name) or {}
    if not team_cfg:
        if record_events:
            db.add_member_lease_event(
                email=target,
                action="sync_skip",
                from_team=team_name or None,
                to_team=None,
                message="Team 配置不存在，无法同步 join_at",
            )
        return {"checked": 1, "synced": 0, "reason": "team_cfg_missing"}

    # 1) 优先从 invites 找 accepted/completed 的时间
    join_at = None
    try:
        inv = get_invite_status_for_email(team_cfg, target)
    except Exception as e:
        inv = {"found": False, "error": str(e)}

    if inv.get("found"):
        status = (inv.get("status") or "").strip().lower()
        if status in {"accepted", "completed", "done"}:
            ts = inv.get("timestamp")
            if isinstance(ts, str) and ts:
                try:
                    join_at = parse_datetime_loose(ts)
                except Exception:
                    join_at = None
        else:
            _defer_join_sync(lease=lease, message=f"invites 状态={status or 'unknown'}，未达到 accepted/completed", reason="invite_not_accepted")
            if record_events:
                db.add_member_lease_event(
                    email=target,
                    action="sync_invite_status",
                    from_team=team_name,
                    to_team=None,
                    message=f"invites 状态={status or 'unknown'}，未达到 accepted/completed",
                )
    elif inv.get("error"):
        _defer_join_sync(lease=lease, message=f"拉取 invites 失败：{inv.get('error')}", reason="invite_error")
        if record_events:
            db.add_member_lease_event(
                email=target,
                action="sync_invite_error",
                from_team=team_name,
                to_team=None,
                message=f"拉取 invites 失败：{inv.get('error')}",
            )

    # 2) invites 不可用/不包含 accepted，则从 members 兜底
    if not join_at:
        try:
            mi = get_member_info_for_email(team_cfg, target)
        except Exception as e:
            mi = {"found": False, "error": str(e)}

        if mi.get("found"):
            ts = mi.get("joined_at")
            if isinstance(ts, str) and ts:
                try:
                    join_at = parse_datetime_loose(ts)
                except Exception:
                    join_at = None

            if not join_at:
                allow_approx = env_bool("AUTO_TRANSFER_ALLOW_APPROX_JOIN_AT", False)
                if allow_approx:
                    join_at = datetime.now()
                    db.add_member_lease_event(
                        email=target,
                        action="joined_fallback",
                        from_team=team_name,
                        to_team=None,
                        message="成员列表未提供加入时间字段，已使用当前时间近似 join_at（AUTO_TRANSFER_ALLOW_APPROX_JOIN_AT=true）",
                    )
                else:
                    if record_events:
                        db.add_member_lease_event(
                            email=target,
                            action="sync_member_no_time",
                            from_team=team_name,
                            to_team=None,
                            message="成员列表未提供加入时间字段，未写入 join_at（保持 awaiting_join；可手动录入 join_at / 在后台点“近似加入” / 或开启 AUTO_TRANSFER_ALLOW_APPROX_JOIN_AT）",
                        )
                    _defer_join_sync(lease=lease, message="成员列表未提供加入时间字段，未写入 join_at（保持 awaiting_join；可手动录入 join_at / 在后台点“近似加入” / 或开启 AUTO_TRANSFER_ALLOW_APPROX_JOIN_AT）", reason="member_no_time")
                    return {"checked": 1, "synced": 0, "reason": "member_no_time"}
        elif mi.get("error"):
            _defer_join_sync(lease=lease, message=f"拉取 members 失败：{mi.get('error')}", reason="member_error")
            if record_events:
                db.add_member_lease_event(
                    email=target,
                    action="sync_member_error",
                    from_team=team_name,
                    to_team=None,
                    message=f"拉取 members 失败：{mi.get('error')}",
                )

    if not join_at:
        if record_events:
            db.add_member_lease_event(
                email=target,
                action="sync_not_joined",
                from_team=team_name,
                to_team=None,
                message="未在 invites(accepted/completed) 或 members 中找到已加入证据",
            )
        _defer_join_sync(lease=lease, message="未在 invites(accepted/completed) 或 members 中找到已加入证据", reason="not_joined")
        return {"checked": 1, "synced": 0, "reason": "not_joined"}

    expires_at = _expires_at_for_new_term(join_at)
    db.update_member_lease_joined(email=target, joined_at=join_at, expires_at=expires_at, from_team=team_name)
    return {"checked": 1, "synced": 1, "reason": "synced"}


def sync_joined_leases_once(*, limit: int = 50) -> int:
    """
    管理后台手动触发：同步 pending 的 joined_at。
    返回本次成功同步的条数（粗略统计）。
    """
    result = _sync_joined_leases(limit=limit, include_not_due=True, record_events=True)
    return int((result or {}).get("synced") or 0)


def sync_joined_leases_once_detailed(*, limit: int = 50) -> dict:
    result = _sync_joined_leases(limit=limit, include_not_due=True, record_events=True)
    return {k: int(v or 0) for k, v in (result or {}).items()}


def sync_joined_lease_for_email_once_detailed(email: str) -> dict:
    """
    管理后台手动触发：只同步指定邮箱的 join_at（并记录事件）。
    """
    try:
        result = _sync_joined_lease_for_email((email or "").strip().lower(), record_events=True)
    except Exception:
        result = {}
    return {k: int(v or 0) if isinstance(v, (int, float, bool)) else v for k, v in (result or {}).items()}


def run_transfer_for_email(email: str) -> dict:
    """
    管理后台手动触发：只执行指定邮箱的一次到期转移（不强制到期）。
    返回：{success, moved, message}
    """
    target = (email or "").strip().lower()
    if not target:
        return {"success": False, "moved": 0, "message": "email 不能为空"}

    # 只同步该邮箱的 join_at（避免扫全表导致卡顿）
    try:
        _sync_joined_lease_for_email(target, record_events=False)
    except Exception:
        pass

    lease = db.get_member_lease(target)
    if not lease:
        return {"success": False, "moved": 0, "message": "租约不存在"}

    if (lease.get("status") or "").strip() == "pending":
        hint = '仍未写入 joined_at（pending），不会参与到期转移；请先"同步加入时间"/点"近似加入"/或手动录入 joined_at。'
        return {"success": True, "moved": 0, "message": hint, "data": {"status": "pending"}}

    ok = _process_transfer_for_lease(lease, only_if_due=True)
    if ok:
        return {"success": True, "moved": 1, "message": "已发送新 Team 邀请（请看事件）"}

    # 更明确的提示：未到期 vs 转移失败
    try:
        exp = lease.get("expires_at")
        if isinstance(exp, str) and exp:
            exp_dt = datetime.fromisoformat(exp)
            if exp_dt > datetime.now():
                return {"success": True, "moved": 0, "message": f"未到期：expires_at={exp_dt.isoformat(sep=' ', timespec='seconds')}", "data": {"expires_at": exp_dt.isoformat()}}
    except Exception:
        pass
    return {"success": True, "moved": 0, "message": "未转移：可能未到期或转移失败（请看事件/最后错误）"}


def force_transfer_for_email(email: str, *, reason: str = "") -> dict:
    """
    强制换车：不检查到期时间，直接转移到新 Team。
    用于质保换车场景。
    返回：{success, moved, message, new_team}
    """
    target = (email or "").strip().lower()
    if not target:
        return {"success": False, "moved": 0, "message": "email 不能为空"}

    lease = db.get_member_lease(target)
    if not lease:
        return {"success": False, "moved": 0, "message": "租约不存在"}

    current_team_name = lease.get("team_name")

    # 记录换车原因
    db.add_member_lease_event(
        email=target,
        action="transfer_request",
        from_team=current_team_name,
        to_team=None,
        message=reason or "用户申请换车"
    )

    # 强制转移（不检查到期时间）
    ok, new_team = _process_transfer_for_lease_force(lease)

    if ok:
        return {
            "success": True,
            "moved": 1,
            "message": f"已从 {current_team_name} 换车到 {new_team}",
            "new_team": new_team
        }
    else:
        return {
            "success": False,
            "moved": 0,
            "message": "换车失败：没有可用的新 Team 或转移过程出错"
        }


def _process_transfer_for_lease_force(lease: dict) -> tuple:
    """强制执行转移，不检查到期时间。返回 (success, new_team_name)"""
    email = (lease.get("email") or "").strip().lower()
    if not email:
        return False, None

    if not db.mark_member_lease_transferring(email):
        return False, None

    current_team_name = lease.get("team_name")
    current_account_id = lease.get("team_account_id")

    candidates = _pick_next_team(
        current_account_id=current_account_id,
        current_team_name=current_team_name,
        email=email,
    )

    if not candidates:
        msg = "没有可用的新 Team（请至少配置 2 个 Team）"
        db.update_member_lease_transfer_failure(
            email=email,
            message=msg,
            next_attempt_at=_next_attempt_time(int(lease.get("attempts") or 0))
        )
        db.add_member_lease_event(
            email=email,
            action="transfer_failed",
            from_team=current_team_name,
            to_team=None,
            message=msg
        )
        return False, None

    # 尝试转移到候选 Team
    for team_cfg in candidates:
        new_team_name = team_cfg.get("name") or team_cfg.get("team_name") or "unknown"
        new_account_id = team_cfg.get("account_id")

        # 改进的席位检查
        try:
            stats = get_team_stats(new_team_name)
            total = stats.get("total", 0)
            used = stats.get("used", 0)
            pending = stats.get("pending", 0)
            available = total - used - pending

            if available < 1:
                log.info(f"跳过 Team {new_team_name}: 无可用席位（总:{total}, 已用:{used}, 待定:{pending}）")
                continue
        except Exception as e:
            log.warning(f"获取 Team {new_team_name} 席位信息失败: {e}")
            continue

        # 先从旧 Team 移除
        try:
            old_cfg = config.resolve_team(current_team_name)
            if old_cfg:
                from team_service import remove_member_by_email
                remove_member_by_email(old_cfg, email)
        except Exception as rm_err:
            log.warning(f"从旧 Team 移除失败（继续尝试邀请新 Team）: {rm_err}")

        # 邀请到新 Team
        try:
            from team_service import batch_invite_to_team
            result = batch_invite_to_team([email], team_cfg)
            if email in result.get("success", []):
                # 更新租约
                now = datetime.now()
                term_months = int(os.getenv("AUTO_TRANSFER_TERM_MONTHS", "1") or 1)
                from date_utils import add_months_same_day
                expires_at = add_months_same_day(now, max(1, min(24, term_months)))

                db.update_member_lease_transfer_success(
                    email=email,
                    new_team_name=new_team_name,
                    new_team_account_id=new_account_id,
                    invited_at=now,
                    expires_at=expires_at,
                )

                db.add_member_lease_event(
                    email=email,
                    action="transferred",
                    from_team=current_team_name,
                    to_team=new_team_name,
                    message=f"质保换车成功，新到期日 {expires_at.date().isoformat()}"
                )

                return True, new_team_name
        except Exception as inv_err:
            log.warning(f"邀请到新 Team {new_team_name} 失败: {inv_err}")
            continue

    # 所有候选都失败
    msg = "所有候选 Team 邀请均失败"
    db.update_member_lease_transfer_failure(
        email=email,
        message=msg,
        next_attempt_at=_next_attempt_time(int(lease.get("attempts") or 0))
    )
    db.add_member_lease_event(
        email=email,
        action="transfer_failed",
        from_team=current_team_name,
        to_team=None,
        message=msg
    )
    return False, None


def _process_transfer_for_lease(lease: dict, *, only_if_due: bool = True) -> bool:
    email = (lease.get("email") or "").strip().lower()
    if not email:
        return False

    # 未同步 joined_at 不参与到期转移
    if (lease.get("status") or "").strip() == "pending":
        return False

    # 检查是否超过最大重试次数
    attempts = int(lease.get("attempts") or 0)
    if attempts >= MAX_TRANSFER_ATTEMPTS:
        msg = f"已达到最大重试次数 ({MAX_TRANSFER_ATTEMPTS})，标记为失败"
        db.update_member_lease_status(email, "failed")
        db.add_member_lease_event(
            email=email,
            action="transfer_failed",
            from_team=lease.get("team_name"),
            to_team=None,
            message=msg
        )
        log.warning(f"转移失败（超过最大重试次数）: {email}", icon="warning")
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
        db.update_member_lease_transfer_failure(email=email, message=msg, next_attempt_at=_next_attempt_time(attempts))
        db.add_member_lease_event(email=email, action="transfer_failed", from_team=current_team_name, to_team=None, message=msg)
        return False

    transferred = False
    last_err = ""

    kick_old = (
        env_bool("AUTO_TRANSFER_AUTO_LEAVE_OLD_TEAM", False)
        or env_bool("AUTO_TRANSFER_KICK_OLD_TEAM", False)
    )
    kicked_old = False

    for t in candidates:
        team_name = t.get("name") or ""
        account_id = t.get("account_id") or ""

        # 改进的席位检查：检查 available >= pending_invites + 1
        try:
            stats = get_team_stats(team_name)
            total = stats.get("total", 0)
            used = stats.get("used", 0)
            pending = stats.get("pending", 0)
            available = total - used - pending

            if available < 1:
                last_err = f"Team {team_name} 无可用席位（总:{total}, 已用:{used}, 待定:{pending}）"
                log.info(f"跳过 Team {team_name}: {last_err}")
                continue
        except Exception as e:
            last_err = f"获取 Team {team_name} 席位信息失败: {e}"
            log.warning(last_err)
            continue

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

        ok, msg = invite_single_email(email, t)
        if ok:
            now = datetime.now()
            expires_at = _expires_at_for_new_term(now)
            db.update_member_lease_transfer_success(
                email=email,
                new_team_name=team_name,
                new_team_account_id=account_id,
                invited_at=now,
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

    if not env_bool("AUTO_TRANSFER_ENABLED", False):
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
