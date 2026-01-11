"""
Team 管理服务
提供 Team 的增删改查功能
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from logger import log
import config


class TeamManager:
    """Team 管理类"""

    def __init__(self, team_file: str | None = None, config_file: str | None = None):
        self.team_file = Path(team_file) if team_file else Path(config.TEAM_JSON_FILE)
        self.config_file = Path(config_file) if config_file else Path(config.CONFIG_FILE)

    def load_teams(self) -> List[Dict[str, Any]]:
        """加载所有 Team"""
        if not self.team_file.exists():
            return []

        try:
            with open(self.team_file, "r", encoding="utf-8") as f:
                teams = json.load(f)
                return teams if isinstance(teams, list) else []
        except Exception as e:
            log.error(f"加载 Team 失败: {e}")
            return []

    def save_teams(self, teams: List[Dict[str, Any]], team_names: Optional[List[str]] = None) -> bool:
        """保存所有 Team"""
        try:
            self.team_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.team_file, "w", encoding="utf-8") as f:
                json.dump(teams, f, ensure_ascii=False, indent=2)

            # 同步更新 config.toml 中的 team_names
            self._update_config_team_names(teams, team_names=team_names)

            # 重新加载 config.TEAMS,使新Team立即可用
            try:
                import config
                config.reload_teams()
                log.info(f"配置已重新加载,当前有 {len(config.TEAMS)} 个Team", icon="success")
            except Exception as e:
                log.warning(f"重新加载配置失败: {e}")

            log.info(f"保存 {len(teams)} 个 Team 成功", icon="success")
            return True
        except Exception as e:
            log.error(f"保存 Team 失败: {e}")
            return False

    def get_team_list(self) -> List[Dict[str, Any]]:
        """获取 Team 列表(包含名称和基本信息)"""
        teams = self.load_teams()
        team_names = self._load_team_names()

        result = []
        for idx, team in enumerate(teams):
            team_name = team_names[idx] if idx < len(team_names) else f"Team{idx+1}"
            created_at = (
                team.get("created_at")
                or team.get("createdAt")
                or None
            )
            result.append({
                "index": idx,
                "name": team_name,
                "email": team.get("user", {}).get("email", ""),
                "user_id": team.get("user", {}).get("id", ""),
                "account_id": team.get("account", {}).get("id", ""),
                "org_id": team.get("account", {}).get("organizationId", ""),
                "has_token": bool(team.get("accessToken")),
                "created_at": created_at,
            })

        return result

    def add_team(self, name: str, email: str, user_id: str, account_id: str, org_id: str, access_token: str) -> Dict[str, Any]:
        """添加新 Team"""
        teams = self.load_teams()

        # 创建新 Team 对象
        new_team = {
            "user": {
                "id": user_id,
                "email": email
            },
            "account": {
                "id": account_id,
                "organizationId": org_id
            },
            "accessToken": access_token,
            # 用于 UI 显示“添加时间”
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }

        teams.append(new_team)

        team_names = self._load_team_names()
        if len(team_names) < len(teams) - 1:
            for i in range(len(team_names), len(teams) - 1):
                e = teams[i].get("user", {}).get("email", "")
                team_names.append(e.split("@")[0] if e else f"Team{i+1}")
        team_names.append(name or (email.split("@")[0] if email else f"Team{len(teams)}"))

        if self.save_teams(teams, team_names=team_names):
            return {
                "success": True,
                "message": f"Team '{name}' 添加成功",
                "index": len(teams) - 1
            }
        else:
            return {
                "success": False,
                "error": "保存 Team 失败"
            }

    def update_team(self, index: int, name: str, email: str, user_id: str, account_id: str, org_id: str, access_token: Optional[str] = None) -> Dict[str, Any]:
        """更新 Team 信息"""
        teams = self.load_teams()

        if index < 0 or index >= len(teams):
            return {
                "success": False,
                "error": f"Team 索引 {index} 不存在"
            }

        # 更新 Team 信息
        teams[index]["user"]["id"] = user_id
        teams[index]["user"]["email"] = email
        teams[index]["account"]["id"] = account_id
        teams[index]["account"]["organizationId"] = org_id

        # 如果提供了新 token,则更新
        if access_token:
            teams[index]["accessToken"] = access_token

        # 更新 team_names
        team_names = self._load_team_names()
        if len(team_names) > len(teams):
            team_names = team_names[:len(teams)]
        while len(team_names) < len(teams):
            i = len(team_names)
            e = teams[i].get("user", {}).get("email", "")
            team_names.append(e.split("@")[0] if e else f"Team{i+1}")
        team_names[index] = name or team_names[index]

        if self.save_teams(teams, team_names=team_names):
            return {
                "success": True,
                "message": f"Team '{name}' 更新成功"
            }
        else:
            return {
                "success": False,
                "error": "保存 Team 失败"
            }

    def delete_team(self, index: int) -> Dict[str, Any]:
        """删除 Team"""
        teams = self.load_teams()

        if index < 0 or index >= len(teams):
            return {
                "success": False,
                "error": f"Team 索引 {index} 不存在"
            }

        team_names = self._load_team_names()
        team_name = team_names[index] if index < len(team_names) else f"Team{index+1}"

        # 删除 Team
        teams.pop(index)

        if index < len(team_names):
            team_names.pop(index)
        if len(team_names) > len(teams):
            team_names = team_names[:len(teams)]

        if self.save_teams(teams, team_names=team_names):
            return {
                "success": True,
                "message": f"Team '{team_name}' 删除成功"
            }
        else:
            return {
                "success": False,
                "error": "保存 Team 失败"
            }

    def _load_team_names(self) -> List[str]:
        """从 config.toml 加载 team_names"""
        try:
            import config
            team_names = config.get("files.team_names", [])
            return team_names if isinstance(team_names, list) else []
        except Exception as e:
            log.error(f"加载 team_names 失败: {e}")
            return []

    def _update_config_team_names(self, teams: List[Dict[str, Any]], team_names: Optional[List[str]] = None):
        """更新 config.toml 中的 team_names"""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            # 读取现有配置
            if self.config_file.exists():
                with open(self.config_file, "r", encoding="utf-8") as f:
                    content = f.read()
            else:
                content = ""

            desired_names = list(team_names) if team_names is not None else self._load_team_names()
            if len(desired_names) > len(teams):
                desired_names = desired_names[:len(teams)]
            while len(desired_names) < len(teams):
                i = len(desired_names)
                email = teams[i].get("user", {}).get("email", "")
                desired_names.append(email.split("@")[0] if email else f"Team{i+1}")

            import re
            pattern = r"(?ms)^\s*team_names\s*=\s*\[.*?\]\s*$"
            replacement_line = f"team_names = {json.dumps(desired_names, ensure_ascii=False)}"

            if re.search(pattern, content):
                new_content = re.sub(pattern, replacement_line, content)
            else:
                files_section = re.search(r"(?m)^\[files\]\s*$", content)
                if files_section:
                    line_end = content.find("\n", files_section.end())
                    insert_at = len(content) if line_end == -1 else line_end + 1
                    new_content = content[:insert_at] + replacement_line + "\n" + content[insert_at:]
                else:
                    new_content = content.rstrip() + "\n\n[files]\n" + replacement_line + "\n"

            with open(self.config_file, "w", encoding="utf-8") as f:
                f.write(new_content)

        except Exception as e:
            log.error(f"更新 config.toml 失败: {e}")


# 单例实例
team_manager = TeamManager()
