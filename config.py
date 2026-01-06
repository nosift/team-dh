# ==================== 配置模块 ====================
import base64
import json
import os
import random
import re
import string
from pathlib import Path

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

# ==================== 路径 ====================
BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.toml"
TEAM_JSON_FILE = BASE_DIR / "team.json"


def _env_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _decode_env_b64(var_name: str) -> str | None:
    raw = os.getenv(var_name)
    if not raw:
        return None
    try:
        return base64.b64decode(raw).decode("utf-8")
    except Exception:
        return None


def _load_toml_from_env() -> dict:
    if tomllib is None:
        return {}

    raw = _decode_env_b64("CONFIG_TOML_B64") or _decode_env_b64("CONFIG_TOML_BASE64")
    if raw is None:
        raw = os.getenv("CONFIG_TOML")

    if not raw:
        return {}

    try:
        return tomllib.loads(raw)
    except Exception:
        return {}


def _load_toml() -> dict:
    env_cfg = _load_toml_from_env()
    if env_cfg:
        return env_cfg

    if not CONFIG_FILE.exists() or tomllib is None:
        return {}
    try:
        with open(CONFIG_FILE, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def _load_teams_from_env_indexed() -> list:
    teams = []
    for idx in range(0, 100):
        token = (
            os.getenv(f"TEAM_{idx}_TOKEN")
            or os.getenv(f"TEAM_{idx}_AUTH_TOKEN")
            or os.getenv(f"TEAM_{idx}_ACCESS_TOKEN")
        )
        account_id = os.getenv(f"TEAM_{idx}_ACCOUNT_ID")
        org_id = os.getenv(f"TEAM_{idx}_ORG_ID") or os.getenv(f"TEAM_{idx}_ORGANIZATION_ID")

        if not token and not account_id and not org_id:
            break

        if not token or not account_id:
            continue

        name = os.getenv(f"TEAM_{idx}_NAME") or f"Team{idx+1}"
        email = os.getenv(f"TEAM_{idx}_EMAIL") or f"{name}@example.com"
        user_id = os.getenv(f"TEAM_{idx}_USER_ID") or ""

        teams.append(
            {
                "user": {"id": user_id, "email": email},
                "account": {"id": account_id, "organizationId": org_id or ""},
                "accessToken": token,
            }
        )

    return teams


def _load_teams_from_env_json() -> list:
    raw = _decode_env_b64("TEAM_JSON_B64") or _decode_env_b64("TEAM_JSON_BASE64")
    if raw is None:
        raw = os.getenv("TEAM_JSON")

    if not raw:
        return []

    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else [data]
    except Exception:
        return []


def _load_teams() -> list:
    # 适用于 Zeabur/Railway 等无法挂载文件的平台：从环境变量注入 Team 凭证
    env_json = _load_teams_from_env_json()
    if env_json:
        return env_json

    env_indexed = _load_teams_from_env_indexed()
    if env_indexed:
        return env_indexed

    if not TEAM_JSON_FILE.exists():
        return []
    try:
        with open(TEAM_JSON_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else [data]
    except Exception:
        return []


# ==================== 加载配置 ====================
_cfg = _load_toml()
_raw_teams = _load_teams()

# 转换 team.json 格式为 team_service.py 期望的格式
TEAMS = []
_team_names = (_cfg.get("files", {}) or {}).get("team_names", []) or []
for i, t in enumerate(_raw_teams):
    default_name = t.get("user", {}).get("email", f"Team{i+1}").split("@")[0]
    name = _team_names[i] if i < len(_team_names) and _team_names[i] else default_name
    TEAMS.append(
        {
            "name": name,
            "account_id": t.get("account", {}).get("id", ""),
            "org_id": t.get("account", {}).get("organizationId", ""),
            "auth_token": t.get("accessToken", ""),
            "raw": t,  # 保留原始数据
        }
    )

# 邮箱
_email = _cfg.get("email", {})
EMAIL_API_BASE = _email.get("api_base", "")
EMAIL_API_AUTH = _email.get("api_auth", "")
EMAIL_DOMAINS = _email.get("domains", []) or ([_email["domain"]] if _email.get("domain") else [])
EMAIL_DOMAIN = EMAIL_DOMAINS[0] if EMAIL_DOMAINS else ""
EMAIL_ROLE = _email.get("role", "gpt-team")
EMAIL_WEB_URL = _email.get("web_url", "")

# CRS
_crs = _cfg.get("crs", {})
CRS_API_BASE = _crs.get("api_base", "")
CRS_ADMIN_TOKEN = _crs.get("admin_token", "")

# 账号
_account = _cfg.get("account", {})
DEFAULT_PASSWORD = _account.get("default_password", "kfcvivo50")
ACCOUNTS_PER_TEAM = _account.get("accounts_per_team", 4)

# 注册
_reg = _cfg.get("register", {})
REGISTER_NAME = _reg.get("name", "test")
REGISTER_BIRTHDAY = _reg.get("birthday", {"year": "2000", "month": "01", "day": "01"})


def get_random_birthday() -> dict:
    """生成随机生日 (2000-2005年)"""
    year = str(random.randint(2000, 2005))
    month = str(random.randint(1, 12)).zfill(2)
    day = str(random.randint(1, 28)).zfill(2)  # 用28避免月份天数问题
    return {"year": year, "month": month, "day": day}

# 请求
_req = _cfg.get("request", {})
REQUEST_TIMEOUT = _req.get("timeout", 30)
USER_AGENT = _req.get("user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/135.0.0.0")

# 验证码
_ver = _cfg.get("verification", {})
VERIFICATION_CODE_TIMEOUT = _ver.get("timeout", 60)
VERIFICATION_CODE_INTERVAL = _ver.get("interval", 3)
VERIFICATION_CODE_MAX_RETRIES = _ver.get("max_retries", 20)

# 浏览器
_browser = _cfg.get("browser", {})
BROWSER_WAIT_TIMEOUT = _browser.get("wait_timeout", 60)
BROWSER_SHORT_WAIT = _browser.get("short_wait", 10)

# 文件
_files = _cfg.get("files", {})
CSV_FILE = _files.get("csv_file", str(BASE_DIR / "accounts.csv"))
TEAM_TRACKER_FILE = _files.get("tracker_file", str(BASE_DIR / "team_tracker.json"))


# ==================== 配置获取函数 ====================
def get(key: str, default=None):
    """
    获取配置项的值
    支持点号分隔的嵌套键，例如: "web.port" 或 "redemption.database_file"
    """
    # 环境变量优先（便于云平台通过 Secrets 注入）
    if key == "web.admin_password":
        env_value = os.getenv("ADMIN_PASSWORD") or os.getenv("WEB_ADMIN_PASSWORD")
        if env_value:
            return env_value

    if key == "web.enable_admin":
        env_value = os.getenv("ENABLE_ADMIN") or os.getenv("WEB_ENABLE_ADMIN")
        parsed = _env_bool(env_value)
        if parsed is not None:
            return parsed

    if key == "redemption.database_file":
        env_value = os.getenv("REDEMPTION_DATABASE_FILE") or os.getenv("DATABASE_FILE")
        if env_value:
            return env_value

    keys = key.split(".")
    value = _cfg

    for k in keys:
        if isinstance(value, dict):
            value = value.get(k)
            if value is None:
                return default
        else:
            return default

    return value if value is not None else default

# ==================== 随机姓名列表 ====================
FIRST_NAMES = [
    "James", "John", "Robert", "Michael", "William", "David", "Richard", "Joseph",
    "Thomas", "Christopher", "Charles", "Daniel", "Matthew", "Anthony", "Mark",
    "Mary", "Patricia", "Jennifer", "Linda", "Elizabeth", "Barbara", "Susan",
    "Jessica", "Sarah", "Karen", "Emma", "Olivia", "Sophia", "Isabella", "Mia"
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Thompson", "White",
    "Harris", "Clark", "Lewis", "Robinson", "Walker", "Young", "Allen"
]


def get_random_name() -> str:
    """获取随机外国名字"""
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    return f"{first} {last}"





# ==================== 邮箱辅助函数 ====================
def get_random_domain() -> str:
    return random.choice(EMAIL_DOMAINS) if EMAIL_DOMAINS else EMAIL_DOMAIN


def generate_random_email(prefix_len: int = 8) -> str:
    prefix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=prefix_len))
    return f"{prefix}oaiteam@{get_random_domain()}"


def generate_email_for_user(username: str) -> str:
    safe = re.sub(r'[^a-zA-Z0-9]', '', username.lower())[:20]
    return f"{safe}oaiteam@{get_random_domain()}"


def get_team(index: int = 0) -> dict:
    return TEAMS[index] if 0 <= index < len(TEAMS) else {}


def get_team_by_email(email: str) -> dict:
    return next((t for t in TEAMS if t.get("user", {}).get("email") == email), {})


def get_team_by_org(org_id: str) -> dict:
    return next((t for t in TEAMS if t.get("account", {}).get("organizationId") == org_id), {})


def resolve_team(team_name: str) -> dict:
    """
    根据 team_name 查找 Team 配置。

    - 优先精确匹配 TEAMS[i]["name"]
    - 其次忽略大小写/首尾空格匹配
    - 最后支持 "Team1"/"team 1" 这类按序号映射到 TEAMS[0]
    """
    if not team_name:
        return {}

    normalized = str(team_name).strip()
    if not normalized:
        return {}

    exact = next((t for t in TEAMS if (t.get("name") or "") == normalized), None)
    if exact:
        return exact

    lowered = normalized.casefold()
    relaxed = next((t for t in TEAMS if (t.get("name") or "").strip().casefold() == lowered), None)
    if relaxed:
        return relaxed

    m = re.match(r"^team\s*(\d+)$", normalized, flags=re.IGNORECASE)
    if m:
        idx = int(m.group(1)) - 1
        if 0 <= idx < len(TEAMS):
            return TEAMS[idx]

    return {}


def reload_teams():
    """重新加载 team.json 和 team_names 配置"""
    global TEAMS, _raw_teams, _cfg

    # 重新加载 team.json
    _raw_teams = _load_teams()

    # 重新加载 config.toml
    _cfg = _load_toml()

    # 重新构建 TEAMS
    TEAMS.clear()
    team_names = _cfg.get("files", {}).get("team_names", [])

    for i, t in enumerate(_raw_teams):
        # 优先使用 team_names 配置,否则使用邮箱前缀
        team_name = team_names[i] if i < len(team_names) else t.get("user", {}).get("email", f"Team{i+1}").split("@")[0]

        TEAMS.append({
            "name": team_name,
            "account_id": t.get("account", {}).get("id", ""),
            "org_id": t.get("account", {}).get("organizationId", ""),
            "auth_token": t.get("accessToken", ""),
            "raw": t  # 保留原始数据
        })

    return len(TEAMS)
