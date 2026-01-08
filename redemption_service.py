"""
兑换服务模块
处理兑换码兑换的核心业务逻辑
"""

from datetime import datetime
from typing import Dict, Any, Optional
import uuid
from database import db
from team_service import batch_invite_to_team, get_team_stats
from logger import log
import config
from date_utils import add_months_same_day
import os


class RedemptionService:
    """兑换服务类"""

    @staticmethod
    def redeem(
        code: str, email: str, ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        执行兑换

        Args:
            code: 兑换码
            email: 用户邮箱
            ip_address: 用户IP地址 (可选)

        Returns:
            兑换结果字典
        """
        code = (code or "").strip().upper()
        email = (email or "").strip().lower()

        lock_id: str | None = None
        reserved = False

        try:
            # 1. 验证邮箱格式
            if not RedemptionService._validate_email(email):
                return {
                    "success": False,
                    "error": "邮箱格式无效",
                    "code": "INVALID_EMAIL",
                }

            # 2. 检查IP限流
            rate_limit = config.get("redemption.rate_limit_per_hour", 10)
            if ip_address and db.count_ip_redemptions(ip_address) >= rate_limit:
                return {
                    "success": False,
                    "error": f"操作过于频繁，请1小时后再试 (限制: {rate_limit}次/小时)",
                    "code": "RATE_LIMIT",
                }

            # 3. 检查邮箱是否已兑换
            if db.check_email_redeemed(email):
                return {
                    "success": False,
                    "error": "该邮箱已经兑换过席位",
                    "code": "EMAIL_ALREADY_REDEEMED",
                }

            # 4. 预占兑换码（数据库级并发锁）
            lock_id = uuid.uuid4().hex
            lock_seconds = int(config.get("redemption.code_lock_seconds", 120) or 120)
            ok, message, code_info = db.reserve_code(code, lock_by=lock_id, lock_seconds=lock_seconds)
            if not ok or not code_info:
                return {"success": False, "error": message, "code": "INVALID_CODE"}
            reserved = True

            team_name = code_info["team_name"]

            # 5. 检查Team席位
            seat_check = RedemptionService._check_team_seats(team_name)
            if not seat_check["available"]:
                db.release_reserved_code(code, lock_by=lock_id)
                reserved = False
                return {
                    "success": False,
                    "error": seat_check["message"],
                    "code": "NO_SEATS",
                }

            # 6. 创建兑换记录
            redemption_id = db.create_redemption(
                code_id=code_info["id"],
                email=email,
                team_name=team_name,
                ip_address=ip_address,
            )

            # 7. 邀请用户到Team
            db.update_redemption_status(redemption_id, "inviting")
            log.info(f"正在邀请 {email} 到 Team {team_name}...")
            invite_result = RedemptionService._invite_to_team(email, team_name)

            if invite_result["success"]:
                # 8. 更新兑换记录状态为成功
                db.update_redemption_status(redemption_id, "success")

                # 9. 消费预占的兑换码（增加使用次数并释放锁）
                if not db.consume_reserved_code(code, lock_by=lock_id):
                    # 兜底：避免因锁过期导致未计数
                    db.increment_code_usage(code)
                    db.release_reserved_code(code, lock_by=lock_id)
                reserved = False

                # 10. 更新Team统计
                RedemptionService._update_team_stats(team_name)

                # 11. 记录“成员租约”（用于按月到期自动转移到新 Team）
                try:
                    now = datetime.now()
                    team_cfg = config.resolve_team(team_name) or {}
                    team_account_id = team_cfg.get("account_id")
                    term_months = int(os.getenv("AUTO_TRANSFER_TERM_MONTHS", "1") or 1)
                    expires_at = add_months_same_day(now, max(1, min(24, term_months)))

                    existed = db.get_member_lease(email) is not None
                    db.upsert_member_lease(
                        email=email,
                        team_name=team_name,
                        team_account_id=team_account_id,
                        start_at=now,
                        expires_at=expires_at,
                    )
                    if not existed:
                        db.add_member_lease_event(
                            email=email,
                            action="created",
                            from_team=None,
                            to_team=team_name,
                            message=f"创建租约：到期 {expires_at.date().isoformat()}",
                        )
                except Exception as e:
                    log.warning(f"写入成员租约失败（不影响兑换流程）: {e}")

                log.info(f"{email} 兑换成功", icon="success")

                return {
                    "success": True,
                    "message": f"兑换成功！邀请邮件已发送到 {email}",
                    "data": {
                        "email": email,
                        "team": team_name,
                        "redeemed_at": datetime.now().isoformat(),
                    },
                }
            else:
                # 邀请失败
                db.update_redemption_status(
                    redemption_id, "failed", invite_result["error"]
                )
                db.release_reserved_code(code, lock_by=lock_id)
                reserved = False

                log.error(f"{email} 邀请失败: {invite_result['error']}")

                return {
                    "success": False,
                    "error": f"邀请失败: {invite_result['error']}",
                    "code": "INVITE_FAILED",
                }

        except Exception as e:
            log.error(f"兑换过程出错: {e}")
            return {
                "success": False,
                "error": f"系统错误: {str(e)}",
                "code": "SYSTEM_ERROR",
            }
        finally:
            if reserved and lock_id:
                try:
                    db.release_reserved_code(code, lock_by=lock_id)
                except Exception:
                    pass

    @staticmethod
    def verify_code_info(code: str) -> Dict[str, Any]:
        """
        验证兑换码并返回详细信息

        Returns:
            验证结果字典
        """
        valid, message = db.verify_code(code)

        if not valid:
            return {"valid": False, "error": message}

        code_info = db.get_code(code)

        return {
            "valid": True,
            "code": code_info["code"],
            "team": code_info["team_name"],
            "max_uses": code_info["max_uses"],
            "used_count": code_info["used_count"],
            "remaining_uses": code_info["max_uses"] - code_info["used_count"],
            "expires_at": code_info["expires_at"],
            "status": code_info["status"],
        }

    @staticmethod
    def _validate_email(email: str) -> bool:
        """验证邮箱格式"""
        import re

        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return re.match(pattern, email) is not None

    @staticmethod
    def _check_team_seats(team_name: str) -> Dict[str, Any]:
        """检查Team是否有可用席位"""
        try:
            # 从config获取team配置
            team_config = config.resolve_team(team_name)

            if not team_config:
                return {"available": False, "message": f"Team {team_name} 不存在"}

            # 获取Team统计信息
            stats = get_team_stats(team_config)

            if not stats:
                return {"available": False, "message": "无法获取Team信息"}

            # 计算可用席位 = 总席位 - 已使用 - 待处理邀请
            seats_entitled = stats.get("seats_entitled", 0)
            seats_in_use = stats.get("seats_in_use", 0)
            pending_invites = stats.get("pending_invites", 0)
            available = seats_entitled - seats_in_use - pending_invites

            if available > 0:
                return {
                    "available": True,
                    "seats": available,
                    "message": f"可用席位: {available}",
                }
            else:
                return {
                    "available": False,
                    "message": f"Team席位已满 (使用: {seats_in_use}/{seats_entitled}, 待处理: {pending_invites})",
                }

        except Exception as e:
            log.error(f"检查Team席位失败: {e}")
            return {"available": False, "message": f"检查席位失败: {str(e)}"}

    @staticmethod
    def _invite_to_team(email: str, team_name: str) -> Dict[str, Any]:
        """邀请用户到Team"""
        try:
            # 获取team配置
            team_config = config.resolve_team(team_name)

            if not team_config:
                return {"success": False, "error": f"Team {team_name} 配置不存在"}

            # 调用batch_invite_to_team (支持单个邮箱)
            result = batch_invite_to_team([email], team_config)

            if email in result.get("success", []):
                return {"success": True, "message": "邀请成功"}
            elif email in result.get("failed", {}):
                error = result["failed"][email]
                return {"success": False, "error": error}
            else:
                return {"success": False, "error": "未知错误"}

        except Exception as e:
            log.error(f"邀请到Team失败: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def _update_team_stats(team_name: str):
        """更新Team统计信息到数据库"""
        try:
            # 获取team配置
            team_config = config.resolve_team(team_name)

            if not team_config:
                return

            # 获取最新统计
            stats = get_team_stats(team_config)

            if stats:
                db.update_team_stats(
                    team_name=team_name,
                    total_seats=stats["seats_entitled"],
                    used_seats=stats["seats_in_use"],
                    pending_invites=stats["pending_invites"],
                )
                log.info(f"Team {team_name} 统计已更新", icon="success")

        except Exception as e:
            log.error(f"更新Team统计失败: {e}")


# 单例实例
redemption_service = RedemptionService()


if __name__ == "__main__":
    # 测试兑换服务
    print("测试兑换服务...")

    # 测试邮箱验证
    print("\n测试邮箱验证:")
    print(f"test@example.com: {RedemptionService._validate_email('test@example.com')}")
    print(f"invalid-email: {RedemptionService._validate_email('invalid-email')}")

    # 测试验证兑换码信息
    print("\n测试验证兑换码:")
    result = RedemptionService.verify_code_info("TEST-DEMO-1234")
    print(f"结果: {result}")

    print("\n✅ 测试完成")
