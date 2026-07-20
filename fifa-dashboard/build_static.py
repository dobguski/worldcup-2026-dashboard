#!/usr/bin/env python3
"""
静态仪表盘构建器
================
从 cache.json 读取最新数据 → 注入 dashboard.html 模板 → 输出最终文件

用法:
  python build_static.py                        # 构建到 fifa-dashboard/dashboard.html
  python build_static.py --target ../repo/      # 构建到指定目录 (如 worldcup-pages)
  python build_static.py --collect              # 先采集数据再构建
  python build_static.py --push                 # 构建 + 自动 git commit & push
"""
import json
import os
import sys
import re
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
CACHE_FILE = ROOT / "data" / "cache.json"
TEMPLATE_FILE = ROOT / "dashboard.html"

# ── 数据注入 ──────────────────────────────────────────────
def inject_data(template_path, cache_path, output_path):
    """将 cache.json 的数据注入到 HTML 模板的 DATA 块中"""
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    with open(cache_path, "r", encoding="utf-8") as f:
        cache = json.load(f)

    # 提取需要嵌入的数据（只取展示需要的字段）
    teams_data = []
    for i, t in enumerate(cache.get("teams", [])):
        teams_data.append({
            "rank": t.get("rank", i + 1), "team": t["team"], "flag": t.get("flag", ""),
            "prob": t["prob"], "trend": t.get("trend", "stable"),
            "note": t.get("note", ""),
        })

    # 构建冠军赔率映射 {team_name: prob}
    champ_odds = {}
    for t in cache.get("teams", []):
        champ_odds[t["team"].lower()] = t["prob"]
        # Also add Chinese name variants from hardcoded mapping
        TEAM_NAMES_CN = {
            "法国": "france", "阿根廷": "argentina", "西班牙": "spain",
            "英格兰": "england", "巴西": "brazil", "德国": "germany",
            "葡萄牙": "portugal", "荷兰": "netherlands", "哥伦比亚": "colombia",
            "美国": "usa", "墨西哥": "mexico", "比利时": "belgium",
            "挪威": "norway", "日本": "japan", "摩洛哥": "morocco",
            "瑞士": "switzerland", "克罗地亚": "croatia", "塞内加尔": "senegal",
            "厄瓜多尔": "ecuador", "加拿大": "canada", "巴拉圭": "paraguay",
            "加纳": "ghana", "阿尔及利亚": "algeria", "瑞典": "sweden",
            "奥地利": "austria", "澳大利亚": "australia", "埃及": "egypt",
            "佛得角": "cape verde", "南非": "south africa", "新西兰": "new zealand",
            "海地": "haiti", "科特迪瓦": "ivory coast", "土耳其": "turkiye",
            "乌拉圭": "uruguay", "韩国": "south korea", "捷克": "czechia",
            "波黑": "bosnia-herzegovina", "卡塔尔": "qatar", "沙特阿拉伯": "saudi arabia",
            "苏格兰": "scotland", "伊朗": "iran", "伊拉克": "iraq",
            "约旦": "jordan", "乌兹别克斯坦": "uzbekistan", "刚果民主": "congo dr",
            "巴拿马": "panama", "库拉索": "curacao", "突尼斯": "tunisia",
            "委内瑞拉": "venezuela", "智利": "chile", "秘鲁": "peru",
            "丹麦": "denmark", "意大利": "italy", "俄罗斯": "russia",
            "尼日利亚": "nigeria", "喀麦隆": "cameroon",
        }
        cn_name = t.get("team", "").lower()
        if cn_name in TEAM_NAMES_CN:
            champ_odds[TEAM_NAMES_CN[cn_name]] = t["prob"]

    def derive_prediction(home_cn, away_cn):
        """从冠军赔率推导比赛三项概率。回退公式：越高的冠军概率 → 越高的比赛胜率"""
        import math
        home_en = TEAM_NAMES_CN.get(home_cn, home_cn.lower())
        away_en = TEAM_NAMES_CN.get(away_cn, away_cn.lower())
        h_prob = champ_odds.get(home_en, 1.0)
        a_prob = champ_odds.get(away_en, 1.0)
        # 将冠军概率映射为比赛胜率 (log-scale Elo-like)
        total = h_prob + a_prob
        if total <= 0:
            return (33, 34, 33)  # 完全无法判断 → 均衡
        # 胜率 = 自身/(自身+对手)，加15%平局基数
        raw_h = h_prob / total * 85
        raw_a = a_prob / total * 85
        draw = 15
        # 归一化到100
        scale = 100 / (raw_h + raw_a + draw)
        return (round(raw_h * scale), round(draw * scale), round(raw_a * scale))

    matches_data = []
    for m in cache.get("matches", []):
        raw_score = str(m.get("score", "")).replace("None", "0").replace("null", "0")
        if raw_score in ("—", "", "None-None", "null-null"):
            raw_score = "0 - 0"
        pred_h = m.get("pred_home")
        pred_d = m.get("pred_draw")
        pred_a = m.get("pred_away")
        # ── P4: 智能回退 — 当 Polymarket 无赔率时从冠军赔率推导 ──
        favorite = m.get("favorite", "") or "N/A"
        favorite_prob = m.get("favorite_prob") or 0
        if pred_h is None or pred_h == "N/A":
            derived_h, derived_d, derived_a = derive_prediction(
                str(m.get("home", "")), str(m.get("away", ""))
            )
            pred_h = derived_h
            pred_d = derived_d
            pred_a = derived_a
            # 确定热门方
            max_prob = max(derived_h, derived_a)
            if derived_h >= derived_a:
                favorite = m.get("home", "")
                favorite_prob = derived_h
            else:
                favorite = m.get("away", "")
                favorite_prob = derived_a
        matches_data.append({
            "date": m["date"], "matchday": m.get("matchday", 0),
            "home": m["home"], "away": m["away"], "group": m.get("group", ""),
            "score": raw_score,
            "pred_home": pred_h if pred_h is not None else "N/A",
            "pred_draw": pred_d if pred_d is not None else "N/A",
            "pred_away": pred_a if pred_a is not None else "N/A",
            "favorite": favorite if favorite else "N/A",
            "favorite_prob": favorite_prob if favorite_prob else 0,
            "favorite_won": m.get("favorite_won") or False,
            "favorite": m.get("favorite") or "",
            "favorite_prob": m.get("favorite_prob") or 0,
            "volume": m.get("volume") or "N/A",
            "note": m.get("note", ""),
        })

    analysis_data = cache.get("analysis", {})

    # 构建新的 DATA 对象
    new_data = {
        "updated": cache.get("updated", datetime.now().strftime("%Y-%m-%d")),
        "total_volume": cache.get("total_volume", "N/A"),
        "others_prob": cache.get("others_prob", 0),
        "teams": teams_data,
        "matches": matches_data,
        "analysis": analysis_data,
    }

    new_data_json = json.dumps(new_data, ensure_ascii=False, indent=2)

    # 替换 HTML 中的 DATA 块
    # 使用字符串定位替换（避免 re.sub 的转义问题）
    start_marker = "const DATA = {"
    end_marker = "\n};"

    start_idx = html.find(start_marker)
    if start_idx == -1:
        print("❌ 未找到 'const DATA = {' 标记")
        return False

    # 找到对应的结束 };
    end_idx = html.find(end_marker, start_idx)
    if end_idx == -1:
        print("❌ 未找到 DATA 结束标记 '};' ")
        return False
    end_idx += len(end_marker)  # 包含 };

    new_data_str = f"const DATA = {new_data_json};"
    new_html = html[:start_idx] + new_data_str + html[end_idx:]

    # 更新 meta 中的日期
    today = datetime.now().strftime("%Y-%m-%d")
    new_html = re.sub(r'data-updated="[^"]*"', f'data-updated="{today}"', new_html)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(new_html)

    size_kb = len(new_html.encode("utf-8")) / 1024
    print(f"✅ 数据已注入 → {output_path} ({size_kb:.1f} KB)")
    print(f"   更新时间: {new_data['updated']}")
    print(f"   球队: {len(teams_data)} | 比赛: {len(matches_data)} | 分层: {len(analysis_data.get('tiers', []))}")
    return True


# ── Git 操作 (worldcup-pages 仓库) ─────────────────────────
def git_commit_and_push(repo_path, message=None):
    """在指定仓库中提交并推送"""
    if message is None:
        message = f"data: 数据更新 {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    try:
        cwd = os.getcwd()
        os.chdir(repo_path)

        subprocess.run(["git", "add", "dashboard.html"], check=True, capture_output=True)
        result = subprocess.run(["git", "commit", "-m", message], capture_output=True, text=True)

        if "nothing to commit" in result.stdout + result.stderr:
            print("📭 数据无变化，跳过提交")
            return True

        subprocess.run(["git", "push", "origin", "master"], check=True)
        print(f"🚀 已推送到 GitHub → datamenu.xyz 即将更新")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Git 操作失败: {e}")
        return False
    finally:
        os.chdir(cwd)


# ── 主入口 ─────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="静态仪表盘构建器")
    parser.add_argument("--target", "-t", help="输出目录 (如 worldcup-pages 仓库路径)")
    parser.add_argument("--collect", "-c", action="store_true", help="构建前先运行 collector 采集数据")
    parser.add_argument("--push", "-p", action="store_true", help="构建后自动 git commit & push")
    parser.add_argument("--message", "-m", help="Git commit message")
    args = parser.parse_args()

    # Step 0: 可选采集
    if args.collect:
        print("📡 采集数据...")
        collector = ROOT / "collector.py"
        if collector.exists():
            subprocess.run([sys.executable, str(collector), "--once"], check=False)
        else:
            print("⚠️ collector.py 未找到，跳过采集")

    # Step 1: 注入数据
    output_path = TEMPLATE_FILE  # 默认覆盖自身
    if args.target:
        target_dir = Path(args.target).resolve()
        if not target_dir.exists():
            print(f"❌ 目标目录不存在: {target_dir}")
            return 1
        output_path = target_dir / "dashboard.html"

    if not CACHE_FILE.exists():
        print(f"❌ 数据缓存不存在: {CACHE_FILE}")
        print("   请先运行: python collector.py --once")
        return 1

    ok = inject_data(TEMPLATE_FILE, CACHE_FILE, output_path)
    if not ok:
        return 1

    # Step 2: 可选推送
    if args.push:
        repo_path = args.target or ROOT
        git_commit_and_push(repo_path, args.message)

    return 0


if __name__ == "__main__":
    sys.exit(main())
