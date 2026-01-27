'''
加入时间同步服务
负责同步用户实际加入 Team 的时间
'''

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import config
from config import env_bool
from database import db
from date_utils import add_months_same_day, parse_datetime_loose
from lease_models import LeaseAction, SyncReason
from logger import log
from team_service import get_invite_status_for_email, get_member_info_for_email


def _defer_join_sync_seconds(reason: SyncReason) -> int:
    '''根据失败原因返回延迟秒数'''
    delays = {
        SyncReason.MEMBER_NO_TIME: 24 * 3600,      # 24小时
        SyncReason.INVITE_NOT_ACCEPTED: 20 * 60,   # 20分钟
        SyncReason.INVITE_ERROR: 60 * 60,          # 1小时
        SyncReason.MEMBER_ERROR: 60 * 60,          # 1小时
        SyncReason.NOT_JOINED: 30 * 60,            # 30分钟
    }
    return delays.get(reason, 30 * 60)


def _defer_join_sync(*, lease: dict, message: str, reason: SyncReason):
    '''延迟下次同步尝试'''
    try:
        email = (lease.get('email') or '').strip().lower()
        if not email:
            return
        delay = _defer_join_sync_seconds(reason)
        next_at = datetime.now() + timedelta(seconds=delay)
        db.defer_member_lease_join_sync(email=email, next_attempt_at=next_at, last_error=message)
    except Exception:
        pass


def _expires_at_for_new_term(now: datetime) -> datetime:
    '''计算新租期的到期时间'''
    import os
    term_months = int(os.getenv('AUTO_TRANSFER_TERM_MONTHS', '1') or 1)
    term_months = max(1, min(24, term_months))
    return add_months_same_day(now, term_months)


class JoinSyncService:
    '''加入时间同步服务'''

    @staticmethod
    def sync_single_email(email: str, *, record_events: bool = True) -> dict:
        '''同步单个邮箱的加入时间

        Returns:
            dict: {checked: int, synced: int, reason: str}
        '''
        target = (email or '').strip().lower()
        if not target:
            return {'checked': 0, 'synced': 0, 'reason': 'empty_email'}

        lease = db.get_member_lease(target)
        if not lease:
            return {'checked': 0, 'synced': 0, 'reason': 'lease_not_found'}

        if (lease.get('status') or '').strip() != 'pending':
            return {'checked': 0, 'synced': 0, 'reason': 'not_pending'}

        team_name = (lease.get('team_name') or '').strip()
        team_cfg = config.resolve_team(team_name) or {}
        if not team_cfg:
            if record_events:
                db.add_member_lease_event(
                    email=target,
                    action=LeaseAction.SYNC_SKIP,
                    from_team=team_name or None,
                    to_team=None,
                    message='Team 配置不存在，无法同步 joined_at',
                )
            return {'checked': 1, 'synced': 0, 'reason': 'team_cfg_missing'}

        # 1) 优先从 invites 获取 accepted 时间
        joined_at = JoinSyncService._get_joined_at_from_invites(
            team_cfg, target, lease, record_events
        )

        # 2) 如果 invites 没有,从 members 兜底
        if not joined_at:
            joined_at = JoinSyncService._get_joined_at_from_members(
                team_cfg, target, lease, team_name, record_events
            )

        if not joined_at:
            if record_events:
                db.add_member_lease_event(
                    email=target,
                    action=LeaseAction.SYNC_NOT_JOINED,
                    from_team=team_name,
                    to_team=None,
                    message='未在 invites(accepted/completed) 或 members 中找到已加入证据',
                )
            _defer_join_sync(
                lease=lease,
                message='未在 invites(accepted/completed) 或 members 中找到已加入证据',
                reason=SyncReason.NOT_JOINED,
            )
            return {'checked': 1, 'synced': 0, 'reason': 'not_joined'}

        # 3) 更新租约为 active 状态
        expires_at = _expires_at_for_new_term(joined_at)
        db.update_member_lease_joined(
            email=target, joined_at=joined_at, expires_at=expires_at, from_team=team_name
        )
        return {'checked': 1, 'synced': 1, 'reason': 'synced'}

    @staticmethod
    def _get_joined_at_from_invites(
        team_cfg: dict, email: str, lease: dict, record_events: bool
    ) -> Optional[datetime]:
        '''从 invites 获取加入时间'''
        try:
            inv = get_invite_status_for_email(team_cfg, email)
        except Exception as e:
            inv = {'found': False, 'error': str(e)}

        if inv.get('found'):
            status = (inv.get('status') or '').strip().lower()
            if status in {'accepted', 'completed', 'done'}:
                ts = inv.get('timestamp')
                if isinstance(ts, str) and ts:
                    try:
                        return parse_datetime_loose(ts)
                    except Exception:
                        pass
            else:
                _defer_join_sync(
                    lease=lease,
                    message=f"invites 状态={status or 'unknown'}，未达到 accepted/completed",
                    reason=SyncReason.INVITE_NOT_ACCEPTED,
                )
                if record_events:
                    db.add_member_lease_event(
                        email=email,
                        action=LeaseAction.SYNC_INVITE_STATUS,
                        from_team=lease.get('team_name'),
                        to_team=None,
                        message=f"invites 状态={status or 'unknown'}，未达到 accepted/completed",
                    )
        elif inv.get('error'):
            _defer_join_sync(
                lease=lease,
                message=f"拉取 invites 失败：{inv.get('error')}",
                reason=SyncReason.INVITE_ERROR,
            )
            if record_events:
                db.add_member_lease_event(
                    email=email,
                    action=LeaseAction.SYNC_INVITE_ERROR,
                    from_team=lease.get('team_name'),
                    to_team=None,
                    message=f"拉取 invites 失败：{inv.get('error')}",
                )

        return None

    @staticmethod
    def _get_joined_at_from_members(
        team_cfg: dict, email: str, lease: dict, team_name: str, record_events: bool
    ) -> Optional[datetime]:
        '''从 members 获取加入时间(兜底)'''
        try:
            mi = get_member_info_for_email(team_cfg, email)
        except Exception as e:
            mi = {'found': False, 'error': str(e)}

        if mi.get('found'):
            ts = mi.get('joined_at')
            if isinstance(ts, str) and ts:
                try:
                    return parse_datetime_loose(ts)
                except Exception:
                    pass

            # 成员列表没有时间字段,是否允许近似
            allow_approx = env_bool('AUTO_TRANSFER_ALLOW_APPROX_JOIN_AT', False)
            if allow_approx:
                joined_at = datetime.now()
                if record_events:
                    db.add_member_lease_event(
                        email=email,
                        action=LeaseAction.JOINED_FALLBACK,
                        from_team=team_name,
                        to_team=None,
                        message='成员列表未提供加入时间字段，已使用当前时间近似 joined_at（AUTO_TRANSFER_ALLOW_APPROX_JOIN_AT=true）',
                    )
                return joined_at
            else:
                if record_events:
                    db.add_member_lease_event(
                        email=email,
                        action=LeaseAction.SYNC_MEMBER_NO_TIME,
                        from_team=team_name,
                        to_team=None,
                        message="成员列表未提供加入时间字段，未写入 joined_at（保持 pending；可手动录入 joined_at / 在后台点'近似加入' / 或开启 AUTO_TRANSFER_ALLOW_APPROX_JOIN_AT）",
                    )
                _defer_join_sync(
                    lease=lease,
                    message='成员列表未提供加入时间字段，未写入 joined_at',
                    reason=SyncReason.MEMBER_NO_TIME,
                )
        elif mi.get('error'):
            _defer_join_sync(
                lease=lease,
                message=f"拉取 members 失败：{mi.get('error')}",
                reason=SyncReason.MEMBER_ERROR,
            )
            if record_events:
                db.add_member_lease_event(
                    email=email,
                    action=LeaseAction.SYNC_MEMBER_ERROR,
                    from_team=team_name,
                    to_team=None,
                    message=f"拉取 members 失败：{mi.get('error')}",
                )

        return None

    @staticmethod
    def sync_batch(*, limit: int = 50, include_not_due: bool = False, record_events: bool = True) -> dict:
        '''批量同步加入时间

        Returns:
            dict: {checked, synced, invite_errors, invite_not_accepted, member_errors, member_no_time, not_joined, skipped}
        '''
        rows = db.list_member_leases_pending_join_with_due(limit=limit, include_not_due=include_not_due)
        if not rows:
            return {
                'checked': 0,
                'synced': 0,
                'invite_errors': 0,
                'invite_not_accepted': 0,
                'member_errors': 0,
                'member_no_time': 0,
                'not_joined': 0,
                'skipped': 0,
            }

        stats = {
            'checked': 0,
            'synced': 0,
            'invite_errors': 0,
            'invite_not_accepted': 0,
            'member_errors': 0,
            'member_no_time': 0,
            'not_joined': 0,
            'skipped': 0,
        }

        for lease in rows:
            email = (lease.get('email') or '').strip().lower()
            if not email:
                stats['skipped'] += 1
                continue

            result = JoinSyncService.sync_single_email(email, record_events=record_events)
            stats['checked'] += result.get('checked', 0)
            stats['synced'] += result.get('synced', 0)

            reason = result.get('reason', '')
            if 'invite_error' in reason:
                stats['invite_errors'] += 1
            elif 'invite_not_accepted' in reason or 'invite_status' in reason:
                stats['invite_not_accepted'] += 1
            elif 'member_error' in reason:
                stats['member_errors'] += 1
            elif 'member_no_time' in reason:
                stats['member_no_time'] += 1
            elif 'not_joined' in reason:
                stats['not_joined'] += 1

        return stats
