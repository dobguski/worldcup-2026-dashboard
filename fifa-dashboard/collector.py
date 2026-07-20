#!/usr/bin/env python3
"""
FIFA 2026 数据采集引擎
======================
数据源优先级（按可靠性排序）：
1. ✅ CLOB API — /midpoint 实时成交价（通过 Gamma /events?tag_slug=2026-fifa-world-cup 获取token_id）
2. Gamma API — outcomePrices 作为回退
3. 手动维护的比赛结果 — 从分析报告提取的结构化数据

用法：
  python collector.py --once     # 采集一次，写入 data/
  python collector.py --daemon   # 持续采集，每30分钟一次
  python collector.py --report   # 输出可直接用于报告的 Markdown
"""
import json
import os
import sys
import time
import argparse
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CACHE_FILE = DATA_DIR / "cache.json"
HISTORY_FILE = DATA_DIR / "history.jsonl"

# 确保 data 目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# 内置数据：冠军赔率快照（最新已知数据，来自聚合站报道）
# 更新方式：每周至少一次 WebSearch 刷新
# ============================================================
CHAMPION_ODDS_SNAPSHOT = {
    "updated": "2026-06-20",
    "source": "Polymarket (via Gate.com / KuCoin / BingX aggregation)",
    "total_volume": "$23.25亿",
    "teams": [
        {"rank": 1,  "team": "法国",     "flag": "🇫🇷", "prob": 18.0, "trend": "up",
         "note": "Mbappé领军，小组赛首战3-0完胜"},
        {"rank": 2,  "team": "西班牙",   "flag": "🇪🇸", "prob": 17.0, "trend": "up",
         "note": "黄金一代，赔率稳步上升"},
        {"rank": 3,  "team": "英格兰",   "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "prob": 11.0, "trend": "down",
         "note": "防守端伤病困扰，价格下滑"},
        {"rank": 4,  "team": "巴西",     "flag": "🇧🇷", "prob": 9.0,  "trend": "down",
         "note": "1-1平摩洛哥 + 核心伤病"},
        {"rank": 5,  "team": "葡萄牙",   "flag": "🇵🇹", "prob": 9.0,  "trend": "stable",
         "note": "C罗最后一届，阵容深度良好"},
        {"rank": 6,  "team": "阿根廷",   "flag": "🇦🇷", "prob": 8.0,  "trend": "stable",
         "note": "卫冕冠军，尚未出战"},
        {"rank": 7,  "team": "德国",     "flag": "🇩🇪", "prob": 5.0,  "trend": "up",
         "note": "7-1大胜后信心飙升"},
        {"rank": 8,  "team": "挪威",     "flag": "🇳🇴", "prob": 3.0,  "trend": "stable",
         "note": "Haaland效应持续"},
        {"rank": 9,  "team": "荷兰",     "flag": "🇳🇱", "prob": 3.0,  "trend": "down",
         "note": "2-2被日本逼平后下滑"},
        {"rank": 10, "team": "美国",     "flag": "🇺🇸", "prob": 2.0,  "trend": "up",
         "note": "4-1大胜巴拉圭，东道主溢价"},
        {"rank": 11, "team": "哥伦比亚", "flag": "🇨🇴", "prob": 2.0,  "trend": "stable",
         "note": "南美黑马，小组赛表现稳定"},
        {"rank": 12, "team": "日本",     "flag": "🇯🇵", "prob": 2.0,  "trend": "up",
         "note": "2-2逼平荷兰，亚洲之光"},
        {"rank": 13, "team": "摩洛哥",   "flag": "🇲🇦", "prob": 2.0,  "trend": "up",
         "note": "1-1逼平巴西，非洲黑马"},
        {"rank": 14, "team": "墨西哥",   "flag": "🇲🇽", "prob": 1.5,  "trend": "up",
         "note": "2-0完胜南非，揭幕战表现亮眼"},
        {"rank": 15, "team": "比利时",   "flag": "🇧🇪", "prob": 1.0,  "trend": "stable",
         "note": "黄金一代逐渐老去"},
        {"rank": 16, "team": "克罗地亚", "flag": "🇭🇷", "prob": 1.0,  "trend": "stable",
         "note": "魔笛最后一届世界杯"},
    ],
    "others_prob": 5.5,
}

# ============================================================
# 比赛数据：从分析报告提取（v1.2，10场比赛）
# ============================================================
# 比赛数据从 scripts/fetch_matches.py 导入（单一数据源）
# 在 Railway 部署环境中 scripts/ 可能不在构建上下文中，提供 fallback
try:
    import importlib.util
    _fm_path = ROOT.parent / "scripts" / "fetch_matches.py"
    if _fm_path.exists():
        _fm_spec = importlib.util.spec_from_file_location(
            "fetch_matches", str(_fm_path))
        _fm = importlib.util.module_from_spec(_fm_spec)
        _fm_spec.loader.exec_module(_fm)
        MATCHES_RAW = _fm.KNOWN_MATCHES
    else:
        raise FileNotFoundError("scripts/fetch_matches.py not in build context")
except Exception:
    # Fallback: minimal match data for Railway environment (must be list of dicts)
    MATCHES_RAW = [
        {"home":"墨西哥","away":"南非",    "score":"2-0","stage":"Group A","group":"A","date":"2026-06-11","note":"揭幕战"},
        {"home":"加拿大","away":"波黑",    "score":"1-1","stage":"Group B","group":"B","date":"2026-06-12","note":""},
        {"home":"巴西",  "away":"摩洛哥",  "score":"1-1","stage":"Group C","group":"C","date":"2026-06-13","note":""},
        {"home":"美国",  "away":"巴拉圭",  "score":"4-1","stage":"Group D","group":"D","date":"2026-06-14","note":""},
        {"home":"德国",  "away":"库拉索",  "score":"7-1","stage":"Group E","group":"E","date":"2026-06-15","note":""},
        {"home":"荷兰",  "away":"日本",    "score":"2-2","stage":"Group F","group":"F","date":"2026-06-16","note":""},
    ]

# 补充概率数据（仅前10场有Polymarket赛前概率）
PROB_DATA = {
    ("墨西哥","南非"):    {"pred_home":70,"pred_draw":21,"pred_away":9, "favorite":"墨西哥","favorite_prob":70,"favorite_won":True,"volume":"$186万"},
    ("韩国","捷克"):      {"pred_home":38,"pred_draw":32,"pred_away":33,"favorite":"韩国","favorite_prob":38,"favorite_won":True,"volume":"$107万"},
    ("加拿大","波黑"):    {"pred_home":54,"pred_draw":23,"pred_away":23,"favorite":"加拿大","favorite_prob":54,"favorite_won":False},
    ("美国","巴拉圭"):    {"pred_home":50,"pred_draw":28,"pred_away":22,"favorite":"美国","favorite_prob":50,"favorite_won":True,"volume":"$60.6万"},
    ("卡塔尔","瑞士"):    {"pred_home":7,"pred_draw":14,"pred_away":79,"favorite":"瑞士","favorite_prob":79,"favorite_won":False},
    ("巴西","摩洛哥"):    {"pred_home":84,"pred_draw":10,"pred_away":6,"favorite":"巴西","favorite_prob":84,"favorite_won":False},
    ("海地","苏格兰"):    {"pred_home":17,"pred_draw":24,"pred_away":64,"favorite":"苏格兰","favorite_prob":64,"favorite_won":True},
    ("澳大利亚","土耳其"):{"pred_home":19,"pred_draw":26,"pred_away":57,"favorite":"土耳其","favorite_prob":57,"favorite_won":False},
    ("德国","库拉索"):    {"pred_home":94,"pred_draw":4,"pred_away":2,"favorite":"德国","favorite_prob":94,"favorite_won":True},
    ("荷兰","日本"):      {"pred_home":48,"pred_draw":26,"pred_away":26,"favorite":"荷兰","favorite_prob":48,"favorite_won":False},
}

# 组装完整比赛数据
MATCHES_DATA = []
for m in MATCHES_RAW:
    entry = {
        "date": m["date"], "matchday": 0, "stage": m.get("stage","小组赛"),
        "home": m["home"], "away": m["away"], "group": m["group"],
        "score": m["score"], "result": "",
        "pred_home": None, "pred_draw": None, "pred_away": None,
        "favorite": "", "favorite_prob": 0, "favorite_won": None,
        "volume": "", "note": m.get("note",""),
    }
    # 查找概率数据
    prob = PROB_DATA.get((m["home"], m["away"])) or PROB_DATA.get((m["away"], m["home"]))
    if prob:
        entry.update(prob)
    MATCHES_DATA.append(entry)

# 

# ============================================================
# 分层分析数据（从报告 §2 计算得出）
# ============================================================
ANALYSIS_DATA = {
    "tiers": [
        {"label": "超级热门 (>75%)", "color": "super", "count": 3, "wins": 1, "rate": 33.3,
         "examples": "德国✅、巴西❌、瑞士❌"},
        {"label": "中强热门 (60-75%)", "color": "strong", "count": 2, "wins": 2, "rate": 100.0,
         "examples": "墨西哥✅、苏格兰✅"},
        {"label": "温和热门 (50-60%)", "color": "mild", "count": 3, "wins": 1, "rate": 33.3,
         "examples": "加拿大❌、美国✅、土耳其❌"},
        {"label": "微弱优势 (35-50%)", "color": "weak", "count": 2, "wins": 2, "rate": 100.0,
         "examples": "韩国✅、荷兰❌"},
    ],
    "brier_score": 0.303,
    "brier_baseline": 0.25,
    "summary": (
        "10场比赛中热门获胜5场（50%），与抛硬币基线一致。"
        "超级热门（>75%）翻车率67%（仅德国取胜），中强热门（60-75%）是当前唯一甜点区（100%命中）。"
        "整体Brier Score 0.303，校准度略低于随机基线（0.25），样本量小需持续追踪。"
    ),
}


def try_gamma_api():
    """从 Gamma API + CLOB midpoint 获取实时冠军赔率"""
    import urllib.request
    import urllib.error

    # Step 1: Gamma 获取 World Cup Winner event
    url = "https://gamma-api.polymarket.com/events?tag_slug=2026-fifa-world-cup&active=true&limit=5"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "DobGuski-FIFA-Dashboard/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            events = json.loads(resp.read().decode())
    except Exception as e:
        print(f"  ⚠️ Gamma API: {e}")
        return None

    winner_event = next((e for e in events if 'Winner' in e.get('title', '')), None)
    if not winner_event:
        return None

    markets = winner_event.get('markets', [])
    total_vol = winner_event.get('volume24hr', 0)
    print(f"  ✅ Gamma: {len(markets)} 个冠军市场, 24h量=${total_vol:,.0f}")

    # Step 2: 并行获取 CLOB midpoint (ThreadPoolExecutor, 10 workers)
    from polymarket_api import get_midpoint
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def fetch_one(m):
        q = m.get('question', '')
        team = q.replace('Will ', '').replace(' win the 2026 FIFA World Cup?', '')
        tokens = json.loads(m.get('clobTokenIds', '[]')) if isinstance(m.get('clobTokenIds'), str) else m.get('clobTokenIds', [])
        token_id = tokens[0] if tokens else None
        pct = None
        if token_id:
            r = get_midpoint(token_id)
            if r.get('success') and r.get('data'):
                pct = round(float(r['data'].get('mid', 0)) * 100, 1)
        if pct is None:
            prices = json.loads(m.get('outcomePrices', '[]')) if isinstance(m.get('outcomePrices'), str) else m.get('outcomePrices', [])
            pct = round(float(prices[0]) * 100, 1) if len(prices) > 0 else 0
        vol = float(m.get('volume24hr', 0) or 0)
        return {'team': team, 'prob': pct, 'token_id': token_id, 'vol': vol}

    teams = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(fetch_one, m): m for m in markets}
        for f in as_completed(futures):
            teams.append(f.result())

    teams.sort(key=lambda x: x['prob'], reverse=True)
    return {
        'source': 'CLOB midpoint (via Gamma tag_slug=2026-fifa-world-cup)',
        'total_volume_24h': total_vol,
        'teams': teams,
        'top16_share': round(sum(t['prob'] for t in teams[:16]), 1),
        'others_share': round(sum(t['prob'] for t in teams[16:]), 1),
    }


def collect():
    """执行一次完整数据采集"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] 🔄 数据采集开始...")

    # 1. 尝试 Gamma + CLOB 实时数据
    live_data = try_gamma_api()
    if live_data:
        print(f"  ✅ 实时数据: {len(live_data['teams'])} 队, Top16={live_data['top16_share']}%")
        teams_data = live_data['teams']
        src = live_data['source']
        total_vol = f"${live_data['total_volume_24h']:,.0f}"
        others = live_data['others_share']
    else:
        print("  📡 使用内置快照数据")
        teams_data = CHAMPION_ODDS_SNAPSHOT["teams"]
        src = CHAMPION_ODDS_SNAPSHOT["source"]
        total_vol = CHAMPION_ODDS_SNAPSHOT["total_volume"]
        others = CHAMPION_ODDS_SNAPSHOT["others_prob"]

    # 2. 组装缓存数据
    cache = {
        "updated": datetime.now().strftime("%Y-%m-%d"),
        "source": src,
        "total_volume": total_vol,
        "teams": teams_data,
        "others_prob": others,
        "matches": MATCHES_DATA,
        "analysis": ANALYSIS_DATA,
        "collector_timestamp": timestamp,
    }

    # 3. 写入缓存
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    print(f"  📄 缓存已写入: {CACHE_FILE}")

    # 4. 追加历史记录
    history_entry = {
        "timestamp": timestamp,
        "teams": teams_data,
        "total_volume": total_vol,
    }
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(history_entry, ensure_ascii=False) + "\n")
    print(f"  📜 历史已追加: {HISTORY_FILE}")

    return cache


def daemon_mode(interval_sec=1800):
    """持续采集模式（默认30分钟）"""
    print(f"🔄 守护进程启动，采集间隔: {interval_sec}秒 ({interval_sec//60}分钟)")
    print(f"按 Ctrl+C 停止...")
    try:
        while True:
            collect()
            print(f"  ⏳ 等待 {interval_sec}秒...")
            time.sleep(interval_sec)
    except KeyboardInterrupt:
        print("\n👋 守护进程已停止")


def main():
    parser = argparse.ArgumentParser(description="FIFA 2026 数据采集引擎")
    parser.add_argument("--once", action="store_true", help="采集一次后退出")
    parser.add_argument("--daemon", action="store_true", help="持续采集模式")
    parser.add_argument("--interval", type=int, default=1800, help="采集间隔（秒），默认1800")
    args = parser.parse_args()

    if args.daemon:
        daemon_mode(args.interval)
    else:
        # 默认 --once
        cache = collect()
        print(f"\n✅ 数据采集完成")
        print(f"   更新时间: {cache['updated']}")
        print(f"   冠军赔率: {len(cache['teams'])} 支球队")
        print(f"   比赛记录: {len(cache['matches'])} 场")
        print(f"   分层分析: {len(cache['analysis']['tiers'])} 个层级")
        print(f"\n💡 启动仪表盘: cd fifa-dashboard && python app.py")


if __name__ == "__main__":
    main()
