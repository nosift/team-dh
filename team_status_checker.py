"""
Team 状态定期检测模块
定期检测所有 Team 的状态（Token 是否有效）并更新到数据库
"""

import threading
import time
from datetime import datetime
from logger import log
from database import db


class TeamStatusChecker:
    """Team 状态检测器"""

    def __init__(self):
        self._worker_started = False

    def check_all_teams(self):
        """检测所有 Team 的状态"""
        try:
            from team_manager import team_manager
            from team_service import check_team_status
            import config

            teams = team_manager.get_team_list()
            checked_count = 0
            active_count = 0
            inactive_count = 0

            log.info(f"开始检测 {len(teams)} 个 Team 的状态", icon="check")

            for team_info in teams:
                team_name = team_info["name"]
                idx = team_info.get("index")

                # 获取 Team 配置
                team_config = None
                if isinstance(idx, int) and 0 <= idx < len(config.TEAMS):
                    team_config = config.TEAMS[idx]
                if not team_config:
                    team_config = config.resolve_team(team_name)

                if not team_config:
                    log.warning(f"Team {team_name} 配置不存在，跳过检测")
                    continue

                # 检测状态
                try:
                    status = check_team_status(team_config)
                    is_active = status.get("active", False)
                    error_msg = status.get("error")

                    # 更新数据库
                    db.update_team_status(
                        team_name=team_name,
                        is_active=is_active,
                        status_error=error_msg,
                        last_checked_at=datetime.now()
                    )

                    checked_count += 1
                    if is_active:
                        active_count += 1
                        log.info(f"Team {team_name}: 正常 ✓", icon="check")
                    else:
                        inactive_count += 1
                        log.warning(f"Team {team_name}: 停用 ✗ ({error_msg})", icon="warning")

                except Exception as e:
                    log.error(f"检测 Team {team_name} 状态失败: {e}")
                    continue

            log.info(
                f"Team 状态检测完成: 共 {checked_count} 个，正常 {active_count} 个，停用 {inactive_count} 个",
                icon="check"
            )

            return {
                "checked": checked_count,
                "active": active_count,
                "inactive": inactive_count
            }

        except Exception as e:
            log.error(f"检测 Team 状态失败: {e}")
            return {"checked": 0, "active": 0, "inactive": 0}

    def start_worker(self, interval: int = 10800):
        """启动后台检测线程

        Args:
            interval: 检测间隔（秒），默认 10800 秒（3 小时）
        """
        if self._worker_started:
            return

        self._worker_started = True

        def _worker():
            log.info(f"Team 状态检测后台任务已启动（间隔: {interval // 3600} 小时）", icon="rocket")

            # 启动后立即执行一次检测
            time.sleep(10)  # 等待 10 秒让服务器完全启动
            self.check_all_teams()

            # 定期检测
            while True:
                try:
                    time.sleep(interval)
                    self.check_all_teams()
                except Exception as e:
                    log.error(f"Team 状态检测循环出错: {e}")
                    time.sleep(60)  # 出错后等待 1 分钟再继续

        thread = threading.Thread(target=_worker, daemon=True, name="TeamStatusChecker")
        thread.start()


# 全局实例
team_status_checker = TeamStatusChecker()


def start_team_status_checker(interval: int = 10800):
    """启动 Team 状态检测后台任务

    Args:
        interval: 检测间隔（秒），默认 10800 秒（3 小时）
    """
    team_status_checker.start_worker(interval=interval)
