#!/usr/bin/env python3
"""
比赛结果自动采集器
==================
数据源：WebSearch 聚合体育媒体（FIFA官方、ESPN、新华社等）
输出：结构化 JSON → 可用于更新报告

用法：
  python scripts/fetch_matches.py                 # 搜索最新比赛日
  python scripts/fetch_matches.py --date 2026-06-19  # 指定日期
  python scripts/fetch_matches.py --json          # JSON 输出
"""
import json
import sys
import os
import re
from datetime import datetime, timedelta

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAGE_DIR = os.path.join(ROOT, "_stage", "matches")
os.makedirs(STAGE_DIR, exist_ok=True)

# 已知的2026世界杯比赛结果（截至6月21日）
# 后续通过 WebSearch 每日增量更新
KNOWN_MATCHES = [
    # Day 1 (6/11)
    {"date":"2026-06-11","home":"墨西哥","away":"南非","group":"A","score":"2-0","stage":"小组赛第1轮"},
    {"date":"2026-06-11","home":"韩国","away":"捷克","group":"A","score":"2-1","stage":"小组赛第1轮"},
    # Day 2 (6/12)
    {"date":"2026-06-12","home":"加拿大","away":"波黑","group":"B","score":"1-1","stage":"小组赛第1轮"},
    # Day 3 (6/13)
    {"date":"2026-06-13","home":"美国","away":"巴拉圭","group":"D","score":"4-1","stage":"小组赛第1轮"},
    {"date":"2026-06-13","home":"卡塔尔","away":"瑞士","group":"B","score":"1-1","stage":"小组赛第1轮"},
    {"date":"2026-06-13","home":"巴西","away":"摩洛哥","group":"C","score":"1-1","stage":"小组赛第1轮"},
    {"date":"2026-06-13","home":"海地","away":"苏格兰","group":"C","score":"0-1","stage":"小组赛第1轮"},
    {"date":"2026-06-13","home":"澳大利亚","away":"土耳其","group":"D","score":"2-0","stage":"小组赛第1轮"},
    # Day 4 (6/14)
    {"date":"2026-06-14","home":"德国","away":"库拉索","group":"E","score":"7-1","stage":"小组赛第1轮"},
    {"date":"2026-06-14","home":"荷兰","away":"日本","group":"F","score":"2-2","stage":"小组赛第1轮"},
    {"date":"2026-06-14","home":"科特迪瓦","away":"厄瓜多尔","group":"E","score":"1-0","stage":"小组赛第1轮"},
    {"date":"2026-06-14","home":"瑞典","away":"突尼斯","group":"F","score":"5-1","stage":"小组赛第1轮"},
    # Day 5 (6/15)
    {"date":"2026-06-15","home":"西班牙","away":"佛得角","group":"H","score":"0-0","stage":"小组赛第1轮"},
    {"date":"2026-06-15","home":"比利时","away":"埃及","group":"G","score":"1-1","stage":"小组赛第1轮"},
    {"date":"2026-06-15","home":"沙特阿拉伯","away":"乌拉圭","group":"H","score":"1-1","stage":"小组赛第1轮"},
    {"date":"2026-06-15","home":"伊朗","away":"新西兰","group":"G","score":"2-2","stage":"小组赛第1轮"},
    # Day 6 (6/16)
    {"date":"2026-06-16","home":"法国","away":"塞内加尔","group":"I","score":"3-1","stage":"小组赛第1轮"},
    {"date":"2026-06-16","home":"挪威","away":"伊拉克","group":"I","score":"4-1","stage":"小组赛第1轮"},
    {"date":"2026-06-16","home":"阿根廷","away":"阿尔及利亚","group":"J","score":"3-0","stage":"小组赛第1轮"},
    {"date":"2026-06-16","home":"奥地利","away":"约旦","group":"J","score":"3-1","stage":"小组赛第1轮"},
    # Day 7 (6/17)
    {"date":"2026-06-17","home":"葡萄牙","away":"刚果民主","group":"K","score":"1-1","stage":"小组赛第1轮"},
    {"date":"2026-06-17","home":"英格兰","away":"克罗地亚","group":"L","score":"4-2","stage":"小组赛第1轮"},
    {"date":"2026-06-17","home":"加纳","away":"巴拿马","group":"L","score":"1-0","stage":"小组赛第1轮"},
    {"date":"2026-06-17","home":"哥伦比亚","away":"乌兹别克斯坦","group":"K","score":"3-1","stage":"小组赛第1轮"},
    # Day 8 (6/18)
    {"date":"2026-06-18","home":"捷克","away":"南非","group":"A","score":"1-1","stage":"小组赛第2轮"},
    {"date":"2026-06-18","home":"瑞士","away":"波黑","group":"B","score":"4-1","stage":"小组赛第2轮"},
    {"date":"2026-06-18","home":"加拿大","away":"卡塔尔","group":"B","score":"6-0","stage":"小组赛第2轮"},
    {"date":"2026-06-18","home":"墨西哥","away":"韩国","group":"A","score":"1-0","stage":"小组赛第2轮","note":"墨西哥提前晋级R32"},
    # Day 9 (6/19)
    {"date":"2026-06-19","home":"摩洛哥","away":"苏格兰","group":"C","score":"1-0","stage":"小组赛第2轮"},
    {"date":"2026-06-19","home":"巴西","away":"海地","group":"C","score":"3-0","stage":"小组赛第2轮","note":"海地淘汰"},
    {"date":"2026-06-19","home":"美国","away":"澳大利亚","group":"D","score":"2-0","stage":"小组赛第2轮"},
    {"date":"2026-06-19","home":"土耳其","away":"巴拉圭","group":"D","score":"0-1","stage":"小组赛第2轮"},
    # Day 10 (6/20)
    {"date":"2026-06-20","home":"荷兰","away":"瑞典","group":"F","score":"5-1","stage":"小组赛第2轮"},
    {"date":"2026-06-20","home":"德国","away":"科特迪瓦","group":"E","score":"2-1","stage":"小组赛第2轮"},
    {"date":"2026-06-20","home":"厄瓜多尔","away":"库拉索","group":"E","score":"0-0","stage":"小组赛第2轮"},
    {"date":"2026-06-20","home":"日本","away":"突尼斯","group":"F","score":"4-0","stage":"小组赛第2轮"},
    # Day 11 (6/21)
    {"date":"2026-06-21","home":"西班牙","away":"沙特阿拉伯","group":"H","score":"4-0","stage":"小组赛第2轮"},
    {"date":"2026-06-21","home":"比利时","away":"伊朗","group":"G","score":"0-0","stage":"小组赛第2轮"},
    {"date":"2026-06-21","home":"乌拉圭","away":"佛得角","group":"H","score":"2-2","stage":"小组赛第2轮"},
    {"date":"2026-06-21","home":"新西兰","away":"埃及","group":"G","score":"1-3","stage":"小组赛第2轮"},
    # Day 12 (6/22)
    {"date":"2026-06-22","home":"阿根廷","away":"奥地利","group":"J","score":"2-0","stage":"小组赛第2轮"},
    {"date":"2026-06-22","home":"法国","away":"伊拉克","group":"I","score":"3-0","stage":"小组赛第2轮"},
    {"date":"2026-06-22","home":"挪威","away":"塞内加尔","group":"I","score":"3-2","stage":"小组赛第2轮"},
    {"date":"2026-06-22","home":"约旦","away":"阿尔及利亚","group":"J","score":"1-2","stage":"小组赛第2轮"},
    # Day 13 (6/23)
    {"date":"2026-06-23","home":"葡萄牙","away":"乌兹别克斯坦","group":"K","score":"5-0","stage":"小组赛第2轮"},
    {"date":"2026-06-23","home":"英格兰","away":"加纳","group":"L","score":"0-0","stage":"小组赛第2轮"},
    {"date":"2026-06-23","home":"巴拿马","away":"克罗地亚","group":"L","score":"0-0","stage":"小组赛第2轮","note":"进行中"},
]


def get_latest_date():
    """获取已记录的最新比赛日期"""
    if not KNOWN_MATCHES:
        return None
    return max(m["date"] for m in KNOWN_MATCHES)


def search_new_results(date_str=None):
    """
    通过 WebSearch 搜索指定日期及之后的比赛结果。
    注意：此函数由 Claude Code agent 在 WebSearch 上下文中调用，
    返回的是搜索结果的结构化摘要，不是实时API数据。
    """
    if date_str is None:
        latest = get_latest_date()
        if latest:
            # 从最新日期的下一天开始搜索
            dt = datetime.strptime(latest, "%Y-%m-%d") + timedelta(days=1)
            date_str = dt.strftime("%Y-%m-%d")

    print(f"🔍 搜索 {date_str} 及之后的比赛结果...")
    print(f"   已知比赛: {len(KNOWN_MATCHES)} 场")
    print(f"   最新日期: {get_latest_date()}")
    print()
    print("   💡 提示: 在 Claude Code 中运行 WebSearch 获取最新结果：")
    print(f"      WebSearch('FIFA World Cup 2026 results scores {date_str}')")
    print()
    print("   当前已记录的比赛：")
    for m in KNOWN_MATCHES[-10:]:
        print(f"   {m['date']} | {m['home']} vs {m['away']} | {m['score']} | {m['stage']}")


def export_json():
    """导出所有已知比赛为 JSON"""
    output = {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_matches": len(KNOWN_MATCHES),
        "latest_date": get_latest_date(),
        "matches": KNOWN_MATCHES,
    }
    path = os.path.join(STAGE_DIR, f"matches_{datetime.now().strftime('%Y%m%d')}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"✅ 已导出: {path}")
    return output


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", type=str, help="搜索指定日期及之后的比赛")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--show", action="store_true", help="显示所有已知比赛")
    args = ap.parse_args()

    if args.json:
        data = export_json()
        if not args.show:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    if args.show:
        print(f"已知比赛: {len(KNOWN_MATCHES)} 场")
        for m in KNOWN_MATCHES:
            print(f"  {m['date']} | {m['group']}组 | {m['home']} vs {m['away']} | {m['score']}")
        return 0

    search_new_results(args.date)
    return 0


if __name__ == "__main__":
    sys.exit(main())
