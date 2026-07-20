#!/usr/bin/env python3
"""
FIFA 2026 实时仪表盘 — Flask 主应用 (生产加固版)
=================================================
"""
import json
import os
import sys
import time
import hashlib
import threading
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from flask import Flask, jsonify, render_template, request

# ── 路径配置 ────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CACHE_FILE = DATA_DIR / "cache.json"
HISTORY_FILE = DATA_DIR / "history.jsonl"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── 自动播种默认数据 ─────────────────────────────────────
def _seed_default_cache():
    """如果缓存为空，用内置数据创建初始缓存"""
    if CACHE_FILE.exists():
        return
    import importlib.util
    # 尝试从 collector 导入数据
    try:
        spec = importlib.util.spec_from_file_location("collector", ROOT / "collector.py")
        collector = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(collector)
        default = {
            "updated": "2026-06-20",
            "source": "Polymarket (via Gate.com / KuCoin / BingX aggregation)",
            "total_volume": "$23.25亿",
            "teams": collector.CHAMPION_ODDS_SNAPSHOT["teams"],
            "others_prob": 5.5,
            "matches": collector.MATCHES_DATA,
            "analysis": collector.ANALYSIS_DATA,
        }
    except Exception:
        # 硬编码最小默认数据
        default = {
            "updated": "2026-06-20",
            "source": "Polymarket (built-in seed)",
            "total_volume": "$23.25亿",
            "teams": [
                {"rank":1,"team":"法国","flag":"🇫🇷","prob":18.0,"trend":"up","note":"Mbappé领军"},
                {"rank":2,"team":"西班牙","flag":"🇪🇸","prob":17.0,"trend":"up","note":"黄金一代"},
                {"rank":3,"team":"英格兰","flag":"🏴󠁧󠁢󠁥󠁮󠁧󠁿","prob":11.0,"trend":"down","note":"防守伤病"},
                {"rank":4,"team":"巴西","flag":"🇧🇷","prob":9.0,"trend":"down","note":"1-1平摩洛哥"},
                {"rank":5,"team":"葡萄牙","flag":"🇵🇹","prob":9.0,"trend":"stable","note":"C罗最后一届"},
            ],
            "others_prob": 51.0,
            "matches": [],
            "analysis": {"tiers":[],"brier_score":None,"summary":"数据初始化中"},
        }
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(default, f, ensure_ascii=False, indent=2)
    print("📦 已创建默认数据缓存")

_seed_default_cache()

# ── 环境检测 ────────────────────────────────────────────
IS_PRODUCTION = os.environ.get("RAILWAY_ENVIRONMENT", "") == "production" or \
                os.environ.get("FLASK_ENV", "") == "production"
IS_DEBUG = os.environ.get("FLASK_DEBUG", str(not IS_PRODUCTION)).lower() == "true"

# ── Builder 配置（环境变量优先） ─────────────────────────
def _load_builder_config():
    config = {
        "builder_name": os.environ.get("BUILDER_NAME", "dobguski"),
        "builder_code": os.environ.get("BUILDER_CODE", ""),
        "api_key": os.environ.get("BUILDER_API_KEY", ""),
        "secret": os.environ.get("BUILDER_SECRET", ""),
        "passphrase": os.environ.get("BUILDER_PASSPHRASE", ""),
    }
    if not config["api_key"]:
        config_file = ROOT / "builder_config.json"
        if config_file.exists():
            with open(config_file, "r", encoding="utf-8") as f:
                local = json.load(f)
                for k in config:
                    if not config[k]:
                        config[k] = local.get(k, "")
    return config

BUILDER = _load_builder_config()

# ── 交易保护密钥 ─────────────────────────────────────────
# 下单需要此 token，防止公开滥用
ORDER_AUTH_TOKEN = os.environ.get("ORDER_AUTH_TOKEN", "")
if not ORDER_AUTH_TOKEN and BUILDER.get("secret"):
    ORDER_AUTH_TOKEN = hashlib.sha256(BUILDER["secret"].encode()).hexdigest()[:16]

# ── 简易速率限制器 ───────────────────────────────────────
class RateLimiter:
    def __init__(self, max_requests=10, window_seconds=60):
        self.max = max_requests
        self.window = window_seconds
        self.hits = {}  # ip → [timestamps]
        self.lock = threading.Lock()

    def allow(self, ip):
        now = time.time()
        with self.lock:
            if ip not in self.hits:
                self.hits[ip] = []
            self.hits[ip] = [t for t in self.hits[ip] if now - t < self.window]
            if len(self.hits[ip]) >= self.max:
                return False
            self.hits[ip].append(now)
            return True

order_limiter = RateLimiter(max_requests=5, window_seconds=60)   # 5次/分钟
book_limiter = RateLimiter(max_requests=30, window_seconds=60)   # 30次/分钟

# ── Flask 应用初始化 ─────────────────────────────────────
app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False
app.config["TEMPLATES_AUTO_RELOAD"] = not IS_PRODUCTION

# 生产环境安全头
@app.after_request
def add_security_headers(response):
    if IS_PRODUCTION:
        response.headers["X-Content-Type-Options"] = "nosniff"
        pass  # X-Frame-Options removed to allow iframe embed on datamenu.xyz
        response.headers["X-Robots-Tag"] = "index, follow"
    return response

# ── 数据加载辅助 ─────────────────────────────────────────
def sanitize_score(raw):
    """Null值转0-0，—转0-0"""
    s = str(raw).replace("None", "0").replace("null", "0")
    if s in ("—", "", "None-None", "null-null"):
        return "0 - 0"
    return s

def sanitize_pred(val):
    """Null概率转N/A"""
    return val if val is not None else "N/A"

def load_cache():
    if CACHE_FILE.exists():
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def load_history():
    records = []
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    return records

# ── 页面路由 ─────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html", data=load_cache(), builder=BUILDER)

@app.route("/matches")
def matches():
    cache = load_cache()
    stats = {}
    if cache and cache.get("matches"):
        matches = cache["matches"]
        # 清洗比分数据：null/—/None → 0-0, null概率 → N/A
        for m in matches:
            s = str(m.get("score", "")).replace("None", "0").replace("null", "0")
            if s in ("—", "", "None-None", "null-null"):
                m["score"] = "0 - 0"
            else:
                m["score"] = s
            for k in ("pred_home", "pred_away", "pred_draw"):
                if m.get(k) is None:
                    m[k] = "N/A"
            if not m.get("favorite"):
                m["favorite"] = "N/A"
        fav_wins = sum(1 for m in matches if m.get("favorite_won"))
        stats = {
            "fav_wins": fav_wins,
            "fav_losses": len(matches) - fav_wins,
            "fav_win_rate": round(fav_wins / len(matches) * 100) if matches else 0,
        }
    return render_template("matches.html", data=cache, stats=stats, builder=BUILDER)

@app.route("/analysis")
def analysis():
    return render_template("analysis.html", data=load_cache(), builder=BUILDER)

@app.route("/embed")
def embed():
    """纯净版：无导航栏、无页脚，供 datamenu.xyz iframe 嵌入"""
    cache = load_cache()
    stats = {}
    if cache and cache.get("matches"):
        matches = cache["matches"]
        fav_wins = sum(1 for m in matches if m.get("favorite_won"))
        stats = {
            "fav_wins": fav_wins,
            "fav_losses": len(matches) - fav_wins,
            "fav_win_rate": round(fav_wins / len(matches) * 100) if matches else 0,
        }
    return render_template("embed.html", data=cache, stats=stats, builder=BUILDER)

# ── 公开 API ─────────────────────────────────────────────
@app.route("/api/odds")
def api_odds():
    cache = load_cache()
    if cache and "teams" in cache:
        return jsonify({
            "updated": cache.get("updated", "unknown"),
            "total_volume": cache.get("total_volume", "N/A"),
            "teams": cache["teams"],
            "others_prob": cache.get("others_prob", 0),
        })
    return jsonify({"error": "暂无数据", "teams": []}), 503

@app.route("/api/matches")
def api_matches():
    cache = load_cache()
    matches_data = cache.get("matches", []) if cache else []
    return jsonify({
        "updated": cache.get("updated", "unknown") if cache else "unknown",
        "total_tracked": len(matches_data),
        "total_wc_matches": 104,
        "matches": matches_data,
    })

@app.route("/api/analysis")
def api_analysis():
    cache = load_cache()
    analysis_data = cache.get("analysis", {}) if cache else {}
    return jsonify({
        "updated": cache.get("updated", "unknown") if cache else "unknown",
        "tiers": analysis_data.get("tiers", []),
        "brier_score": analysis_data.get("brier_score"),
        "summary": analysis_data.get("summary", ""),
    })

@app.route("/api/history")
def api_history():
    team = request.args.get("team", "")
    if not team:
        return jsonify({"error": "请指定球队名称"}), 400
    records = load_history()
    trend = []
    for r in records:
        ts = r.get("timestamp", r.get("updated", ""))
        for t in r.get("teams", []):
            if t.get("team") == team:
                trend.append({
                    "timestamp": ts, "prob": t.get("prob", 0),
                    "trend": t.get("trend", "stable"), "rank": t.get("rank", 0),
                })
                break
    return jsonify({"team": team, "data_points": len(trend), "trend": trend})

@app.route("/api/status")
def api_status():
    cache = load_cache()
    return jsonify({
        "status": "ok",
        "data_available": cache is not None,
        "last_updated": cache.get("updated", "never") if cache else "never",
        "history_snapshots": len(load_history()),
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "trading_enabled": bool(BUILDER.get("api_key") and ORDER_AUTH_TOKEN),
    })

# ── 交易端点（受保护）────────────────────────────────────
def _check_order_auth():
    """验证下单请求是否合法"""
    # 1. 速率限制
    ip = request.remote_addr or "unknown"
    if not order_limiter.allow(ip):
        return jsonify({"success": False, "error": "请求过于频繁，请稍后重试"}), 429

    # 2. Auth token 验证
    auth = request.headers.get("X-Order-Auth", "")
    if ORDER_AUTH_TOKEN and auth != ORDER_AUTH_TOKEN:
        return jsonify({"success": False, "error": "未授权"}), 401

    # 3. 交易开关
    if not BUILDER.get("api_key"):
        return jsonify({"success": False, "error": "交易功能未启用"}), 503

    return None  # 通过

@app.route("/api/order", methods=["POST"])
def api_order():
    """代理下单到 Polymarket CLOB API（受保护）"""
    # 安全校验
    auth_error = _check_order_auth()
    if auth_error:
        return auth_error

    data = request.get_json(silent=True) or {}
    token_id = (data.get("token_id") or "").strip()
    price = data.get("price")
    size = data.get("size")
    side = (data.get("side") or "BUY").upper()
    wallet_addr = (data.get("wallet_address") or "").strip()

    # 参数校验（统一错误消息，不泄露细节）
    if not all([token_id, price is not None, size is not None, wallet_addr]):
        return jsonify({"success": False, "error": "参数不完整"}), 400
    if side not in ("BUY", "SELL"):
        return jsonify({"success": False, "error": "参数无效"}), 400
    try:
        price_f = float(price)
        size_f = float(size)
        if not (0.01 <= price_f <= 1.0):
            return jsonify({"success": False, "error": "价格超出范围"}), 400
        if size_f <= 0:
            return jsonify({"success": False, "error": "数量无效"}), 400
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "参数格式错误"}), 400

    # 调用 CLOB API
    from polymarket_api import place_order
    result = place_order(
        token_id=token_id, price=price_f, size=size_f, side=side,
        api_key=BUILDER["api_key"], secret_b64=BUILDER["secret"],
        passphrase=BUILDER["passphrase"], wallet_address=wallet_addr,
        builder_code=BUILDER["builder_code"],
    )

    # 隐藏内部错误详情
    if not result.get("success"):
        err_msg = result.get("error", "")
        if IS_PRODUCTION and len(err_msg) > 100:
            err_msg = err_msg[:100] + "..."
        result["error"] = err_msg

    return jsonify(result)

@app.route("/api/book")
def api_book():
    ip = request.remote_addr or "unknown"
    if not book_limiter.allow(ip):
        return jsonify({"success": False, "error": "请求过于频繁"}), 429
    token_id = request.args.get("token_id", "").strip()
    if not token_id:
        return jsonify({"success": False, "error": "需要 token_id"}), 400
    from polymarket_api import get_order_book
    return jsonify(get_order_book(token_id))

# ── 钱包管理端点 ─────────────────────────────────────────
@app.route("/api/wallet/deploy", methods=["POST"])
def api_wallet_deploy():
    """为用户 EOA 部署 Safe 钱包"""
    data = request.get_json(silent=True) or {}
    eoa = (data.get("eoa_address") or "").strip()
    if not eoa or not eoa.startswith("0x"):
        return jsonify({"success": False, "error": "无效的钱包地址"}), 400

    from relayer import deploy_safe, get_safe_status

    # 先检查是否已部署
    status = get_safe_status(eoa, BUILDER["api_key"], BUILDER["secret"], BUILDER["passphrase"])
    if status.get("success") and status.get("data", {}).get("deployed"):
        safe_addr = status["data"].get("safeAddress", status["data"].get("address", ""))
        return jsonify({"success": True, "deployed": True, "safe_address": safe_addr})

    # 部署
    result = deploy_safe(eoa, BUILDER["api_key"], BUILDER["secret"], BUILDER["passphrase"])
    return jsonify(result)


@app.route("/api/wallet/status")
def api_wallet_status():
    """查询 Safe 部署状态 + 授权状态"""
    eoa = request.args.get("eoa", "").strip()
    if not eoa:
        return jsonify({"success": False, "error": "需要 eoa 参数"}), 400

    from relayer import get_safe_status, check_allowance
    from relayer import CTF_EXCHANGE, NEG_RISK_CTF, NEG_RISK_ADAPTER

    result = {"eoa": eoa, "safe_deployed": False, "safe_address": None, "approvals": {}}

    # Safe 状态
    safe = get_safe_status(eoa, BUILDER["api_key"], BUILDER["secret"], BUILDER["passphrase"])
    if safe.get("success"):
        data = safe.get("data", {})
        result["safe_deployed"] = data.get("deployed", False)
        result["safe_address"] = data.get("safeAddress") or data.get("address")

    safe_addr = result["safe_address"]
    if safe_addr:
        for name, spender in [("ctf_exchange", CTF_EXCHANGE),
                               ("neg_risk_ctf", NEG_RISK_CTF),
                               ("neg_risk_adapter", NEG_RISK_ADAPTER)]:
            r = check_allowance(safe_addr, spender)
            result["approvals"][name] = r.get("allowance", 0) if r.get("success") else 0

    return jsonify(result)


@app.route("/api/wallet/approve", methods=["POST"])
def api_wallet_approve():
    """批量设置代币授权"""
    data = request.get_json(silent=True) or {}
    safe_addr = (data.get("safe_address") or "").strip()
    if not safe_addr:
        return jsonify({"success": False, "error": "需要 safe_address"}), 400

    from relayer import build_approval_txs, execute_batch

    txs = build_approval_txs(safe_addr)
    result = execute_batch(txs, safe_addr, BUILDER["api_key"],
                           BUILDER["secret"], BUILDER["passphrase"])
    return jsonify(result)


# ── 错误处理 ─────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "not found"}) if request.path.startswith("/api") else \
           ('<h2>404</h2>', 404)

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "服务器内部错误"}) if request.path.startswith("/api") else \
           ('<h2>500</h2>', 500)

# ── 后台数据自动刷新 ─────────────────────────────────────
def _start_auto_refresh(interval_minutes=30):
    """后台线程定期刷新数据（默认30分钟）"""
    import threading, importlib.util
    def _refresh_loop():
        collector_path = ROOT / "collector.py"
        if not collector_path.exists():
            return
        # Run first collection immediately on startup
        first_run = True
        while True:
            if not first_run:
                time.sleep(interval_minutes * 60)
            first_run = False
            try:
                spec = importlib.util.spec_from_file_location("collector", collector_path)
                collector = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(collector)
                collector.collect()
            except Exception as e:
                print(f"[AUTO-REFRESH] 采集失败: {e}")
    t = threading.Thread(target=_refresh_loop, daemon=True)
    t.start()
    print(f"🔄 自动刷新已启动 (每 {interval_minutes} 分钟)")

# ── 启动后台刷新（模块级别，gunicorn 导入时即启动） ─────────
_start_auto_refresh()

# ── 启动入口 ─────────────────────────────────────────────
if __name__ == "__main__":
    print("⚽ DobGuski FIFA 2026 仪表盘启动中...")
    print(f"📍 http://localhost:5050")
    print(f"🔒 生产模式: {IS_PRODUCTION}")
    print(f"🛡️ 交易保护: {'已启用' if ORDER_AUTH_TOKEN else '已禁用'}")
    app.run(host="0.0.0.0", port=5050, debug=IS_DEBUG)
