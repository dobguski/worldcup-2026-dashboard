#!/usr/bin/env python3
"""
auto_pipeline.py — 全自动数据管道编排引擎 v1.0
================================================
消除所有手动触发环节，实现端到端自动化。

架构（遵循 Layer 0-2 解耦）：
  Layer 0: 资源库 (_stage/)
    ├── collector.py --daemon → 每30min拉取 CLOB 冠军赔率
    ├── fetch_matches.py       → 比赛结果数据库
    └── WebSearch cron         → 每日搜索新赛果

  Layer 1: 验证门
    ├── verify_polymarket.py   → 报告数据QC
    ├── verify_requirements.py → 需求一致性
    └── auto_qa.py --quick     → 魔鬼QA

  Layer 2: 生产库 (发布)
    ├── 生成/更新报告 Markdown
    ├── 生成图表 PNG
    ├── 数据备份
    └── git commit + push

用法：
  python scripts/auto_pipeline.py              # 全量运行
  python scripts/auto_pipeline.py --collect    # 仅数据采集
  python scripts/auto_pipeline.py --publish    # 仅验证+发布
  python scripts/auto_pipeline.py --daemon     # 守护模式(采集+发布循环)
"""
import json
import os
import re
import sys
import subprocess
import time
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
STAGE_DIR = ROOT / "_stage"
REPORT_FILE = ROOT / "Polymarket_FIFA2026_分析报告.md"
SCRIPTS_DIR = ROOT / "scripts"
QC_DIR = SCRIPTS_DIR / "qc"
DASHBOARD_DIR = ROOT / "fifa-dashboard"
CACHE_FILE = DASHBOARD_DIR / "data" / "cache.json"

os.makedirs(STAGE_DIR / "collector", exist_ok=True)
os.makedirs(STAGE_DIR / "reports", exist_ok=True)


def log(phase, msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{phase}] {msg}")


def run_cmd(cmd, cwd=None, timeout=120):
    """运行命令，返回 (success, output)"""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd=str(cwd) if cwd else str(ROOT),
            encoding="utf-8", errors="replace",
        )
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, str(e)


# ============================================================
# Layer 0 — 数据采集
# ============================================================

def collect_champion_odds():
    """CLOB 冠军赔率采集"""
    log("INGEST", "采集冠军赔率 (CLOB)...")
    ok, out = run_cmd(
        [sys.executable, "collector.py", "--once"],
        cwd=DASHBOARD_DIR, timeout=90
    )
    if ok:
        log("INGEST", "冠军赔率采集完成")
        return True
    else:
        log("INGEST", f"采集失败: {out[-200:]}")
        return False


def collect_match_results():
    """比赛结果导出（静态数据)"""
    log("INGEST", "导出比赛结果...")
    ok, out = run_cmd(
        [sys.executable, "fetch_matches.py", "--json"],
        cwd=SCRIPTS_DIR, timeout=15
    )
    return ok


def collect_live_scores():
    """实时比分采集（worldcup26.ir 主源 + football-data.org 热备）"""
    log("LIVE", "采集实时比分...")
    ok, out = run_cmd(
        [sys.executable, str(SCRIPTS_DIR / "fetch_matches_live.py"), "--json"],
        timeout=20
    )
    if ok:
        # 解析输出检查是否有进行中的比赛
        try:
            data = json.loads(out)
            live_count = data.get("live", 0)
            source = data.get("source", "unknown")
            log("LIVE", f"{source}: {data['total']}场, 进行中={live_count}场")
        except json.JSONDecodeError:
            pass
    else:
        log("LIVE", f"采集失败: {out[-100:]}" if out else "采集超时")
    return ok


# ============================================================
# Layer 1 — 质量验证
# ============================================================

def verify_report():
    """报告 QC 检查"""
    log("VERIFY", "运行报告QC...")
    ok, out = run_cmd(
        [sys.executable, str(QC_DIR / "verify_polymarket.py"), str(REPORT_FILE)],
        timeout=30
    )
    # extract blocker count
    blocker_count = out.count("🔴 [")
    log("VERIFY", f"QC完成: BLOCKER={blocker_count}")
    return blocker_count == 0, out


def verify_requirements():
    """需求一致性检查"""
    log("VERIFY", "需求↔QC一致性...")
    ok, out = run_cmd(
        [sys.executable, str(QC_DIR / "verify_requirements.py")],
        timeout=10
    )
    return ok, out


def run_devil_qa():
    """魔鬼级 QA"""
    log("VERIFY", "魔鬼QA...")
    ok, out = run_cmd(
        [sys.executable, str(ROOT / "auto_qa.py"), "--quick"],
        timeout=30
    )
    return ok


# ============================================================
# Layer 2 — 发布
# ============================================================

def generate_report_from_cache():
    """从 cache.json 覆写报告的数据部分（冠军表+比赛数据+日期戳+版本）"""
    if not CACHE_FILE.exists():
        log("PUB", "缓存不存在，跳过报告更新")
        return False

    if not REPORT_FILE.exists():
        log("PUB", "报告文件不存在，跳过")
        return False

    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        cache = json.load(f)
    with open(REPORT_FILE, "r", encoding="utf-8") as f:
        report = f.read()

    timestamp = datetime.now().strftime("%Y-%m-%d")
    time_label = datetime.now().strftime("%Y年%m月%d日")
    teams = cache.get("teams", [])
    matches = cache.get("matches", [])
    total_vol = cache.get("total_volume", "N/A")

    # 1. 更新分析日期
    report = re.sub(
        r'> 分析日期：\d{4}年\d{1,2}月\d{1,2}日[^<\n]*',
        f'> 分析日期：{time_label} · 自动采集 · CLOB实时数据',
        report
    )

    # 2. 更新冠军排名表 (找到表格起始和结束)
    # 标记: | 排名 | 球队 | CLOB概率
    champ_start = report.find("| 排名 | 球队 | CLOB概率")
    if champ_start > 0:
        champ_end = report.find("\n\n", report.find("> 数据来源：", champ_start))
        if champ_end < 0:
            champ_end = report.find("\n\n---", champ_start)
        if champ_end > champ_start:
            new_table = "| 排名 | 球队 | CLOB概率 | 24h交易量 | 趋势 | 原因 |\n"
            new_table += "|:---:|:---|:---:|:---:|:---:|:---|\n"
            flags = {"France":"🇫🇷","Spain":"🇪🇸","England":"🏴Pd","Brazil":"🇧🇷",
                     "Portugal":"🇵🇹","Argentina":"🇦🇷","Germany":"🇩🇪","Netherlands":"🇳🇱",
                     "Norway":"🇳🇴","USA":"🇺🇸","Colombia":"🇨🇴","Japan":"🇯🇵",
                     "Morocco":"🇲🇦","Mexico":"🇲🇽","Belgium":"🇧🇪","Croatia":"🇭🇷",
                     "Switzerland":"🇨🇭","Sweden":"🇸🇪","Italy":"🇮🇹","Uruguay":"🇺🇾",
                     "Canada":"🇨🇦","Korea":"🇰🇷","Senegal":"🇸🇳","Ecuador":"🇪🇨"}
            for i, t in enumerate(teams[:16]):
                f = flags.get(t["team"], "  ")
                tr = "↑" if t.get("trend") == "up" else "↓" if t.get("trend") == "down" else "→"
                new_table += f"| {i+1} | {f} {t['team']} | **{t['prob']:.1f}%** | ${t.get('vol',0):,.0f} | {tr} | 自动采集 |\n"
            others = round(sum(t["prob"] for t in teams[16:]), 1)
            new_table += f"| — | 🔹 其他{len(teams)-16}队 | **{others:.1f}%** | — | — | 自动采集 |\n"
            report = report[:champ_start] + new_table + "\n" + report[champ_end:]

    # 3. 版本历史去重: 删除所有旧 v1.4 auto行, 插入一条最新行
    import re
    v14_pattern = re.compile(r'\| v1\.4 \| \d{4}-\d{2}-\d{2} \| auto \| .*\n?')
    new_ver_line = f"| v1.4 | {timestamp} | auto | — | {len(matches)} | 自动管道更新：{len(teams)}队赔率 + {len(matches)}场比赛 |\n"
    report = v14_pattern.sub("", report)  # 删除所有旧v1.4行
    ver_marker = "| v1.3 |"
    if ver_marker in report:
        report = report.replace(ver_marker, new_ver_line + ver_marker, 1)

    # 4. 写入报告
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(report)

    log("PUB", f"报告已更新: {REPORT_FILE.name} ({len(teams)}队赔率, {len(matches)}场比赛)")
    return True


def generate_charts():
    """自动生成图表"""
    log("PUB", "生成图表...")
    ok, out = run_cmd(
        [sys.executable, str(QC_DIR / "generate_charts.py")],
        timeout=15
    )
    return ok


def backup_report():
    """自动备份"""
    log("PUB", "备份报告...")
    ok, out = run_cmd(
        [sys.executable, str(QC_DIR / "backup_report.py")],
        timeout=10
    )
    return ok


def rebuild_dashboard():
    """重建静态 dashboard.html"""
    log("PUB", "重建 dashboard...")
    build_script = DASHBOARD_DIR / "build_static.py"
    if build_script.exists():
        ok, out = run_cmd(
            [sys.executable, str(build_script)],
            cwd=DASHBOARD_DIR, timeout=30
        )
        if ok:
            log("PUB", "dashboard.html 已刷新")
        return ok
    return False


def git_commit_and_push():
    """自动提交推送"""
    log("PUB", "Git 提交...")
    ok, out = run_cmd(
        [sys.executable, str(ROOT / "git_safe.py"), "-m",
         f"auto: pipeline update {datetime.now().strftime('%Y-%m-%d %H:%M')}"],
        timeout=60
    )
    if ok:
        log("PUB", "Git 推送完成")
    else:
        log("PUB", f"Git 失败: {out[-200:]}")
    return ok


# ============================================================
# 编排
# ============================================================

def pipeline_full(publish=False):
    """全量管道"""
    log("PIPE", "=" * 50)
    log("PIPE", "全自动管道启动")

    # Layer 0
    collect_champion_odds()
    collect_match_results()
    collect_live_scores()

    # Layer 1
    v_ok, _ = verify_report()
    vr_ok, _ = verify_requirements()
    qa_ok = run_devil_qa()

    gate_pass = v_ok and vr_ok and qa_ok
    log("PIPE", f"验证门: {'PASS' if gate_pass else 'WARN'}")

    # Layer 2
    if publish:
        if gate_pass:
            generate_report_from_cache()
            rebuild_dashboard()
            generate_charts()
            backup_report()
            git_commit_and_push()
            log("PIPE", "发布完成")
        else:
            log("PIPE", "验证未通过，跳过发布")
    else:
        generate_report_from_cache()
        rebuild_dashboard()
        generate_charts()
        backup_report()
        log("PIPE", "采集+验证完成 (跳过git push)")

    log("PIPE", "管道结束")


def daemon_mode(interval_min=5):
    """守护模式：60s比分 / 5min赔率 / 30min全量发布 + 看门狗自动重启"""
    import traceback
    log("DAEMON", "三层节奏: 60s比分 → 5min赔率+面板 → 30min全量+push [看门狗已启用]")
    cycle = 0
    consecutive_failures = 0
    while True:
        cycle += 1
        ts = datetime.now().strftime("%H:%M:%S")

        # 每60秒: 实时比分 + dashboard刷新
        try:
            collect_live_scores()
            rebuild_dashboard()
            consecutive_failures = 0
        except Exception as e:
            consecutive_failures += 1
            log("DAEMON", f"周期异常 ({consecutive_failures}次): {str(e)[:80]}")
            if consecutive_failures > 10:
                log("DAEMON", "连续失败>10次, 跳过本周期")

        # 每5分钟 (每5个周期): 冠军赔率刷新
        if cycle % 5 == 0:
            log("DAEMON", f"[{ts}] 5min 冠军赔率刷新")
            collect_champion_odds()

        # 每30分钟 (每30个周期): 全量发布 (报告+图表+备份+push)
        if cycle % 30 == 0:
            log("DAEMON", f"[{ts}] 30min 全量发布")
            verify_report()
            generate_report_from_cache()
            generate_charts()
            backup_report()
            git_commit_and_push()

        time.sleep(60)  # 60秒基础间隔


def main():
    import argparse
    ap = argparse.ArgumentParser(description="全自动数据管道")
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--daemon", action="store_true")
    ap.add_argument("--interval", type=int, default=1)
    args = ap.parse_args()

    if args.daemon:
        daemon_mode(args.interval)
    elif args.collect:
        collect_live_scores()
        collect_champion_odds()
        collect_match_results()
        verify_report()
    elif args.publish:
        pipeline_full(publish=True)
    else:
        pipeline_full(publish=False)


if __name__ == "__main__":
    main()
