'''
转移调度器 - 负责定时任务和批量转移调度
'''

from __future__ import annotations

import os
import threading
import time
import uuid

from config import env_bool
from database import db
from join_sync_service import JoinSyncService
from logger import log
from transfer_executor import TransferExecutor


class TransferScheduler:
    '''转移调度器 - 负责后台定时任务'''

    _worker_started = False

    @staticmethod
    def run_once(*, limit: int = 20) -> int:
        '''执行一轮到期转移

        Returns:
            int: 成功转移的人数
        '''
        lock_by = uuid.uuid4().hex
        if not db.acquire_lock('auto_transfer_monthly', lock_by=lock_by, lock_seconds=90):
            return 0

        moved = 0
        try:
            # 先同步加入时间
            JoinSyncService.sync_batch(limit=50, include_not_due=False, record_events=False)

            # 获取到期租约
            due = db.list_due_member_leases(limit=limit)
            if not due:
                return 0

            # 逐个转移
            for lease in due:
                if TransferExecutor.execute(lease, only_if_due=True):
                    moved += 1

            return moved
        finally:
            db.release_lock('auto_transfer_monthly', lock_by=lock_by)

    @staticmethod
    def run_for_email(email: str) -> dict:
        '''手动触发单个邮箱的转移

        Returns:
            dict: {success: bool, moved: int, message: str}
        '''
        target = (email or '').strip().lower()
        if not target:
            return {'success': False, 'moved': 0, 'message': 'email 不能为空'}

        # 先同步该邮箱的加入时间
        try:
            JoinSyncService.sync_single_email(target, record_events=False)
        except Exception:
            pass

        lease = db.get_member_lease(target)
        if not lease:
            return {'success': False, 'moved': 0, 'message': '租约不存在'}

        if (lease.get('status') or '').strip() == 'pending':
            hint = "仍未写入 joined_at（pending），不会参与到期转移；请先同步加入时间/点近似加入/或手动录入 joined_at。"
            return {'success': True, 'moved': 0, 'message': hint, 'data': {'status': 'pending'}}

        ok = TransferExecutor.execute(lease, only_if_due=True)
        if ok:
            return {'success': True, 'moved': 1, 'message': '已发送新 Team 邀请（请看事件）'}

        # 未转移：检查原因
        try:
            from datetime import datetime

            exp = lease.get('expires_at')
            if isinstance(exp, str) and exp:
                exp_dt = datetime.fromisoformat(exp)
                if exp_dt > datetime.now():
                    return {
                        'success': True,
                        'moved': 0,
                        'message': f"未到期：expires_at={exp_dt.isoformat(sep=' ', timespec='seconds')}",
                        'data': {'expires_at': exp_dt.isoformat()},
                    }
        except Exception:
            pass
        return {'success': True, 'moved': 0, 'message': '未转移：可能未到期或转移失败（请看事件/最后错误）'}

    @staticmethod
    def sync_joined_leases_once(*, limit: int = 50) -> int:
        '''手动触发批量同步加入时间

        Returns:
            int: 成功同步的数量
        '''
        result = JoinSyncService.sync_batch(limit=limit, include_not_due=True, record_events=True)
        return int((result or {}).get('synced') or 0)

    @staticmethod
    def sync_joined_leases_once_detailed(*, limit: int = 50) -> dict:
        '''手动触发批量同步加入时间(详细统计)

        Returns:
            dict: {checked, synced, invite_errors, ...}
        '''
        result = JoinSyncService.sync_batch(limit=limit, include_not_due=True, record_events=True)
        return {k: int(v or 0) for k, v in (result or {}).items()}

    @staticmethod
    def sync_joined_lease_for_email_once_detailed(email: str) -> dict:
        '''手动触发单个邮箱的同步加入时间(详细统计)

        Returns:
            dict: {checked, synced, reason}
        '''
        try:
            result = JoinSyncService.sync_single_email((email or '').strip().lower(), record_events=True)
        except Exception:
            result = {}
        return {k: int(v or 0) if isinstance(v, (int, float, bool)) else v for k, v in (result or {}).items()}

    @staticmethod
    def start_worker():
        '''启动后台定时任务线程'''
        if TransferScheduler._worker_started:
            return
        TransferScheduler._worker_started = True

        if not env_bool('AUTO_TRANSFER_ENABLED', False):
            log.info('AUTO_TRANSFER_ENABLED=false，自动转移功能未启用', icon='info')
            return

        poll_seconds = int(os.getenv('AUTO_TRANSFER_POLL_SECONDS', '300') or 300)
        poll_seconds = max(30, poll_seconds)

        def loop():
            log.info(f'自动转移线程已启动（每 {poll_seconds}s 检查一次）', icon='start')
            while True:
                try:
                    moved = TransferScheduler.run_once(limit=20)
                    if moved:
                        log.info(f'本轮自动转移完成: {moved} 人', icon='team')
                except Exception as e:
                    log.warning(f'自动转移任务异常: {e}')
                time.sleep(poll_seconds)

        t = threading.Thread(target=loop, name='auto-transfer', daemon=True)
        t.start()


# 导出兼容旧接口的函数
def run_transfer_once(*, limit: int = 20) -> int:
    '''兼容旧接口'''
    return TransferScheduler.run_once(limit=limit)


def run_transfer_for_email(email: str) -> dict:
    '''兼容旧接口'''
    return TransferScheduler.run_for_email(email)


def sync_joined_leases_once(*, limit: int = 50) -> int:
    '''兼容旧接口'''
    return TransferScheduler.sync_joined_leases_once(limit=limit)


def sync_joined_leases_once_detailed(*, limit: int = 50) -> dict:
    '''兼容旧接口'''
    return TransferScheduler.sync_joined_leases_once_detailed(limit=limit)


def sync_joined_lease_for_email_once_detailed(email: str) -> dict:
    '''兼容旧接口'''
    return TransferScheduler.sync_joined_lease_for_email_once_detailed(email)


def start_transfer_worker():
    '''兼容旧接口'''
    TransferScheduler.start_worker()
