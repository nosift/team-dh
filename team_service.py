# ==================== Team 服务模块 ====================
# 处理 ChatGPT Team 邀请相关功能

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from time import time

from config import (
    TEAMS,
    ACCOUNTS_PER_TEAM,
    REQUEST_TIMEOUT,
    USER_AGENT
)
from logger import log


def create_session_with_retry():
    """创建带重试机制的 HTTP Session"""
    session = requests.Session()
    retry_strategy = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "POST", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


http_session = create_session_with_retry()


_CACHE_TTL_SECONDS = 12
_invites_cache: dict[str, tuple[float, list]] = {}
_members_cache: dict[str, tuple[float, list]] = {}


def _is_pending_invite(invite: dict) -> bool:
    status = (
        (invite.get("status") or invite.get("invite_status") or invite.get("state") or "")
        .strip()
        .lower()
    )

    if not status:
        return True

    # 只要不是明确的“已处理/已结束”状态，都认为仍待接受
    if status in {"accepted", "completed", "done", "revoked", "canceled", "cancelled", "declined", "expired"}:
        return False
    return True


def _extract_invite_items(payload) -> list:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    candidates = [
        payload.get("items"),
        payload.get("account_invites"),
        payload.get("invites"),
        payload.get("data"),
    ]
    for c in candidates:
        if isinstance(c, list):
            return c
        if isinstance(c, dict):
            inner = c.get("items") or c.get("account_invites") or c.get("invites")
            if isinstance(inner, list):
                return inner

    return []


def build_invite_headers(team: dict) -> dict:
    """构建邀请请求的 Headers"""
    auth_token = team["auth_token"]
    if not auth_token.startswith("Bearer "):
        auth_token = f"Bearer {auth_token}"

    return {
        "accept": "*/*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "authorization": auth_token,
        "chatgpt-account-id": team["account_id"],
        "content-type": "application/json",
        "origin": "https://chatgpt.com",
        "referer": "https://chatgpt.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Chromium";v="135", "Not)A;Brand";v="99", "Google Chrome";v="135"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    }


def invite_single_email(email: str, team: dict) -> tuple[bool, str]:
    """邀请单个邮箱到 Team

    Args:
        email: 邮箱地址
        team: Team 配置

    Returns:
        tuple: (success, message)
    """
    headers = build_invite_headers(team)
    payload = {
        "email_addresses": [email],
        "role": "standard-user",
        "resend_emails": True
    }
    invite_url = f"https://chatgpt.com/backend-api/accounts/{team['account_id']}/invites"

    try:
        response = http_session.post(invite_url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)

        if response.status_code == 200:
            result = response.json()
            if result.get("account_invites"):
                return True, "邀请成功"
            elif result.get("errored_emails"):
                return False, f"邀请错误: {result['errored_emails']}"
            else:
                return True, "邀请已发送"
        else:
            return False, f"HTTP {response.status_code}: {response.text[:200]}"

    except Exception as e:
        return False, str(e)


def batch_invite_to_team(emails: list, team: dict) -> dict:
    """批量邀请多个邮箱到 Team

    Args:
        emails: 邮箱列表
        team: Team 配置

    Returns:
        dict: {"success": [...], "failed": [...]}
    """
    log.info(f"批量邀请 {len(emails)} 个邮箱到 {team['name']} (ID: {team['account_id'][:8]}...)", icon="email")

    headers = build_invite_headers(team)
    payload = {
        "email_addresses": emails,
        "role": "standard-user",
        "resend_emails": True
    }
    invite_url = f"https://chatgpt.com/backend-api/accounts/{team['account_id']}/invites"

    result = {
        "success": [],
        "failed": []
    }

    try:
        response = http_session.post(invite_url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)

        if response.status_code == 200:
            resp_data = response.json()

            # 处理成功邀请
            if resp_data.get("account_invites"):
                for invite in resp_data["account_invites"]:
                    invited_email = invite.get("email_address", "")
                    if invited_email:
                        result["success"].append(invited_email)
                        log.success(f"邀请成功: {invited_email}")

            # 处理失败的邮箱
            if resp_data.get("errored_emails"):
                for err in resp_data["errored_emails"]:
                    err_email = err.get("email", "")
                    err_msg = err.get("error", "Unknown error")
                    if err_email:
                        result["failed"].append({"email": err_email, "error": err_msg})
                        log.error(f"邀请失败: {err_email} - {err_msg}")

            # 如果没有明确的成功/失败信息，假设全部成功
            if not resp_data.get("account_invites") and not resp_data.get("errored_emails"):
                result["success"] = emails
                for email in emails:
                    log.success(f"邀请成功: {email}")

        else:
            log.error(f"批量邀请失败: HTTP {response.status_code}")
            result["failed"] = [{"email": e, "error": f"HTTP {response.status_code}"} for e in emails]

    except Exception as e:
        log.error(f"批量邀请异常: {e}")
        result["failed"] = [{"email": e, "error": str(e)} for e in emails]

    log.info(f"邀请结果: 成功 {len(result['success'])}, 失败 {len(result['failed'])}")
    return result


def get_team_stats(team: dict) -> dict:
    """获取 Team 的统计信息 (席位使用情况)

    Args:
        team: Team 配置

    Returns:
        dict: {"seats_in_use": int, "seats_entitled": int, "pending_invites": int}
    """
    headers = build_invite_headers(team)

    # 获取订阅信息
    subs_url = f"https://chatgpt.com/backend-api/subscriptions?account_id={team['account_id']}"

    try:
        response = http_session.get(subs_url, headers=headers, timeout=REQUEST_TIMEOUT)

        if response.status_code != 200:
            log.warning(f"获取 Team 统计失败: HTTP {response.status_code}")
            return {}

        data = response.json() or {}

        # 订阅接口的 pending_invites 有时不准确，这里用 invites 列表兜底（取更大值）
        pending_from_subs = (
            data.get("pending_invites")
            or data.get("pending_invites_count")
            or data.get("pending_invite_count")
            or 0
        )
        pending_from_invites = 0
        try:
            pending_from_invites = len(get_pending_invites(team))
        except Exception:
            pending_from_invites = 0

        pending_invites = max(int(pending_from_subs or 0), int(pending_from_invites or 0))

        return {
            "seats_in_use": data.get("seats_in_use", 0),
            "seats_entitled": data.get("seats_entitled", 0),
            "pending_invites": pending_invites,
            "plan_type": data.get("plan_type", ""),
        }

    except Exception as e:
        log.warning(f"获取 Team 统计异常: {e}")
        return {}


def get_pending_invites(team: dict, *, max_items: int = 500) -> list:
    """获取 Team 的待处理邀请列表

    Args:
        team: Team 配置

    Returns:
        list: 待处理邀请列表
    """
    cache_key = team.get("account_id") or team.get("name") or ""
    if cache_key:
        cached = _invites_cache.get(cache_key)
        if cached and (time() - cached[0]) < _CACHE_TTL_SECONDS:
            return cached[1]

    headers = build_invite_headers(team)

    pending: list = []
    offset = 0
    limit = 100

    try:
        while len(pending) < max_items:
            url = (
                f"https://chatgpt.com/backend-api/accounts/{team['account_id']}/invites"
                f"?offset={offset}&limit={limit}&query="
            )
            response = http_session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

            if response.status_code != 200:
                break

            data = response.json()
            items = _extract_invite_items(data)
            if not items:
                break

            for item in items:
                if isinstance(item, dict) and _is_pending_invite(item):
                    pending.append(item)
                    if len(pending) >= max_items:
                        break

            offset += len(items)
            if len(items) < limit:
                break

    except Exception as e:
        log.warning(f"获取待处理邀请异常: {e}")

    if cache_key:
        _invites_cache[cache_key] = (time(), pending)

    return pending


def get_all_invites_debug(team: dict, *, max_items: int = 500) -> tuple[list, str | None]:
    """获取 Team 的邀请列表（包含已接受/已结束），并返回可读错误信息（如有）。"""
    cache_key = team.get("account_id") or team.get("name") or ""
    if cache_key:
        cached = _invites_cache.get(cache_key)
        if cached and (time() - cached[0]) < _CACHE_TTL_SECONDS:
            return cached[1], None

    headers = build_invite_headers(team)

    items_all: list = []
    offset = 0
    limit = 100
    last_err: str | None = None

    try:
        while len(items_all) < max_items:
            url_candidates = [
                f"https://chatgpt.com/backend-api/accounts/{team['account_id']}/invites?offset={offset}&limit={limit}&query=",
                f"https://chatgpt.com/backend-api/accounts/{team['account_id']}/invites?offset={offset}&limit={limit}",
                f"https://chatgpt.com/backend-api/accounts/{team['account_id']}/invites?offset={offset}&limit={limit}&status=all",
                f"https://chatgpt.com/backend-api/accounts/{team['account_id']}/invites?offset={offset}&limit={limit}&include_processed=true",
            ]

            items = []
            ok_resp = None
            for url in url_candidates:
                response = http_session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
                if response.status_code != 200:
                    last_err = f"invites {url} -> HTTP {response.status_code}: {response.text[:160]}"
                    continue
                ok_resp = response
                try:
                    data = response.json()
                except Exception:
                    last_err = f"invites {url} -> JSON 解析失败"
                    continue
                items = _extract_invite_items(data)
                break

            if not ok_resp:
                break
            if not items:
                break
            items_all.extend([i for i in items if isinstance(i, dict)])

            offset += len(items)
            if len(items) < limit:
                break
    except Exception as e:
        last_err = str(e)
        log.warning(f"获取邀请列表异常: {e}")

    if cache_key:
        _invites_cache[cache_key] = (time(), items_all)

    return items_all[:max_items], last_err


def get_all_invites(team: dict, *, max_items: int = 500) -> list:
    items, _ = get_all_invites_debug(team, max_items=max_items)
    return items


def get_invite_status_for_email(team: dict, email: str) -> dict:
    """
    查询某个邮箱在该 Team 的邀请状态。

    返回示例：
      {"found": True, "status": "accepted", "timestamp": "...", "raw": {...}}
    """
    target = (email or "").strip().lower()
    if not target:
        return {"found": False}

    items, err = get_all_invites_debug(team, max_items=500)
    if err and not items:
        return {"found": False, "error": err}

    for inv in items:
        e = (inv.get("email_address") or inv.get("email") or inv.get("emailAddress") or "").strip().lower()
        if e != target:
            continue

        status = (
            (inv.get("status") or inv.get("invite_status") or inv.get("state") or "")
            .strip()
            .lower()
        )
        # 时间字段尽量取“接受/完成”时间
        ts = (
            inv.get("accepted_at")
            or inv.get("acceptedAt")
            or inv.get("completed_at")
            or inv.get("completedAt")
            or inv.get("updated_at")
            or inv.get("updatedAt")
            or inv.get("created_at")
            or inv.get("createdAt")
        )
        return {"found": True, "status": status, "timestamp": ts, "raw": inv}

    return {"found": False}


def get_team_members_debug(team: dict, *, max_items: int = 500) -> tuple[list, str | None]:
    """
    获取 Team 成员列表（用于按邮箱踢出旧 Team）。

    注意：ChatGPT 后端接口可能会变更；此函数尽量兼容不同返回结构。
    """
    cache_key = team.get("account_id") or team.get("name") or ""
    if cache_key:
        cached = _members_cache.get(cache_key)
        if cached and (time() - cached[0]) < _CACHE_TTL_SECONDS:
            return cached[1], None

    headers = build_invite_headers(team)
    items_all: list = []
    offset = 0
    limit = 100
    last_err: str | None = None

    candidates = [
        f"https://chatgpt.com/backend-api/accounts/{team['account_id']}/members?offset={{offset}}&limit={{limit}}",
        f"https://chatgpt.com/backend-api/accounts/{team['account_id']}/members",
        f"https://chatgpt.com/backend-api/accounts/{team['account_id']}/account_users?offset={{offset}}&limit={{limit}}",
        f"https://chatgpt.com/backend-api/accounts/{team['account_id']}/account_users",
        f"https://chatgpt.com/backend-api/accounts/{team['account_id']}/users?offset={{offset}}&limit={{limit}}",
        f"https://chatgpt.com/backend-api/accounts/{team['account_id']}/users",
    ]

    def extract(payload) -> list:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for k in ("items", "members", "data"):
                v = payload.get(k)
                if isinstance(v, list):
                    return v
                if isinstance(v, dict) and isinstance(v.get("items"), list):
                    return v["items"]
        return []

    try:
        while len(items_all) < max_items:
            response = None
            items = []

            for tmpl in candidates:
                url = tmpl.format(offset=offset, limit=limit)
                resp = http_session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
                if resp.status_code != 200:
                    last_err = f"members {url} -> HTTP {resp.status_code}: {resp.text[:160]}"
                    continue
                try:
                    data = resp.json()
                except Exception:
                    last_err = f"members {url} -> JSON 解析失败"
                    continue
                items = extract(data)
                response = resp
                break

            if response is None:
                break
            if not items:
                break

            for item in items:
                if isinstance(item, dict):
                    items_all.append(item)
                    if len(items_all) >= max_items:
                        break

            offset += len(items)
            if len(items) < limit:
                break
    except Exception as e:
        last_err = str(e)
        log.warning(f"获取成员列表异常: {e}")

    if cache_key:
        _members_cache[cache_key] = (time(), items_all)

    return items_all[:max_items], last_err


def get_team_members(team: dict, *, max_items: int = 500) -> list:
    items, _ = get_team_members_debug(team, max_items=max_items)
    return items


def get_member_info_for_email(team: dict, email: str) -> dict:
    """
    在 Team 成员列表中查找邮箱，并尽量返回加入时间字段。

    返回示例：
      {"found": True, "joined_at": "...", "raw": {...}}
    """
    target = (email or "").strip().lower()
    if not target:
        return {"found": False}

    members, err = get_team_members_debug(team, max_items=500)
    if err and not members:
        return {"found": False, "error": err}

    for m in members:
        if not isinstance(m, dict):
            continue

        e = (
            (m.get("email") or "")
            or ((m.get("user", {}) or {}).get("email") or "")
            or ((m.get("account_user", {}) or {}).get("email") or "")
        )
        e = (e or "").strip().lower()
        if e != target:
            continue

        joined_at = (
            m.get("joined_at")
            or m.get("joinedAt")
            or m.get("created_at")
            or m.get("createdAt")
            or m.get("added_at")
            or m.get("addedAt")
            or m.get("updated_at")
            or m.get("updatedAt")
        )
        return {"found": True, "joined_at": joined_at, "raw": m}

    return {"found": False}


def remove_member_by_email(team: dict, email: str) -> tuple[bool, str]:
    """
    从 Team 移除指定邮箱对应的成员。

    返回 (success, message)
    """
    target = (email or "").strip().lower()
    if not target:
        return False, "email 为空"

    members = get_team_members(team, max_items=500)
    member = None
    for m in members:
        e = (
            (m.get("email") if isinstance(m, dict) else "")
            or (m.get("user", {}) or {}).get("email") if isinstance(m, dict) else ""
        )
        e = (e or "").strip().lower()
        if e == target:
            member = m
            break

    if not member:
        return False, "未在成员列表中找到该邮箱"

    member_id = (
        member.get("id")
        or member.get("member_id")
        or member.get("memberId")
        or (member.get("user", {}) or {}).get("id")
    )
    if not member_id:
        return False, "无法解析 member_id"

    headers = build_invite_headers(team)

    # 兼容不同实现：优先 DELETE /members/{id}
    url = f"https://chatgpt.com/backend-api/accounts/{team['account_id']}/members/{member_id}"
    try:
        resp = http_session.delete(url, headers=headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code in (200, 204):
            return True, "已移除"
        # 尝试另一种 payload 接口（若存在）
        alt = f"https://chatgpt.com/backend-api/accounts/{team['account_id']}/members/remove"
        resp2 = http_session.post(alt, headers=headers, json={"member_id": member_id, "email": target}, timeout=REQUEST_TIMEOUT)
        if resp2.status_code in (200, 204):
            return True, "已移除"
        return False, f"移除失败: HTTP {resp.status_code} / {resp2.status_code}"
    except Exception as e:
        return False, str(e)

def check_available_seats(team: dict) -> int:
    """检查 Team 可用席位数

    Args:
        team: Team 配置

    Returns:
        int: 可用席位数
    """
    stats = get_team_stats(team)

    if not stats:
        return 0

    seats_in_use = stats.get("seats_in_use", 0)
    seats_entitled = stats.get("seats_entitled", 5)  # 默认 5 席位
    pending = len(get_pending_invites(team))

    available = seats_entitled - seats_in_use - pending
    return max(0, available)


def print_team_summary(team: dict):
    """打印 Team 摘要信息"""
    stats = get_team_stats(team)
    pending = get_pending_invites(team)

    log.info(f"{team['name']} 状态 (ID: {team['account_id'][:8]}...)", icon="team")

    if stats:
        seats_info = f"席位: {stats.get('seats_in_use', '?')}/{stats.get('seats_entitled', '?')}"
        pending_info = f"待处理邀请: {len(pending)}"
        available = stats.get('seats_entitled', 5) - stats.get('seats_in_use', 0) - len(pending)
        available_info = f"可用席位: {available}"
        log.info(f"{seats_info} | {pending_info} | {available_info}")
    else:
        log.warning("无法获取状态信息")
