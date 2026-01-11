"""
兑换码生成CLI工具
用于批量生成和管理兑换码
"""

import argparse
import csv
import secrets
import string
from datetime import datetime, timedelta
from typing import List, Optional
from database import db
from logger import log


class CodeGenerator:
    """兑换码生成器"""

    @staticmethod
    def generate_code(prefix: str = "TEAM", length: int = 12) -> str:
        """
        生成随机兑换码
        格式: PREFIX-XXXX-XXXX-XXXX
        """
        # 使用大写字母和数字 (排除易混淆的字符: 0, O, I, 1)
        chars = string.ascii_uppercase.replace("O", "").replace("I", "") + "23456789"

        # 生成随机字符串
        random_str = "".join(secrets.choice(chars) for _ in range(length))

        # 分段格式化
        parts = [prefix]
        for i in range(0, length, 4):
            parts.append(random_str[i : i + 4])

        return "-".join(parts)

    @staticmethod
    def generate_codes(
        team_name: str,
        count: int = 10,
        max_uses: int = 1,
        expires_days: Optional[int] = None,
        prefix: str = "TEAM",
        notes: Optional[str] = None,
        auto_transfer_enabled: bool = True,
    ) -> List[str]:
        """
        生成兑换码 (API friendly wrapper)

        Args:
            team_name: Team名称
            count: 生成数量
            max_uses: 每个码最大使用次数
            expires_days: 有效天数 (None表示永久有效)
            prefix: 兑换码前缀
            notes: 备注信息
            auto_transfer_enabled: 是否启用自动转移(默认True)

        Returns:
            生成的兑换码列表
        """
        return CodeGenerator.batch_generate(
            team_name=team_name,
            count=count,
            max_uses=max_uses,
            valid_days=expires_days,
            prefix=prefix,
            notes=notes,
            auto_transfer_enabled=auto_transfer_enabled,
        )

    @staticmethod
    def batch_generate(
        team_name: str,
        count: int = 10,
        max_uses: int = 1,
        valid_days: Optional[int] = None,
        prefix: str = "TEAM",
        notes: Optional[str] = None,
        auto_transfer_enabled: bool = True,
    ) -> List[str]:
        """
        批量生成兑换码并保存到数据库

        Args:
            team_name: Team名称
            count: 生成数量
            max_uses: 每个码最大使用次数
            valid_days: 有效天数 (None表示永久有效)
            prefix: 兑换码前缀
            notes: 备注信息
            auto_transfer_enabled: 是否启用自动转移(默认True)

        Returns:
            生成的兑换码列表
        """
        codes = []
        expires_at = None

        if valid_days:
            expires_at = datetime.now() + timedelta(days=valid_days)

        log.info(f"开始生成 {count} 个兑换码...")

        for i in range(count):
            # 生成唯一的兑换码
            while True:
                code = CodeGenerator.generate_code(prefix=prefix)
                # 检查是否已存在
                if not db.get_code(code):
                    break

            # 保存到数据库
            try:
                db.create_code(
                    code=code,
                    team_name=team_name,
                    max_uses=max_uses,
                    expires_at=expires_at,
                    notes=notes,
                    auto_transfer_enabled=auto_transfer_enabled,
                )
                codes.append(code)
                log.progress_inline(f"已生成: {i + 1}/{count}")
            except Exception as e:
                log.error(f"保存兑换码失败: {e}")

        log.progress_clear()
        log.info(f"成功生成 {len(codes)} 个兑换码", icon="success")

        return codes

    @staticmethod
    def export_to_csv(codes: List[str], filename: str = "redemption_codes.csv"):
        """导出兑换码到CSV文件"""
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["兑换码", "Team", "最大使用次数", "过期时间", "创建时间", "状态"])

            for code in codes:
                code_info = db.get_code(code)
                if code_info:
                    writer.writerow(
                        [
                            code_info["code"],
                            code_info["team_name"],
                            code_info["max_uses"],
                            code_info["expires_at"] or "永久有效",
                            code_info["created_at"],
                            code_info["status"],
                        ]
                    )

        log.info(f"✅ 兑换码已导出到: {filename}")

    @staticmethod
    def list_codes(team_name: Optional[str] = None, status: Optional[str] = None):
        """列出兑换码"""
        codes = db.list_codes(team_name=team_name, status=status)

        if not codes:
            log.info("暂无兑换码")
            return

        # 打印表头
        print(
            f"\n{'ID':<6} {'兑换码':<20} {'Team':<15} {'使用情况':<12} {'状态':<10} {'过期时间':<20}"
        )
        print("-" * 95)

        # 打印数据
        for code in codes:
            usage = f"{code['used_count']}/{code['max_uses']}"
            expires = code["expires_at"] or "永久"
            print(
                f"{code['id']:<6} {code['code']:<20} {code['team_name']:<15} "
                f"{usage:<12} {code['status']:<10} {expires:<20}"
            )

        print(f"\n共 {len(codes)} 个兑换码")

    @staticmethod
    def disable_code(code: str):
        """禁用兑换码"""
        if db.get_code(code):
            db.update_code_status(code, "disabled")
            log.info(f"✅ 兑换码 {code} 已禁用")
        else:
            log.error(f"兑换码 {code} 不存在")

    @staticmethod
    def enable_code(code: str):
        """启用兑换码"""
        if db.get_code(code):
            db.update_code_status(code, "active")
            log.info(f"✅ 兑换码 {code} 已启用")
        else:
            log.error(f"兑换码 {code} 不存在")


def main():
    parser = argparse.ArgumentParser(description="兑换码生成和管理工具")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # 生成兑换码命令
    generate_parser = subparsers.add_parser("generate", help="生成兑换码")
    generate_parser.add_argument(
        "--team", "-t", required=True, help="Team名称 (必需)"
    )
    generate_parser.add_argument(
        "--count", "-c", type=int, default=10, help="生成数量 (默认: 10)"
    )
    generate_parser.add_argument(
        "--max-uses", "-m", type=int, default=1, help="每个码最大使用次数 (默认: 1)"
    )
    generate_parser.add_argument(
        "--valid-days", "-v", type=int, help="有效天数 (不指定则永久有效)"
    )
    generate_parser.add_argument(
        "--prefix", "-p", default="TEAM", help="兑换码前缀 (默认: TEAM)"
    )
    generate_parser.add_argument("--notes", "-n", help="备注信息")
    generate_parser.add_argument(
        "--export", "-e", help="导出CSV文件路径 (例: codes.csv)"
    )

    # 列出兑换码命令
    list_parser = subparsers.add_parser("list", help="列出兑换码")
    list_parser.add_argument("--team", "-t", help="按Team筛选")
    list_parser.add_argument(
        "--status", "-s", choices=["active", "disabled", "expired"], help="按状态筛选"
    )

    # 禁用兑换码命令
    disable_parser = subparsers.add_parser("disable", help="禁用兑换码")
    disable_parser.add_argument("code", help="要禁用的兑换码")

    # 启用兑换码命令
    enable_parser = subparsers.add_parser("enable", help="启用兑换码")
    enable_parser.add_argument("code", help="要启用的兑换码")

    # 查看统计命令
    stats_parser = subparsers.add_parser("stats", help="查看统计信息")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # 执行命令
    if args.command == "generate":
        codes = CodeGenerator.batch_generate(
            team_name=args.team,
            count=args.count,
            max_uses=args.max_uses,
            valid_days=args.valid_days,
            prefix=args.prefix,
            notes=args.notes,
        )

        # 打印生成的兑换码
        print("\n生成的兑换码:")
        print("=" * 50)
        for i, code in enumerate(codes, 1):
            print(f"{i}. {code}")
        print("=" * 50)

        # 导出到CSV
        if args.export:
            CodeGenerator.export_to_csv(codes, args.export)

    elif args.command == "list":
        CodeGenerator.list_codes(team_name=args.team, status=args.status)

    elif args.command == "disable":
        CodeGenerator.disable_code(args.code)

    elif args.command == "enable":
        CodeGenerator.enable_code(args.code)

    elif args.command == "stats":
        stats = db.get_dashboard_stats()
        print("\n📊 兑换码系统统计")
        print("=" * 50)
        print(f"总兑换码数: {stats['total_codes']}")
        print(f"激活的兑换码: {stats['active_codes']}")
        print(f"总兑换次数: {stats['total_redemptions']}")
        print(f"成功兑换次数: {stats['successful_redemptions']}")
        print(f"今日兑换次数: {stats['today_redemptions']}")
        print("=" * 50)


if __name__ == "__main__":
    main()
