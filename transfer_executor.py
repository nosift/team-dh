"""
转移执行器 - 负责执行具体的 Team 转移操作
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

import config
from database import db
from date_utils import add_months_same_day
from join_sync_service import JoinSyncService
from lease_models import LeaseAction
from logger import log
from redemption_service import RedemptionService
from team_service import invite_single_email, remove_member_by_email


def _env_bool(name: str, default: bool = False) -> bool:
    """解析环境变量为布尔值"""
    raw = os.getenv(name)
    if raw is None:
        return default
    v = raw.strip().lower()
    if v in {"1", "true", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _pick_next_team(*, current_account_id: str | None, current_team_name: str | None, email: str) -> list[dict]:
    """选择下一个 Team (轮询策略)"""
    teams = [
        t
        for t in (config.TEAMS or [])
        if (t.get("auth_token") or "").strip() and (t.get("account_id") or "").strip()
    ]
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
    """计算下次重试时间 (指数退避)"""
    base = 300  # 5分钟
    secs = min(24 * 3600, base * (2 ** max(0, min(12, int(attempts or 0)))))
    return datetime.now() + timedelta(seconds=secs)


def _expires_at_for_new_term(now: datetime) -> datetime:
    """计算新租期的到期时间"""
    term_months = int(os.getenv("AUTO_TRANSFER_TERM_MONTHS", "1") or 1)
    term_months = max(1, min(24, term_months))
    return add_months_same_day(now, term_months)


class TransferExecutor:
    """转移执行器 - 负责执行单个租约的转移"""

    @staticmethod
    def execute(lease: dict, *, only_if_due: bool = True) -> bool:
        """执行转移操作

        Args:
            lease: 租约记录
            only_if_due: 是否只转移已到期的

        Returns:
            bool: 是否转移成功
        """
        email = (lease.get("email") or "").strip().lower()
        if not email:
            return False

        # 只转移 active 状态且已加入的租约
        if (lease.get("status") or "").strip() != "active":
            return False

        if not lease.get("joined_at"):
            return False

        # 检查是否到期
        if only_if_due:
            try:
                exp = lease.get("expires_at")
                if isinstance(exp, str) and exp:
                    exp_dt = datetime.fromisoformat(exp)
                    if exp_dt > datetime.now():
                        return False
            except Exception:
                return False

        # 标记为转移中
        if not db.mark_member_lease_transferring(email):
            return False

        current_team_name = lease.get("team_name")
        current_account_id = lease.get("team_account_id")

        # 选择候选 Team
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
                next_attempt_at=_next_attempt_time(int(lease.get("attempts") or 0)),
            )
            db.add_member_lease_event(
                email=email,
                action=LeaseAction.TRANSFER_FAILED,
                from_team=current_team_name,
                to_team=None,
                message=msg,
            )
            return False

        # 是否自动退出旧 Team
        kick_old = _env_bool("AUTO_TRANSFER_AUTO_LEAVE_OLD_TEAM", False) or _env_bool(
            "AUTO_TRANSFER_KICK_OLD_TEAM", False
        )
        kicked_old = False
        transferred = False
        last_err = ""

        # 尝试转移到候选 Team
        for t in candidates:
            team_name = t.get("name") or ""
            account_id = t.get("account_id") or ""

            # 先退出旧 Team (如果配置了)
            if kick_old and (not kicked_old) and current_team_name:
                old_cfg = config.resolve_team(current_team_name) or {}
                if not old_cfg:
                    last_err = f"旧 Team 配置不存在: {current_team_name}"
                    break
                ok_kick, kick_msg = remove_member_by_email(old_cfg, email)
                if not ok_kick:
                    last_err = f"退出旧 Team 失败: {kick_msg}"
                    db.add_member_lease_event(
                        email=email,
                        action=LeaseAction.LEAVE_OLD_FAILED,
                        from_team=current_team_name,
                        to_team=None,
                        message=kick_msg,
                    )
                    break
                kicked_old = True
                db.add_member_lease_event(
                    email=email,
                    action=LeaseAction.LEFT_OLD_TEAM,
                    from_team=current_team_name,
                    to_team=None,
                    message="已退出旧 Team",
                )

            # 检查新 Team 席位
            seat_check = RedemptionService._check_team_seats(team_name)
            if not seat_check.get("available"):
                last_err = seat_check.get("message") or "无可用席位"
                continue

            # 邀请到新 Team
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
                    action=LeaseAction.TRANSFERRED,
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
            db.add_member_lease_event(
                email=email,
                action=LeaseAction.TRANSFER_FAILED,
                from_team=current_team_name,
                to_team=None,
                message=msg,
            )
            return False

        return True
