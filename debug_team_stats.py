#!/usr/bin/env python3
"""
Team 统计调试脚本
用于诊断 Team 统计显示问题
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from database import db
from team_manager import team_manager
import config
from logger import log

def debug_team_stats():
    """调试 Team 统计"""
    print("=" * 80)
    print("Team 统计调试信息")
    print("=" * 80)

    # 1. 检查配置文件
    print("\n1. 配置文件检查:")
    print(f"   CONFIG_FILE: {config.CONFIG_FILE}")
    print(f"   CONFIG_FILE exists: {config.CONFIG_FILE.exists()}")
    print(f"   TEAM_JSON_FILE: {config.TEAM_JSON_FILE}")
    print(f"   TEAM_JSON_FILE exists: {config.TEAM_JSON_FILE.exists()}")
    print(f"   FALLBACK_CONFIG_FILE: {config.FALLBACK_CONFIG_FILE}")
    print(f"   FALLBACK_CONFIG_FILE exists: {config.FALLBACK_CONFIG_FILE.exists()}")
    print(f"   FALLBACK_TEAM_JSON_FILE: {config.FALLBACK_TEAM_JSON_FILE}")
    print(f"   FALLBACK_TEAM_JSON_FILE exists: {config.FALLBACK_TEAM_JSON_FILE.exists()}")

    # 2. 检查 Team 列表
    print("\n2. Team 列表 (team_manager.get_team_list()):")
    teams = team_manager.get_team_list()
    print(f"   Team 数量: {len(teams)}")
    for team in teams:
        print(f"   - Team {team.get('index')}: {team.get('name')}")
        print(f"     account_id: {team.get('account_id')}")
        print(f"     email: {team.get('email')}")
        print(f"     has_token: {team.get('has_token')}")

    # 3. 检查 config.TEAMS
    print("\n3. config.TEAMS:")
    print(f"   TEAMS 数量: {len(config.TEAMS)}")
    for idx, team in enumerate(config.TEAMS):
        print(f"   - Team {idx}: {team.get('name')}")
        print(f"     account_id: {team.get('account_id')}")
        print(f"     token: {'***' if team.get('token') else 'None'}")

    # 4. 检查数据库统计
    print("\n4. 数据库统计 (db.list_team_stats()):")
    raw_stats = db.list_team_stats()
    print(f"   统计记录数量: {len(raw_stats)}")
    for stat in raw_stats:
        print(f"   - team_name: {stat.get('team_name')}")
        print(f"     total_seats: {stat.get('total_seats')}")
        print(f"     used_seats: {stat.get('used_seats')}")
        print(f"     pending_invites: {stat.get('pending_invites')}")
        print(f"     available_seats: {stat.get('available_seats')}")

    # 5. 测试 resolve_team
    print("\n5. 测试 config.resolve_team():")
    for stat in raw_stats:
        team_name = stat.get('team_name')
        resolved = config.resolve_team(team_name)
        print(f"   - resolve_team('{team_name}'): {resolved.get('name') if resolved else 'None'}")

    # 6. 测试 _team_index_from_any_name
    print("\n6. 测试 _team_index_from_any_name():")
    from web_server import _team_index_from_any_name
    for stat in raw_stats:
        team_name = stat.get('team_name')
        idx = _team_index_from_any_name(team_name)
        print(f"   - _team_index_from_any_name('{team_name}'): {idx}")

    # 7. 检查兑换码
    print("\n7. 兑换码统计:")
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT team_name, COUNT(*) as count
                FROM redemption_codes
                WHERE status != 'deleted'
                GROUP BY team_name
            """)
            for row in cursor.fetchall():
                print(f"   - {row['team_name']}: {row['count']} 个兑换码")
    except Exception as e:
        print(f"   错误: {e}")

    # 8. 检查兑换记录
    print("\n8. 兑换记录统计:")
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT team_name, COUNT(*) as count
                FROM redemptions
                GROUP BY team_name
            """)
            for row in cursor.fetchall():
                print(f"   - {row['team_name']}: {row['count']} 次兑换")
    except Exception as e:
        print(f"   错误: {e}")

    print("\n" + "=" * 80)
    print("调试完成")
    print("=" * 80)

if __name__ == "__main__":
    debug_team_stats()
