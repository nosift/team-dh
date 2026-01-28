"""
异常转移检测模块
定期检查活跃租约的 Team 状态，如果 Team 不可用则触发转移
确保用户始终可以使用 Team，实现无感切换
"""

import threading
import time
from datetime import datetime
from logger import log
from database import db
from transfer_executor import TransferExecutor


class AbnormalTransferChecker:
    """异常转移检测器"""

    def __init__(self):
        self._worker_started = False

    def check_and_transfer_abnormal_leases(self):
        """检查并转移异常租约"""
        try:
            # 获取所有活跃的租约
            with db.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT * FROM member_leases
                    WHERE status = 'active' AND joined_at IS NOT NULL
                    ORDER BY email
                """)
                leases = [dict(row) for row in cursor.fetchall()]

            if not leases:
                log.info("没有活跃的租约需要检查")
                return {"checked": 0, "transferred": 0, "failed": 0}

            log.info(f"开始检查 {len(leases)} 个活跃租约的 Team 状态", icon="check")

            checked_count = 0
            transferred_count = 0
            failed_count = 0

            for lease in leases:
                email = lease.get('email', '')
                team_name = lease.get('team_name', '')

                if not email or not team_name:
                    continue

                # 检查 Team 状态
                team_status = db.get_team_status(team_name)

                # 如果没有状态信息，跳过（默认认为正常）
                if team_status is None:
                    checked_count += 1
                    continue

                is_active = team_status.get('is_active', 1)
                checked_count += 1

                # 如果 Team 状态正常，跳过
                if is_active:
                    continue

                # Team 不可用，触发异常转移
                status_error = team_status.get('status_error', '未知错误')
                log.warning(f"检测到异常租约: {email} 的 Team {team_name} 不可用 ({status_error})")

                # 记录异常事件
                db.add_member_lease_event(
                    email=email,
                    action="abnormal_detected",
                    from_team=team_name,
                    to_team=None,
                    message=f"检测到 Team 异常: {status_error}"
                )

                # 执行转移（不检查到期时间）
                try:
                    success = TransferExecutor.execute(lease, only_if_due=False)
                    if success:
                        transferred_count += 1
                        log.info(f"异常转移成功: {email} 从 {team_name} 转移到新 Team")
                    else:
                        failed_count += 1
                        log.warning(f"异常转移失败: {email}")
                except Exception as e:
                    failed_count += 1
                    log.error(f"异常转移出错: {email} - {e}")

            log.info(
                f"异常转移检查完成: 检查 {checked_count} 个，转移 {transferred_count} 个，失败 {failed_count} 个",
                icon="check"
            )

            return {
                "checked": checked_count,
                "transferred": transferred_count,
                "failed": failed_count
            }

        except Exception as e:
            log.error(f"异常转移检查失败: {e}")
            return {"checked": 0, "transferred": 0, "failed": 0}

    def start_worker(self, interval: int = 1800):
        """启动后台检测线程

        Args:
            interval: 检测间隔（秒），默认 1800 秒（30 分钟）
        """
        if self._worker_started:
            return

        self._worker_started = True

        def _worker():
            log.info(f"异常转移检测后台任务已启动（间隔: {interval // 60} 分钟）", icon="rocket")

            # 启动后等待 30 秒让服务器完全启动
            time.sleep(30)
            self.check_and_transfer_abnormal_leases()

            # 定期检测
            while True:
                try:
                    time.sleep(interval)
                    self.check_and_transfer_abnormal_leases()
                except Exception as e:
                    log.error(f"异常转移检测循环出错: {e}")
                    time.sleep(60)  # 出错后等待 1 分钟再继续

        thread = threading.Thread(target=_worker, daemon=True, name="AbnormalTransferChecker")
        thread.start()


# 全局实例
abnormal_transfer_checker = AbnormalTransferChecker()


def start_abnormal_transfer_checker(interval: int = 1800):
    """启动异常转移检测后台任务

    Args:
        interval: 检测间隔（秒），默认 1800 秒（30 分钟）
    """
    abnormal_transfer_checker.start_worker(interval=interval)
