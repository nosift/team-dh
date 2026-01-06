"""
Flask Web服务器
提供兑换码兑换的Web界面和API接口
"""

from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for
from functools import wraps
import secrets
from datetime import datetime
from redemption_service import RedemptionService
from database import db
from logger import log
import config


app = Flask(__name__)
app.secret_key = secrets.token_hex(32)  # 用于session加密

# 配置
ADMIN_PASSWORD = config.get("web.admin_password", "admin123")
ENABLE_ADMIN = config.get("web.enable_admin", True)


# ==================== 认证装饰器 ====================

def require_admin(f):
    """管理员认证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not ENABLE_ADMIN:
            return jsonify({"error": "管理后台已禁用"}), 403

        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated_function


# ==================== 用户API ====================

@app.route("/")
def index():
    """兑换页面"""
    with open("static/index.html", "r", encoding="utf-8") as f:
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

        # 获取客户端IP
        ip_address = request.remote_addr

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
        body { font-family: Arial; max-width: 400px; margin: 100px auto; padding: 20px; }
        input { width: 100%; padding: 10px; margin: 10px 0; }
        button { width: 100%; padding: 10px; background: #007bff; color: white; border: none; cursor: pointer; }
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
        body { font-family: Arial; max-width: 400px; margin: 100px auto; padding: 20px; }
        input { width: 100%; padding: 10px; margin: 10px 0; }
        button { width: 100%; padding: 10px; background: #007bff; color: white; border: none; cursor: pointer; }
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
        team_stats = db.list_team_stats()

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

        include_deleted = request.args.get("include_deleted", "false").lower() in {"1", "true", "yes", "y", "on"}
        codes = db.list_codes(team_name=team_name, status=status, include_deleted=include_deleted)

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

        return jsonify({
            "success": True,
            "data": redemptions
        })
    except Exception as e:
        log.error(f"获取兑换记录失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/codes/<code>/status", methods=["PUT"])
@require_admin
def admin_update_code_status(code):
    """更新兑换码状态"""
    try:
        data = request.get_json()
        status = data.get("status")

        if status not in ["active", "disabled", "expired", "deleted"]:
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
        result = team_manager.delete_team(index)

        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 404

    except Exception as e:
        log.error(f"删除 Team 失败: {e}")
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

        if count < 1 or count > 1000:
            return jsonify({"success": False, "error": "生成数量必须在 1-1000 之间"}), 400

        if max_uses < 1 or max_uses > 100:
            return jsonify({"success": False, "error": "最大使用次数必须在 1-100 之间"}), 400

        # 获取 Team 名称
        teams = team_manager.get_team_list()
        if index < 0 or index >= len(teams):
            return jsonify({"success": False, "error": f"Team 索引 {index} 不存在"}), 404

        team_name = teams[index]["name"]

        # 生成兑换码
        generator = CodeGenerator()
        codes = generator.generate_codes(
            team_name=team_name,
            count=count,
            max_uses=max_uses,
            expires_days=expires_days
        )

        return jsonify({
            "success": True,
            "message": f"成功为 Team '{team_name}' 生成 {len(codes)} 个兑换码",
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

            # 获取对应的team配置
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
    host = config.get("web.host", "0.0.0.0")
    port = config.get("web.port", 5000)
    debug = config.get("web.debug", False)

    run_server(host=host, port=port, debug=debug)
