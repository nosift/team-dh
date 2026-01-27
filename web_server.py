"""
Flask Web服务器
提供兑换码兑换的Web界面和API接口
"""

from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for
from functools import wraps
import os
import secrets
from datetime import datetime
from redemption_service import RedemptionService
from database import db
from logger import log
import config
import ipaddress
from team_service import get_member_info_for_email
from transfer_scheduler import start_transfer_worker
from transfer_scheduler import run_transfer_once, sync_joined_leases_once, sync_joined_leases_once_detailed, run_transfer_for_email, sync_joined_lease_for_email_once_detailed
from monitor import monitor, run_monitor_loop


app = Flask(__name__)

# ==================== Session / Secret Key ====================
# 多进程(gunicorn 多 worker)场景下，secret_key 必须固定，否则登录态会在不同 worker 间随机失效，
# 前端请求 /api/* 会被重定向到 /admin/login，导致出现 “<!DOCTYPE ... is not valid JSON”。
_secret_key = (
    os.getenv("SECRET_KEY")
    or os.getenv("FLASK_SECRET_KEY")
    or config.get("web.secret_key")
)
if not _secret_key:
    _secret_key = secrets.token_hex(32)
    log.warning("未设置 SECRET_KEY/FLASK_SECRET_KEY/web.secret_key，已生成临时 session key；多实例/重启后登录态会失效")
app.secret_key = _secret_key  # 用于 session 加密

# 配置
ADMIN_PASSWORD = config.get("web.admin_password", "admin123")
ENABLE_ADMIN = config.get("web.enable_admin", True)

# 后台：按月到期自动转移（默认关闭，通过 AUTO_TRANSFER_ENABLED=true 开启）
start_transfer_worker()

# 后台：监控和告警（默认开启，通过 MONITOR_ENABLED=false 关闭）
if os.getenv("MONITOR_ENABLED", "true").lower() != "false":
    monitor_interval = int(os.getenv("MONITOR_INTERVAL", "300"))  # 默认 5 分钟
    run_monitor_loop(interval=monitor_interval)


_last_config_reload_sig: tuple[float, float, int, int] | None = None


def _config_files_signature() -> tuple[float, float, int, int]:
    cfg_path = config.CONFIG_FILE if config.CONFIG_FILE.exists() else config.FALLBACK_CONFIG_FILE
    team_path = config.TEAM_JSON_FILE if config.TEAM_JSON_FILE.exists() else config.FALLBACK_TEAM_JSON_FILE
    try:
        cfg_stat = cfg_path.stat()
        cfg_mtime = cfg_stat.st_mtime
        cfg_size = cfg_stat.st_size
    except Exception:
        cfg_mtime = 0.0
        cfg_size = 0
    try:
        team_stat = team_path.stat()
        team_mtime = team_stat.st_mtime
        team_size = team_stat.st_size
    except Exception:
        team_mtime = 0.0
        team_size = 0
    return (cfg_mtime, team_mtime, cfg_size, team_size)


@app.before_request
def _auto_reload_config_if_changed():
    """
    多 worker 环境下（gunicorn）Team 变更只会在触发保存的那个 worker 里 reload。
    这里按文件 mtime 自动 reload，保证所有 worker 最终一致。
    """
    global _last_config_reload_sig
    try:
        sig = _config_files_signature()
        if _last_config_reload_sig != sig:
            config.reload_teams()
            _last_config_reload_sig = sig
    except Exception:
        # 不影响请求主流程
        pass


# ==================== 认证装饰器 ====================

def require_admin(f):
    """管理员认证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not ENABLE_ADMIN:
            return jsonify({"error": "管理后台已禁用"}), 403

        if not session.get("admin_logged_in"):
            # /api/* 接口返回 JSON，避免前端把 HTML 当 JSON 解析
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "error": "未登录，请重新登录管理后台"}), 401
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated_function


def _get_client_ip() -> str | None:
    """
    获取真实客户端 IP（适配 Zeabur / 反向代理）。
    默认信任 X-Forwarded-For / X-Real-IP（可通过 TRUST_PROXY=false 关闭）。
    """
    trust_proxy = os.getenv("TRUST_PROXY", "true").strip().lower() not in {"0", "false", "no", "off"}
    if not trust_proxy:
        return request.remote_addr

    candidates: list[str] = []

    # RFC 7239 Forwarded: for=...
    forwarded = request.headers.get("Forwarded")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",")]
        for part in parts:
            for kv in part.split(";"):
                kv = kv.strip()
                if kv.lower().startswith("for="):
                    v = kv[4:].strip().strip('"')
                    # 可能带端口、IPv6 方括号
                    if v.startswith("["):
                        end = v.find("]")
                        candidates.append(v[1:end] if end != -1 else v.strip("[]"))
                    else:
                        # IPv4:port
                        candidates.append(v.split(":")[0] if v.count(":") == 1 else v)

    xff = request.headers.get("X-Forwarded-For")
    if xff:
        # XFF: client, proxy1, proxy2
        for ip in [p.strip() for p in xff.split(",") if p.strip()]:
            candidates.append(ip)

    xrip = request.headers.get("X-Real-IP")
    if xrip:
        candidates.append(xrip.strip())

    # 最后回退到 remote_addr
    if request.remote_addr:
        candidates.append(request.remote_addr)

    parsed: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for ip in candidates:
        try:
            parsed.append(ipaddress.ip_address(ip))
        except Exception:
            continue

    for addr in parsed:
        try:
            if addr.is_global:
                return str(addr)
        except Exception:
            pass

    return str(parsed[0]) if parsed else None


def _team_index_from_any_name(team_name: str | None) -> int | None:
    if not team_name:
        return None
    team = config.resolve_team(team_name)
    if not team:
        return None
    account_id = team.get("account_id")
    if account_id:
        for idx, t in enumerate(config.TEAMS):
            if t.get("account_id") == account_id:
                return idx
    # 兜底：按名称匹配
    normalized = str(team.get("name") or "").strip().lower()
    for idx, t in enumerate(config.TEAMS):
        if str(t.get("name") or "").strip().lower() == normalized:
            return idx
    return None


def _team_display_name(team_name: str | None) -> str | None:
    if not team_name:
        return None
    team = config.resolve_team(team_name)
    return (team or {}).get("name") or team_name


# ==================== 用户API ====================

@app.route("/")
def index():
    """兑换页面"""
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.route("/batch.html")
def batch_page():
    """批量兑换页面"""
    with open("static/batch.html", "r", encoding="utf-8") as f:
        return f.read()


@app.route("/user.html")
def user_page():
    """用户中心页面"""
    with open("static/user.html", "r", encoding="utf-8") as f:
        return f.read()


@app.route("/api/redeem", methods=["POST"])
def redeem():
    """兑换接口"""
    try:
        data = request.get_json() or {}

        if not data:
            return jsonify({"success": False, "error": "无效的请求数据"}), 400

        email = data.get("email", "").strip()
        code = data.get("code", "").strip().upper()

        if not email or not code:
            return jsonify({"success": False, "error": "邮箱和兑换码不能为空"}), 400

        # 获取客户端IP（反代环境使用真实IP）
        ip_address = _get_client_ip()

        # 执行兑换
        result = RedemptionService.redeem(code, email, ip_address)

        # 根据结果返回不同的HTTP状态码
        if result["success"]:
            return jsonify(result), 200
        else:
            # 根据错误类型返回不同状态码
            error_code = result.get("code", "UNKNOWN")
            if error_code == "RATE_LIMIT":
                return jsonify(result), 429  # Too Many Requests
            elif error_code in ["INVALID_EMAIL", "INVALID_CODE"]:
                return jsonify(result), 400  # Bad Request
            else:
                return jsonify(result), 500  # Internal Server Error

    except Exception as e:
        log.error(f"兑换接口错误: {e}")
        return jsonify({"success": False, "error": f"系统错误: {str(e)}"}), 500


@app.route("/api/redeem/batch", methods=["POST"])
def redeem_batch():
    """批量兑换接口"""
    try:
        data = request.get_json() or {}

        if not data:
            return jsonify({"success": False, "error": "无效的请求数据"}), 400

        email = data.get("email", "").strip()
        codes = data.get("codes", [])

        if not email:
            return jsonify({"success": False, "error": "邮箱不能为空"}), 400

        if not codes or not isinstance(codes, list):
            return jsonify({"success": False, "error": "兑换码列表不能为空"}), 400

        # 限制单次批量兑换数量
        if len(codes) > 20:
            return jsonify({"success": False, "error": "单次最多兑换20个码"}), 400

        # 获取客户端IP
        ip_address = _get_client_ip()

        results = []
        success_count = 0
        fail_count = 0

        for code in codes:
            code = (code or "").strip().upper()
            if not code:
                continue

            result = RedemptionService.redeem(code, email, ip_address)
            results.append({
                "code": code,
                "success": result.get("success", False),
                "message": result.get("message") or result.get("error", "未知错误")
            })

            if result.get("success"):
                success_count += 1
            else:
                fail_count += 1

        return jsonify({
            "success": True,
            "total": len(results),
            "success_count": success_count,
            "fail_count": fail_count,
            "results": results
        }), 200

    except Exception as e:
        log.error(f"批量兑换接口错误: {e}")
        return jsonify({"success": False, "error": f"系统错误: {str(e)}"}), 500


@app.route("/api/user/status", methods=["POST"])
def user_status():
    """用户状态查询接口"""
    try:
        data = request.get_json() or {}
        email = (data.get("email") or "").strip().lower()

        if not email:
            return jsonify({"success": False, "error": "邮箱不能为空"}), 400

        # 查询租约信息
        lease = db.get_member_lease(email)

        # 查询兑换记录
        redemptions = db.get_redemptions_by_email(email, limit=10)

        if not lease and not redemptions:
            return jsonify({
                "success": True,
                "found": False,
                "message": "未找到该邮箱的记录"
            })

        # 构建响应数据
        response = {
            "success": True,
            "found": True,
            "email": email,
            "lease": None,
            "redemptions": []
        }

        if lease:
            response["lease"] = {
                "team_name": lease.get("team_name"),
                "status": lease.get("status"),
                "joined_at": lease.get("joined_at"),
                "expires_at": lease.get("expires_at"),
                "created_at": lease.get("created_at")
            }

        if redemptions:
            response["redemptions"] = [
                {
                    "code": r.get("code"),
                    "team_name": r.get("team_name"),
                    "redeemed_at": r.get("redeemed_at"),
                    "status": r.get("status", "success")
                }
                for r in redemptions
            ]

        return jsonify(response)

    except Exception as e:
        log.error(f"用户状态查询错误: {e}")
        return jsonify({"success": False, "error": f"系统错误: {str(e)}"}), 500


@app.route("/api/user/unbind", methods=["POST"])
def user_unbind():
    """用户解绑接口 - 主动退出 Team"""
    try:
        data = request.get_json() or {}
        email = (data.get("email") or "").strip().lower()

        if not email:
            return jsonify({"success": False, "error": "邮箱不能为空"}), 400

        # 查询当前租约
        lease = db.get_member_lease(email)
        if not lease:
            return jsonify({"success": False, "error": "未找到该邮箱的 Team 记录"}), 404

        team_name = lease.get("team_name")
        if not team_name:
            return jsonify({"success": False, "error": "无法确定当前 Team"}), 400

        # 获取 Team 配置
        team_cfg = config.resolve_team(team_name)
        if not team_cfg:
            return jsonify({"success": False, "error": f"Team '{team_name}' 配置不存在"}), 400

        # 调用移除成员 API
        from team_service import remove_member_by_email
        success, message = remove_member_by_email(team_cfg, email)

        if success:
            # 更新租约状态为已解绑
            db.update_member_lease_status(email, "unbound")
            db.add_member_lease_event(
                email=email,
                action="unbind",
                from_team=team_name,
                to_team=None,
                message="用户主动解绑"
            )
            return jsonify({
                "success": True,
                "message": f"已成功从 {team_name} 解绑"
            })
        else:
            return jsonify({
                "success": False,
                "error": message or "解绑失败"
            }), 500

    except Exception as e:
        log.error(f"用户解绑错误: {e}")
        return jsonify({"success": False, "error": f"系统错误: {str(e)}"}), 500


@app.route("/api/user/transfer", methods=["POST"])
def user_transfer():
    """用户换车接口 - 质保换车，转移到新 Team"""
    try:
        data = request.get_json() or {}
        email = (data.get("email") or "").strip().lower()
        reason = (data.get("reason") or "").strip()

        if not email:
            return jsonify({"success": False, "error": "邮箱不能为空"}), 400

        # 查询当前租约
        lease = db.get_member_lease(email)
        if not lease:
            return jsonify({"success": False, "error": "未找到该邮箱的 Team 记录"}), 404

        current_team = lease.get("team_name")
        current_status = lease.get("status", "")

        # 检查状态：只允许 active 状态的用户换车
        if current_status not in ["active", "pending", "awaiting_join"]:
            return jsonify({
                "success": False,
                "error": f"当前状态 ({current_status}) 不支持换车"
            }), 400

        # 调用转移服务（强制转移，不检查到期时间）
        from transfer_service import force_transfer_for_email
        result = force_transfer_for_email(email, reason=reason or "用户申请质保换车")

        if result.get("success") and result.get("moved", 0) > 0:
            new_team = result.get("new_team", "新 Team")
            return jsonify({
                "success": True,
                "message": f"已成功从 {current_team} 换车到 {new_team}，邀请邮件已发送"
            })
        else:
            return jsonify({
                "success": False,
                "error": result.get("message", "换车失败，请稍后重试或联系管理员")
            }), 500

    except Exception as e:
        log.error(f"用户换车错误: {e}")
        return jsonify({"success": False, "error": f"系统错误: {str(e)}"}), 500


@app.route("/api/verify", methods=["GET"])
def verify():
    """验证兑换码"""
    code = request.args.get("code", "").strip().upper()

    if not code:
        return jsonify({"valid": False, "error": "兑换码不能为空"}), 400

    result = RedemptionService.verify_code_info(code)
    return jsonify(result)


# ==================== 管理后台 ====================

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """管理员登录"""
    if request.method == "POST":
        password = request.form.get("password", "")

        if password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        else:
            return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>管理员登录</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: Arial; max-width: 400px; margin: 100px auto; padding: 20px; }
        input { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #d2d2d7; border-radius: 8px; }
        button { width: 100%; padding: 10px; background: #000000; color: white; border: none; cursor: pointer; border-radius: 8px; }
        button:hover { background: #1d1d1f; }
        .error { color: red; margin: 10px 0; }
    </style>
</head>
<body>
    <h2>管理员登录</h2>
    <p class="error">密码错误！</p>
    <form method="POST">
        <input type="password" name="password" placeholder="请输入管理密码" required>
        <button type="submit">登录</button>
    </form>
</body>
</html>
            """)

    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>管理员登录</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: Arial; max-width: 400px; margin: 100px auto; padding: 20px; }
        input { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #d2d2d7; border-radius: 8px; }
        button { width: 100%; padding: 10px; background: #000000; color: white; border: none; cursor: pointer; border-radius: 8px; }
        button:hover { background: #1d1d1f; }
    </style>
</head>
<body>
    <h2>管理员登录</h2>
    <form method="POST">
        <input type="password" name="password" placeholder="请输入管理密码" required>
        <button type="submit">登录</button>
    </form>
</body>
</html>
    """)


@app.route("/admin/logout")
def admin_logout():
    """登出"""
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@require_admin
def admin_dashboard():
    """管理后台首页"""
    from flask import make_response
    with open("static/admin.html", "r", encoding="utf-8") as f:
        content = f.read()

    # 创建响应并添加禁用缓存的头部
    response = make_response(content)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/api/admin/stats")
@require_admin
def admin_stats():
    """获取统计信息"""
    try:
        # 获取仪表盘统计
        stats = db.get_dashboard_stats()

        # 获取Team统计
        raw_team_stats = db.list_team_stats()

        # 只返回“当前已配置的 Team”，并对历史遗留的 Team1/Team2/Team3 名称做归一化，避免出现重复/莫名其妙的 TeamX
        from team_manager import team_manager

        teams = team_manager.get_team_list()
        stats_by_index: dict[int, dict] = {}
        for row in raw_team_stats:
            idx = _team_index_from_any_name(row.get("team_name"))
            if idx is None:
                continue
            prev = stats_by_index.get(idx)
            if not prev:
                stats_by_index[idx] = row
                continue
            # 保留更新时间更新的一条
            if str(row.get("last_updated") or "") > str(prev.get("last_updated") or ""):
                stats_by_index[idx] = row

        team_stats: list[dict] = []
        for team in teams:
            idx = team.get("index")
            if not isinstance(idx, int):
                continue
            row = stats_by_index.get(idx) or {}
            team_name = team.get("name")

            last_updated = row.get("last_updated")
            # teams_stats.last_updated 来自 SQLite CURRENT_TIMESTAMP（UTC）
            if isinstance(last_updated, str) and last_updated:
                if " " in last_updated and "T" not in last_updated:
                    last_updated = last_updated.replace(" ", "T", 1)
                if not (last_updated.endswith("Z") or "+" in last_updated or "-" in last_updated[10:]):
                    last_updated = last_updated + "Z"

            created_at = team.get("created_at")
            created_at_source = None

            # 优先从 teams_stats 表获取
            if not created_at:
                team_time_info = db.get_team_created_at(team_name)
                if team_time_info:
                    created_at = team_time_info.get("created_at")
                    created_at_source = team_time_info.get("created_at_source")
                    if not created_at:
                        created_at = team_time_info.get("first_seen_at")
                        created_at_source = "first_seen"

            # 兼容老数据：Team 没有 created_at 时，用该 Team 最早生成兑换码的时间兜底（近似"添加时间"）
            if not created_at:
                try:
                    with db.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            """
                            SELECT MIN(created_at) AS first_time
                            FROM redemption_codes
                            WHERE team_name IN (?, ?)
                        """,
                            (team_name, f"Team{idx+1}"),
                        )
                        r = cursor.fetchone()
                        created_at = (r["first_time"] if r else None)
                        if created_at:
                            created_at_source = "first_code"
                except Exception:
                    created_at = None

            if isinstance(created_at, str) and created_at:
                if " " in created_at and "T" not in created_at:
                    created_at = created_at.replace(" ", "T", 1)
                # redemption_codes.created_at 来自 SQLite CURRENT_TIMESTAMP（UTC）
                if not (created_at.endswith("Z") or "+" in created_at or "-" in created_at[10:]):
                    created_at = created_at + "Z"

            team_stats.append(
                {
                    "team_name": team_name,
                    "team_index": idx,
                    "total_seats": row.get("total_seats", 0),
                    "used_seats": row.get("used_seats", 0),
                    "pending_invites": row.get("pending_invites", 0),
                    "available_seats": row.get("available_seats", 0),
                    "created_at": created_at,
                    "created_at_source": created_at_source,
                    "last_updated": last_updated,
                }
            )

        return jsonify({
            "success": True,
            "data": {
                "dashboard": stats,
                "teams": team_stats
            }
        })
    except Exception as e:
        log.error(f"获取统计失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/codes")
@require_admin
def admin_list_codes():
    """列出兑换码"""
    try:
        team_name = request.args.get("team")
        status = request.args.get("status")
        group_name = request.args.get("group")  # 新增：分组筛选

        include_deleted = request.args.get("include_deleted", "false").lower() in {"1", "true", "yes", "y", "on"}

        # 使用新的支持分组筛选的方法
        codes = db.list_codes_with_group(
            team_name=None,
            status=status,
            group_name=group_name,
            include_deleted=include_deleted
        )

        # 兼容：数据库中可能存的是 Team3 这类旧名字，但前端筛选用的是当前展示名
        # 所以这里按"归一化后的 team_index"过滤，而不是直接按 team_name 字符串过滤
        target_idx = _team_index_from_any_name(team_name)
        if target_idx is not None:
            filtered = []
            for c in codes:
                if _team_index_from_any_name(c.get("team_name")) == target_idx:
                    filtered.append(c)
            codes = filtered

        for c in codes:
            c["team_key"] = c.get("team_name")
            c["team_index"] = _team_index_from_any_name(c.get("team_name"))
            c["team_name"] = _team_display_name(c.get("team_name")) or c.get("team_name")

            # 中文化 auto_transfer_enabled 字段
            auto_transfer = c.get("auto_transfer_enabled", 1)
            c["权限类型"] = "普通用户(按月转移)" if auto_transfer else "VIP用户(永久使用)"

        return jsonify({
            "success": True,
            "data": codes
        })
    except Exception as e:
        log.error(f"获取兑换码列表失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/redemptions")
@require_admin
def admin_list_redemptions():
    """列出兑换记录"""
    try:
        limit = int(request.args.get("limit", 100))
        offset = int(request.args.get("offset", 0))

        redemptions = db.list_redemptions(limit=limit, offset=offset)
        for r in redemptions:
            r["team_key"] = r.get("team_name")
            r["team_index"] = _team_index_from_any_name(r.get("team_name"))
            r["team_name"] = _team_display_name(r.get("team_name")) or r.get("team_name")
            # redeemed_at 来自 SQLite CURRENT_TIMESTAMP（UTC），统一转 ISO+Z 便于前端正确显示本地时间
            v = r.get("redeemed_at")
            if isinstance(v, str) and v:
                if " " in v and "T" not in v:
                    v = v.replace(" ", "T", 1)
                if not (v.endswith("Z") or "+" in v or "-" in v[10:]):
                    v = v + "Z"
                r["redeemed_at"] = v

        return jsonify({
            "success": True,
            "data": redemptions
        })
    except Exception as e:
        log.error(f"获取兑换记录失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/redemptions/<int:redemption_id>", methods=["DELETE"])
@require_admin
def admin_delete_redemption(redemption_id: int):
    """删除单条兑换记录"""
    try:
        ok = db.delete_redemption(redemption_id)
        if not ok:
            return jsonify({"success": False, "error": "兑换记录不存在"}), 404
        return jsonify({"success": True, "message": "删除成功"})
    except Exception as e:
        log.error(f"删除兑换记录失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/leases")
@require_admin
def admin_list_member_leases():
    """列出成员租约（到期/转移状态）"""
    try:
        limit = int(request.args.get("limit", 100))
        offset = int(request.args.get("offset", 0))
        rows = db.list_member_leases(limit=limit, offset=offset)

        # 状态翻译映射
        status_map = {
            "pending": "待加入",
            "active": "生效中",
            "transferring": "转移中",
            "failed": "失败",
            "cancelled": "已取消"
        }

        # 统一把 DATETIME 字符串转成 ISO 形式 + 中文化字段名和状态
        result = []
        for r in rows:
            # 时间格式化
            for k in ("created_at", "invited_at", "joined_at", "expires_at", "next_attempt_at", "last_synced_at", "updated_at"):
                v = r.get(k)
                if isinstance(v, str) and " " in v and "T" not in v:
                    r[k] = v.replace(" ", "T", 1)

            # 状态翻译
            status_raw = r.get("status", "")
            status_cn = status_map.get(status_raw, status_raw)

            # 保留原始英文字段 + 添加中文字段
            item = dict(r)  # 复制所有原始字段
            item.update({
                "邮箱": r.get("email"),
                "当前团队": r.get("team_name"),
                "状态": status_cn,
                "加入时间": r.get("joined_at"),
                "到期时间": r.get("expires_at"),
                "转移次数": r.get("transfer_count", 0)
            })
            result.append(item)

        return jsonify({"success": True, "data": result})
    except Exception as e:
        log.error(f"获取成员租约失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/leases", methods=["POST"])
@require_admin
def admin_upsert_member_lease():
    """手动录入/修正租约：用于将某邮箱纳入到期转移体系。"""
    try:
        payload = request.get_json(silent=True) or {}
        email = (payload.get("email") or "").strip().lower()
        team_name = (payload.get("team_name") or "").strip()
        join_at_raw = (payload.get("join_at") or "").strip()
        expires_at_raw = (payload.get("expires_at") or "").strip()

        if not email or not team_name:
            return jsonify({"success": False, "error": "email/team_name 不能为空"}), 400

        team_cfg = config.resolve_team(team_name) or {}
        team_account_id = team_cfg.get("account_id")

        join_at = None
        expires_at = None
        if expires_at_raw:
            try:
                from date_utils import parse_datetime_loose

                expires_at = parse_datetime_loose(expires_at_raw)
            except Exception:
                return jsonify({"success": False, "error": "expires_at 需要可解析时间，例如 2026-02-07T12:00:00 或 2026-02-07 12:00:00"}), 400

        if join_at_raw:
            try:
                from date_utils import parse_datetime_loose

                join_at = parse_datetime_loose(join_at_raw)
            except Exception:
                return jsonify({"success": False, "error": "join_at 需要可解析时间，例如 2026-01-07T12:00:00 或 2026-01-07 12:00:00"}), 400

            from date_utils import add_months_same_day

            term_months = int(os.getenv("AUTO_TRANSFER_TERM_MONTHS", "1") or 1)
            term_months = max(1, min(24, term_months))
            expires_at = expires_at or add_months_same_day(join_at, term_months)
        elif expires_at:
            # 小白模式：只填到期时间时，按“同日上个月”反推 join_at（可能不完全等价于真实加入时间）
            from date_utils import add_months_same_day

            term_months = int(os.getenv("AUTO_TRANSFER_TERM_MONTHS", "1") or 1)
            term_months = max(1, min(24, term_months))
            join_at = add_months_same_day(expires_at, -term_months)

        db.upsert_member_lease_manual(
            email=email,
            team_name=team_name,
            team_account_id=team_account_id,
            join_at=join_at,
            expires_at=expires_at,
        )
        msg = "管理员手动录入/更新"
        if join_at_raw == "" and expires_at_raw:
            msg += "（仅填 expires_at，已反推 join_at）"
        db.add_member_lease_event(email=email, action="manual_upsert", from_team=None, to_team=team_name, message=msg)
        return jsonify({"success": True, "message": "已录入"})
    except Exception as e:
        log.error(f"录入租约失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/leases/mark-joined", methods=["POST"])
@require_admin
def admin_mark_member_lease_joined():
    """手动标记某邮箱已加入（用于 members 不提供 join 时间字段的场景）。"""
    try:
        payload = request.get_json(silent=True) or {}
        email = (payload.get("email") or "").strip().lower()
        mode = (payload.get("mode") or "now").strip().lower()
        verify = payload.get("verify", True)

        if not email:
            return jsonify({"success": False, "error": "email 不能为空"}), 400

        lease = db.get_member_lease(email)
        if not lease:
            return jsonify({"success": False, "error": "租约不存在"}), 404

        team_name = (lease.get("team_name") or "").strip()
        team_cfg = config.resolve_team(team_name) or {}
        if verify:
            try:
                mi = get_member_info_for_email(team_cfg, email) if team_cfg else {"found": False, "error": "Team 配置不存在"}
            except Exception as e:
                mi = {"found": False, "error": str(e)}
            if not mi.get("found"):
                return jsonify({"success": False, "error": f"未在成员列表确认该邮箱已加入：{mi.get('error') or 'not found'}"}), 400

        join_at = None
        join_at_raw = (payload.get("join_at") or "").strip()
        if join_at_raw:
            try:
                from date_utils import parse_datetime_loose

                join_at = parse_datetime_loose(join_at_raw)
            except Exception:
                return jsonify({"success": False, "error": "join_at 需要可解析时间，例如 2026-01-07T12:00:00"}), 400
        else:
            if mode == "start_at":
                try:
                    start_at = lease.get("start_at")
                    if isinstance(start_at, str) and start_at:
                        join_at = datetime.fromisoformat(start_at.replace(" ", "T", 1))
                except Exception:
                    join_at = None
            join_at = join_at or datetime.now()

        from date_utils import add_months_same_day

        term_months = int(os.getenv("AUTO_TRANSFER_TERM_MONTHS", "1") or 1)
        term_months = max(1, min(24, term_months))
        expires_at = add_months_same_day(join_at, term_months)

        msg = f"管理员近似写入 join_at：{join_at.isoformat(sep=' ', timespec='seconds')}（mode={mode}）"
        if verify:
            msg += "；已通过成员列表确认已加入"

        db.update_member_lease_joined(
            email=email,
            join_at=join_at,
            expires_at=expires_at,
            from_team=team_name or None,
            event_action="joined_fallback_manual",
            event_message=msg,
        )
        return jsonify({"success": True, "message": "已写入 join_at（近似）"})
    except Exception as e:
        log.error(f"标记加入失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/leases/events")
@require_admin
def admin_list_member_lease_events():
    """列出租约事件"""
    try:
        email = request.args.get("email")
        limit = int(request.args.get("limit", 200))
        offset = int(request.args.get("offset", 0))
        rows = db.list_member_lease_events(email=email, limit=limit, offset=offset)
        for r in rows:
            v = r.get("created_at")
            # member_lease_events.created_at 来自 SQLite CURRENT_TIMESTAMP（UTC）
            if isinstance(v, str) and v:
                if " " in v and "T" not in v:
                    v = v.replace(" ", "T", 1)
                if not (v.endswith("Z") or "+" in v or "-" in v[10:]):
                    v = v + "Z"
                r["created_at"] = v
        return jsonify({"success": True, "data": rows})
    except Exception as e:
        log.error(f"获取租约事件失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/leases/sync-join", methods=["POST"])
@require_admin
def admin_sync_joined_leases():
    """手动触发：同步 awaiting_join 的 join_at"""
    try:
        payload = request.get_json(silent=True) or {}
        limit = int(payload.get("limit", 50))
        email = (payload.get("email") or "").strip().lower()
        if email:
            result = sync_joined_lease_for_email_once_detailed(email)
            ok = int((result or {}).get("synced") or 0) > 0
            reason = (result or {}).get("reason") or ""
            msg = "已同步该邮箱 join_at" if ok else f"未同步（{reason or 'unknown'}）"
            return jsonify({"success": True, "message": msg, "data": result})

        result = sync_joined_leases_once_detailed(limit=limit)
        msg = (
            f"已同步 {result.get('synced', 0)} 条（检查 {result.get('checked', 0)} 条）"
            + (f"，成员无时间 {result.get('member_no_time', 0)} 条" if result.get("member_no_time") else "")
            + (f"，members 错误 {result.get('member_errors', 0)} 条" if result.get("member_errors") else "")
            + (f"，invites 错误 {result.get('invite_errors', 0)} 条" if result.get("invite_errors") else "")
        )
        return jsonify({"success": True, "message": msg, "data": result})
    except Exception as e:
        log.error(f"同步加入时间失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/leases/run-transfer-once", methods=["POST"])
@require_admin
def admin_run_transfer_once():
    """手动触发：执行一轮到期转移"""
    try:
        payload = request.get_json(silent=True) or {}
        limit = int(payload.get("limit", 20))
        email = (payload.get("email") or "").strip().lower()
        if email:
            result = run_transfer_for_email(email)
            return jsonify({"success": True, "message": result.get("message", ""), "data": {"moved": result.get("moved", 0), **(result.get("data") or {})}})
        moved = run_transfer_once(limit=limit)
        return jsonify({"success": True, "message": f"本轮转移完成: {moved} 人", "data": {"moved": moved}})
    except Exception as e:
        log.error(f"执行转移失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/leases/force-expire", methods=["POST"])
@require_admin
def admin_force_expire_lease():
    """测试用：将指定邮箱租约标记为立即到期。"""
    try:
        payload = request.get_json(silent=True) or {}
        email = (payload.get("email") or "").strip().lower()
        if not email:
            return jsonify({"success": False, "error": "email 不能为空"}), 400
        db.force_expire_member_lease(email=email)
        db.add_member_lease_event(email=email, action="force_expire", from_team=None, to_team=None, message="管理员强制到期（测试）")
        return jsonify({"success": True, "message": "已强制到期"})
    except Exception as e:
        log.error(f"强制到期失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/leases/delete", methods=["POST"])
@require_admin
def admin_delete_lease():
    """删除租约记录（用于误添加的邮箱）"""
    try:
        payload = request.get_json(silent=True) or {}
        email = (payload.get("email") or "").strip().lower()
        delete_events = bool(payload.get("delete_events", True))
        if not email:
            return jsonify({"success": False, "error": "email 不能为空"}), 400

        lease = db.get_member_lease(email)
        if not lease:
            return jsonify({"success": False, "error": "租约不存在"}), 404

        ok = db.delete_member_lease(email=email, delete_events=delete_events)
        if not ok:
            return jsonify({"success": False, "error": "删除失败"}), 500

        return jsonify({"success": True, "message": f"已删除 {email} 的租约"})
    except Exception as e:
        log.error(f"删除租约失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/codes/<code>/status", methods=["PUT"])
@require_admin
def admin_update_code_status(code):
    """更新兑换码状态"""
    try:
        data = request.get_json()
        status = data.get("status")

        if status not in ["active", "disabled", "expired", "deleted", "used_up"]:
            return jsonify({"success": False, "error": "无效的状态"}), 400

        db.update_code_status(code, status)

        return jsonify({"success": True, "message": f"兑换码状态已更新为 {status}"})
    except Exception as e:
        log.error(f"更新兑换码状态失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/codes/<code>", methods=["DELETE"])
@require_admin
def admin_delete_code(code):
    """删除兑换码（默认软删除）"""
    try:
        hard = request.args.get("hard", "false").lower() in {"1", "true", "yes", "y", "on"}
        ok = db.delete_code(code, hard=hard)
        if not ok:
            return jsonify({"success": False, "error": "兑换码不存在"}), 404

        return jsonify({"success": True, "message": "删除成功" if not hard else "删除成功(含记录)"})
    except Exception as e:
        log.error(f"删除兑换码失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/codes/bulk-delete", methods=["POST"])
@require_admin
def admin_bulk_delete_codes():
    """批量删除兑换码（默认软删除，支持筛选）"""
    try:
        data = request.get_json() or {}
        confirm = (data.get("confirm") or "").strip()
        if confirm not in {"DELETE_ALL", "DELLT"}:
            return jsonify({"success": False, "error": "缺少确认字段 confirm=DELLT"}), 400

        team = (data.get("team") or "").strip()
        status = (data.get("status") or "").strip() or None
        include_deleted = bool(data.get("include_deleted", False))
        hard = bool(data.get("hard", False))

        codes = db.list_codes(team_name=None, status=status, include_deleted=include_deleted)

        if team:
            target_idx = _team_index_from_any_name(team)
            if target_idx is not None:
                codes = [c for c in codes if _team_index_from_any_name(c.get("team_name")) == target_idx]
            else:
                codes = [c for c in codes if (c.get("team_name") or "") == team]

        deleted = 0
        for c in codes:
            if db.delete_code(c.get("code"), hard=hard):
                deleted += 1

        return jsonify(
            {
                "success": True,
                "message": f"已删除 {deleted} 个兑换码" + ("（含记录）" if hard else ""),
                "data": {"deleted": deleted},
            }
        )
    except Exception as e:
        log.error(f"批量删除兑换码失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/redemptions/bulk-delete", methods=["POST"])
@require_admin
def admin_bulk_delete_redemptions():
    """批量删除兑换记录（支持按 team 精确匹配，可留空删除全部）"""
    try:
        data = request.get_json() or {}
        confirm = (data.get("confirm") or "").strip()
        if confirm not in {"DELETE_ALL", "DELLT"}:
            return jsonify({"success": False, "error": "缺少确认字段 confirm=DELLT"}), 400

        team = (data.get("team") or "").strip()
        names = [team] if team else None
        deleted = db.bulk_delete_redemptions(team_names=names)

        return jsonify(
            {"success": True, "message": f"已删除 {deleted} 条兑换记录", "data": {"deleted": deleted}}
        )
    except Exception as e:
        log.error(f"批量删除兑换记录失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== 兑换码分组管理 API ====================

@app.route("/api/admin/groups", methods=["GET"])
@require_admin
def admin_list_groups():
    """获取所有分组及其统计信息"""
    try:
        groups = db.list_code_groups()
        return jsonify({"success": True, "data": groups})
    except Exception as e:
        log.error(f"获取分组列表失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/groups", methods=["POST"])
@require_admin
def admin_create_group():
    """创建新分组"""
    try:
        data = request.get_json() or {}
        name = (data.get("name") or "").strip()
        description = (data.get("description") or "").strip()
        color = (data.get("color") or "#000000").strip()

        if not name:
            return jsonify({"success": False, "error": "分组名称不能为空"}), 400

        # 检查分组名称是否已存在
        existing = db.get_code_group_by_name(name)
        if existing:
            return jsonify({"success": False, "error": "分组名称已存在"}), 400

        group_id = db.create_code_group(name, description, color)
        return jsonify({
            "success": True,
            "message": "分组创建成功",
            "data": {"id": group_id, "name": name}
        })
    except Exception as e:
        log.error(f"创建分组失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/groups/<int:group_id>", methods=["PUT"])
@require_admin
def admin_update_group(group_id):
    """更新分组信息"""
    try:
        data = request.get_json() or {}
        name = data.get("name")
        description = data.get("description")
        color = data.get("color")

        if name is not None:
            name = name.strip()
            if not name:
                return jsonify({"success": False, "error": "分组名称不能为空"}), 400

            # 检查新名称是否与其他分组冲突
            existing = db.get_code_group_by_name(name)
            if existing and existing["id"] != group_id:
                return jsonify({"success": False, "error": "分组名称已存在"}), 400

        success = db.update_code_group(group_id, name, description, color)
        if success:
            return jsonify({"success": True, "message": "分组更新成功"})
        else:
            return jsonify({"success": False, "error": "分组不存在或未修改"}), 404
    except Exception as e:
        log.error(f"更新分组失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/groups/<int:group_id>", methods=["DELETE"])
@require_admin
def admin_delete_group(group_id):
    """删除分组"""
    try:
        data = request.get_json() or {}
        clear_codes = data.get("clear_codes", False)

        success = db.delete_code_group(group_id, clear_codes)
        if success:
            return jsonify({
                "success": True,
                "message": "分组删除成功" if not clear_codes else "分组删除成功，已清除兑换码的分组标记"
            })
        else:
            return jsonify({"success": False, "error": "分组不存在"}), 404
    except Exception as e:
        log.error(f"删除分组失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/codes/batch-group", methods=["POST"])
@require_admin
def admin_batch_update_code_group():
    """批量更新兑换码的分组"""
    try:
        data = request.get_json() or {}
        code_ids = data.get("code_ids", [])
        group_name = data.get("group_name")

        if not isinstance(code_ids, list) or not code_ids:
            return jsonify({"success": False, "error": "code_ids 必须是非空数组"}), 400

        # 如果指定了分组名称，检查分组是否存在
        if group_name:
            group = db.get_code_group_by_name(group_name)
            if not group:
                return jsonify({"success": False, "error": f"分组 '{group_name}' 不存在"}), 404

        updated = db.batch_update_code_group(code_ids, group_name)
        return jsonify({
            "success": True,
            "message": f"已更新 {updated} 个兑换码的分组",
            "data": {"updated": updated}
        })
    except Exception as e:
        log.error(f"批量更新兑换码分组失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== Team 管理 API ====================

@app.route("/api/admin/teams", methods=["GET"])
@require_admin
def admin_list_teams():
    """获取 Team 列表"""
    try:
        from team_manager import team_manager
        teams = team_manager.get_team_list()
        return jsonify({"success": True, "data": teams})
    except Exception as e:
        log.error(f"获取 Team 列表失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/teams", methods=["POST"])
@require_admin
def admin_add_team():
    """添加新 Team"""
    try:
        from team_manager import team_manager
        data = request.get_json()

        name = data.get("name", "").strip()
        email = data.get("email", "").strip()
        user_id = data.get("user_id", "").strip()
        account_id = data.get("account_id", "").strip()
        org_id = data.get("org_id", "").strip()
        access_token = data.get("access_token", "").strip()

        if not all([name, email, user_id, account_id, org_id, access_token]):
            return jsonify({"success": False, "error": "所有字段都不能为空"}), 400

        result = team_manager.add_team(name, email, user_id, account_id, org_id, access_token)

        if result["success"]:
            return jsonify(result), 201
        else:
            return jsonify(result), 500

    except Exception as e:
        log.error(f"添加 Team 失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/teams/<int:index>", methods=["PUT"])
@require_admin
def admin_update_team(index):
    """更新 Team 信息"""
    try:
        from team_manager import team_manager
        data = request.get_json()

        name = data.get("name", "").strip()
        email = data.get("email", "").strip()
        user_id = data.get("user_id", "").strip()
        account_id = data.get("account_id", "").strip()
        org_id = data.get("org_id", "").strip()
        access_token = data.get("access_token", "").strip() if data.get("access_token") else None

        if not all([name, email, user_id, account_id, org_id]):
            return jsonify({"success": False, "error": "基本字段不能为空"}), 400

        result = team_manager.update_team(index, name, email, user_id, account_id, org_id, access_token)

        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 404

    except Exception as e:
        log.error(f"更新 Team 失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/teams/<int:index>", methods=["DELETE"])
@require_admin
def admin_delete_team(index):
    """删除 Team"""
    try:
        from team_manager import team_manager

        cleanup = request.args.get("cleanup", "true").lower() in {"1", "true", "yes", "y", "on"}

        before = team_manager.get_team_list()
        if index < 0 or index >= len(before):
            return jsonify({"success": False, "error": f"Team 索引 {index} 不存在"}), 404
        team_name = before[index]["name"]
        fallback_name = f"Team{index+1}"

        result = team_manager.delete_team(index)

        if result["success"]:
            deleted_codes = 0
            deleted_stats = 0
            if cleanup:
                deleted_codes = db.soft_delete_codes_by_team_names([team_name, fallback_name])
                deleted_stats = db.delete_team_stats_by_names([team_name, fallback_name])

            return jsonify(
                {
                    **result,
                    "message": (result.get("message") or "删除成功")
                }
            )
    except Exception as e:
        log.error(f"删除 Team 失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/teams/<int:index>/sync-created-time", methods=["POST"])
@require_admin
def sync_team_created_time_api(index):
    """同步 Team 创建时间"""
    try:
        from team_manager import team_manager
        from team_service import sync_team_created_time

        teams = team_manager.get_team_list()
        if index < 0 or index >= len(teams):
            return jsonify({"success": False, "error": "Team 不存在"}), 404

        team = teams[index]
        team_name = team.get("name")

        result = sync_team_created_time(team_name)
        return jsonify(result)

    except Exception as e:
        log.error(f"同步 Team 创建时间失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/teams/<int:index>/generate-codes", methods=["POST"])
@require_admin
def admin_generate_codes_for_team(index):
    """为指定 Team 生成兑换码"""
    try:
        from team_manager import team_manager
        from code_generator import CodeGenerator

        data = request.get_json()
        count = int(data.get("count", 4))
        max_uses = int(data.get("max_uses", 1))
        expires_days = data.get("expires_days")  # None 表示永久有效
        requested_team_name = (data.get("team_name") or "").strip()
        auto_transfer_enabled = data.get("auto_transfer_enabled", True)  # 默认启用

        if count < 1 or count > 1000:
            return jsonify({"success": False, "error": "生成数量必须在 1-1000 之间"}), 400

        if max_uses < 1 or max_uses > 100:
            return jsonify({"success": False, "error": "最大使用次数必须在 1-100 之间"}), 400

        # 获取 Team 名称
        teams = team_manager.get_team_list()
        team_name = None

        # 1) 优先用索引（兼容旧前端）
        if 0 <= index < len(teams):
            team_name = teams[index]["name"]

        # 2) 如果前端传了 team_name，则用它做校验/兜底（避免索引漂移导致 404）
        if requested_team_name:
            if team_name and team_name != requested_team_name:
                # 索引可能已漂移：按名字重新查
                team_name = None
            if not team_name:
                matched = next((t for t in teams if (t.get("name") or "") == requested_team_name), None)
                if matched:
                    team_name = matched.get("name")

        if not team_name:
            return jsonify({"success": False, "error": f"Team 不存在（index={index}, team_name={requested_team_name or '-'}）"}), 404

        # 生成兑换码
        generator = CodeGenerator()
        codes = generator.generate_codes(
            team_name=team_name,
            count=count,
            max_uses=max_uses,
            expires_days=expires_days,
            auto_transfer_enabled=auto_transfer_enabled,
        )

        transfer_info = "（启用自动转移）" if auto_transfer_enabled else "（VIP 永久使用）"
        return jsonify({
            "success": True,
            "message": f"成功为 Team '{team_name}' 生成 {len(codes)} 个兑换码{transfer_info}",
            "data": {"codes": codes, "team_name": team_name}
        })

    except Exception as e:
        log.error(f"生成兑换码失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/teams/refresh-stats", methods=["POST"])
@require_admin
def admin_refresh_team_stats():
    """刷新所有 Team 的统计信息"""
    try:
        from team_manager import team_manager
        from team_service import get_team_stats
        import config

        teams = team_manager.get_team_list()
        refreshed = []

        for team_info in teams:
            team_name = team_info["name"]
            idx = team_info.get("index")

            # 优先按索引匹配 config.TEAMS，避免 team_names 漂移导致错配
            team_config = None
            if isinstance(idx, int) and 0 <= idx < len(config.TEAMS):
                team_config = config.TEAMS[idx]
            if not team_config:
                team_config = config.resolve_team(team_name)

            if not team_config:
                continue

            # 获取最新统计
            stats = get_team_stats(team_config)

            if stats:
                # 计算可用席位
                seats_entitled = stats.get("seats_entitled", 0)
                seats_in_use = stats.get("seats_in_use", 0)
                pending_invites = stats.get("pending_invites", 0)
                available = seats_entitled - seats_in_use - pending_invites

                # 更新数据库
                db.update_team_stats(
                    team_name=team_name,
                    total_seats=seats_entitled,
                    used_seats=seats_in_use,
                    pending_invites=pending_invites
                )

                refreshed.append({
                    "team": team_name,
                    "total_seats": seats_entitled,
                    "used_seats": seats_in_use,
                    "pending_invites": pending_invites,
                    "available_seats": available
                })

        return jsonify({
            "success": True,
            "message": f"成功刷新 {len(refreshed)} 个 Team 的统计信息",
            "data": refreshed
        })

    except Exception as e:
        log.error(f"刷新 Team 统计失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== 错误处理 ====================

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "接口不存在"}), 404


@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "服务器内部错误"}), 500


# ==================== 健康检查 ====================

@app.route("/health")
def health():
    """健康检查接口"""
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat()
    })


# ==================== 监控和告警 API ====================

@app.route("/api/admin/monitor/dashboard")
@require_admin
def monitor_dashboard():
    """获取监控仪表板数据"""
    try:
        data = monitor.get_dashboard_data()
        return jsonify({"success": True, "data": data})
    except Exception as e:
        log.error(f"获取监控数据失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/monitor/alerts")
@require_admin
def monitor_alerts():
    """获取告警列表"""
    try:
        limit = int(request.args.get("limit", 50))
        level = request.args.get("level")
        category = request.args.get("category")

        alerts = monitor.alert_manager.get_recent_alerts(
            limit=limit,
            level=level,
            category=category
        )

        return jsonify({"success": True, "alerts": alerts})
    except Exception as e:
        log.error(f"获取告警列表失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/monitor/alerts/<int:alert_id>/resolve", methods=["POST"])
@require_admin
def resolve_alert(alert_id):
    """标记告警为已解决"""
    try:
        resolved_by = request.json.get("resolved_by", "admin")
        monitor.alert_manager.resolve_alert(alert_id, resolved_by)

        return jsonify({"success": True, "message": "告警已标记为已解决"})
    except Exception as e:
        log.error(f"解决告警失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/monitor/check", methods=["POST"])
@require_admin
def run_monitor_check():
    """手动触发监控检查"""
    try:
        monitor.run_all_checks()
        return jsonify({"success": True, "message": "监控检查已完成"})
    except Exception as e:
        log.error(f"运行监控检查失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== 启动服务 ====================

def run_server(host="0.0.0.0", port=5000, debug=False):
    """启动Web服务器"""
    log.info(f"启动Web服务器: http://{host}:{port}", icon="start")
    log.info(f"用户兑换页面: http://{host}:{port}/")
    log.info(f"管理后台: http://{host}:{port}/admin")
    log.info(f"管理密码: {ADMIN_PASSWORD}", icon="code")

    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    # 从配置读取
    host = os.getenv("HOST") or config.get("web.host", "0.0.0.0")
    port = int(os.getenv("PORT") or config.get("web.port", 5000))
    debug = os.getenv("DEBUG", "").lower() in {"1", "true", "yes"} or config.get("web.debug", False)

    run_server(host=host, port=port, debug=debug)

