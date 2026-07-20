#!/usr/bin/env python3
"""
fetch_matches_live.py — 实时比分三源客户端 v2.0
================================================
主源: ESPN API (免费, 无需key) — status, score, venue, broadcast
备源: worldcup26.ir — 104场比赛数据
热备: football-data.org — 10 req/min, 世界杯ID=WC

ESPN API: site.api.espn.com/sports/soccer/fifa.world/scoreboard
          dates=20260611-20260719
          返回: events[].competitions[].competitors[].score + status

用法:
  python scripts/fetch_matches_live.py          # 拉取实时比分
  python scripts/fetch_matches_live.py --json   # JSON输出
  python scripts/fetch_matches_live.py --live   # 仅进行中的比赛
"""
import json
import sys
import os
import gzip
import time
import urllib.request
import urllib.error
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAGE_DIR = os.path.join(ROOT, "_stage", "matches")
os.makedirs(STAGE_DIR, exist_ok=True)

UA = "DobGuski-FIFA-Live/2.0"
ESPN_API = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates=20260611-20260719"

def _safe_int(val):
    if val is None or val == "null" or val == "":
        return 0
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0

# ============================================================
# 主源: ESPN API (免费, 稳定, 官方数据)
# ============================================================
def fetch_espn():
    """ESPN FIFA World Cup scoreboard — 官方实时比分"""
    try:
        req = urllib.request.Request(ESPN_API, headers={
            "User-Agent": UA,
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            if raw[:2] == b'\x1f\x8b':  # gzip
                raw = gzip.decompress(raw)
            data = json.loads(raw.decode())

        events = data.get("events", [])
        results = []
        for e in events:
            comps = e.get("competitions", [{}])[0]
            competitors = comps.get("competitors", [{}, {}])
            home_team = competitors[0].get("team", {})
            away_team = competitors[1].get("team", {})
            home_score = _safe_int(competitors[0].get("score"))
            away_score = _safe_int(competitors[1].get("score"))

            status = e.get("status", {}).get("type", {})
            status_name = status.get("name", "STATUS_SCHEDULED")
            is_finished = status_name in ("STATUS_FULL_TIME", "STATUS_FINAL_PEN", "STATUS_FINAL_AET")
            is_live = not is_finished and status.get("state") == "in"

            results.append({
                "id": e.get("id", ""),
                "home": home_team.get("displayName", home_team.get("shortDisplayName", "")),
                "away": away_team.get("displayName", away_team.get("shortDisplayName", "")),
                "home_score": home_score,
                "away_score": away_score,
                "home_abbr": home_team.get("abbreviation", ""),
                "away_abbr": away_team.get("abbreviation", ""),
                "group": "",  # ESPN doesn't provide group info directly
                "matchday": "",
                "date": e.get("date", "")[:10],
                "finished": is_finished,
                "status": status.get("detail", status_name),
                "venue": comps.get("venue", {}).get("fullName", ""),
                "type": "knockout" if "Round of" in data.get("leagues",[{}])[0].get("season",{}).get("type",{}).get("name","") else "group",
            })

        live = [m for m in results if not m["finished"] and m["status"] not in ("Scheduled", "Pre-Game")]
        finished = [m for m in results if m["finished"]]

        return {
            "source": "ESPN API (site.api.espn.com)",
            "total": len(results),
            "live": len(live),
            "finished": len(finished),
            "matches": results,
        }, None
    except urllib.error.URLError as e:
        return None, f"ESPN network: {e.reason}"
    except Exception as e:
        return None, f"ESPN error: {str(e)[:100]}" if "gzip" not in str(e).lower() else None


# ============================================================
# 备源: worldcup26.ir (降级)
# ============================================================
def fetch_worldcup26():
    """worldcup26.ir 备源"""
    try:
        req = urllib.request.Request(
            "https://worldcup26.ir/get/games",
            headers={"User-Agent": UA, "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        games = data.get("games", []) if isinstance(data, dict) else data
        if not games:
            return None, "empty"

        results = []
        for g in games:
            results.append({
                "id": g.get("id", ""),
                "home": g.get("home_team_name_en", ""),
                "away": g.get("away_team_name_en", ""),
                "home_score": _safe_int(g.get("home_score")),
                "away_score": _safe_int(g.get("away_score")),
                "group": g.get("group", ""),
                "matchday": g.get("matchday", ""),
                "date": g.get("local_date", ""),
                "finished": g.get("finished") == "TRUE",
                "status": g.get("time_elapsed", "unknown"),
                "type": g.get("type", "group"),
            })

        live = [m for m in results if not m["finished"] and m["status"] not in ("notstarted", "unknown")]
        finished = [m for m in results if m["finished"]]
        return {
            "source": "worldcup26.ir",
            "total": len(results),
            "live": len(live),
            "finished": len(finished),
            "matches": results,
        }, None
    except urllib.error.URLError as e:
        return None, f"network: {e.reason}"
    except Exception as e:
        return None, str(e)[:100]


# ============================================================
# 三源聚合: ESPN优先 → worldcup26.ir → football-data.org
# ============================================================
def fetch_live_results(api_token=None):
    # 1. ESPN (主源)
    data, err = fetch_espn()
    if data and data["total"] > 0:
        return data

    # 2. worldcup26.ir (备源)
    if data is None:
        print(f"  ⚠️ ESPN 不可用 ({err}), 尝试 worldcup26.ir...", file=sys.stderr)
    data2, err2 = fetch_worldcup26()
    if data2 and data2["total"] > 0:
        return data2

    # 3. football-data.org (热备)
    if api_token:
        print(f"  ⚠️ worldcup26.ir 不可用 ({err2}), 尝试 football-data.org...", file=sys.stderr)
        data3, _ = fetch_football_data(api_token)
        if data3 and data3["total"] > 0:
            return data3

    return None


def fetch_football_data(api_token=None):
    """football-data.org 热备 (需要 API token)"""
    token = api_token or os.environ.get("FOOTBALL_DATA_TOKEN", "")
    if not token:
        return None, "no token"
    try:
        req = urllib.request.Request(
            "https://api.football-data.org/v4/competitions/WC/matches?status=SCHEDULED,LIVE,IN_PLAY,PAUSED,FINISHED",
            headers={"User-Agent": UA, "X-Auth-Token": token}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        results = []
        for m in data.get("matches", []):
            home = m.get("homeTeam", {}).get("name", "")
            away = m.get("awayTeam", {}).get("name", "")
            score = m.get("score", {}).get("fullTime", {})
            status = m.get("status", "SCHEDULED")
            results.append({
                "id": str(m.get("id", "")),
                "home": home, "away": away,
                "home_score": score.get("home", 0) or 0,
                "away_score": score.get("away", 0) or 0,
                "group": m.get("group", "").replace("GROUP_", ""),
                "date": m.get("utcDate", "")[:10],
                "finished": status == "FINISHED",
                "status": status.lower(),
                "type": "group",
            })
        live = [m for m in results if m["status"] in ("live", "in_play", "paused")]
        return {
            "source": "football-data.org",
            "total": len(results),
            "live": len(live),
            "matches": results,
        }, None
    except Exception as e:
        return None, str(e)[:100]


# ============================================================
def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--token", type=str, default=None)
    args = ap.parse_args()

    data = fetch_live_results(api_token=args.token)
    if not data:
        print(json.dumps({"error": "all sources failed"}, ensure_ascii=False))
        return 1

    ts = datetime.now().strftime("%Y%m%d_%H%M")
    path = os.path.join(STAGE_DIR, f"live_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    if args.live:
        output = {"source": data["source"], "live": [m for m in data["matches"] if not m["finished"] and m["status"] not in ("notstarted", "", "Scheduled")]}
    else:
        output = data

    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"📡 {data['source']} | 总:{data['total']} | 进行:{data['live']} | 完赛:{data['finished']}")
        live_matches = [m for m in data["matches"] if not m["finished"] and m["status"] not in ("notstarted", "", "Scheduled")]
        finished_matches = [m for m in data["matches"] if m["finished"]]
        if live_matches:
            print("\n⚽ 进行中:")
            for m in live_matches:
                print(f"  {m['home']} {m['home_score']}-{m['away_score']} {m['away']} [{m['status']}]")
        if finished_matches[-5:]:
            print("\n✅ 最近完赛:")
            for m in finished_matches[-5:]:
                print(f"  {m['date']} {m['home']} {m['home_score']}-{m['away_score']} {m['away']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
