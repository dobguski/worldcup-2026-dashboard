#!/usr/bin/env python3
"""
health_check.py — 全系统健康检查
================================
验证所有数据后端的可用性和数据完整性。
由 auto_qa.py D7 调用，也可独立运行。

用法:
  python health_check.py              # 文本输出
  python health_check.py --json       # JSON 输出
"""
import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime

PROJECT_DIR = Path(__file__).resolve().parent
FIFA_CACHE = PROJECT_DIR / "fifa-dashboard" / "data" / "cache.json"
FIFA_HISTORY = PROJECT_DIR / "fifa-dashboard" / "data" / "history.jsonl"
TIMELINE_DIR = PROJECT_DIR.parent / "timeline" / "data"


def check_sqlite_db(path, name):
    """Check a SQLite database."""
    try:
        import sqlite3
        if not path.exists():
            return {"name": name, "status": "missing", "size_mb": 0, "tables": 0}
        conn = sqlite3.connect(str(path), timeout=5)
        tables = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        conn.close()
        size_mb = os.path.getsize(path) / (1024 * 1024)
        return {"name": name, "status": "ok", "size_mb": round(size_mb, 1), "tables": tables}
    except Exception as e:
        return {"name": name, "status": "error", "error": str(e)}


def check_json_file(path, name):
    """Check a JSON/JSONL file."""
    if not path.exists():
        return {"name": name, "status": "missing", "size_kb": 0}
    size_kb = os.path.getsize(path) / 1024
    try:
        with open(path, "r", encoding="utf-8") as f:
            if path.suffix == ".jsonl":
                lines = sum(1 for _ in f)
                return {"name": name, "status": "ok", "size_kb": round(size_kb, 1), "lines": lines}
            else:
                data = json.load(f)
                return {"name": name, "status": "ok", "size_kb": round(size_kb, 1), "keys": len(data) if isinstance(data, dict) else len(data)}
    except Exception as e:
        return {"name": name, "status": "error", "error": str(e)}


def check_fifa_dashboard():
    """Check FIFA dashboard data freshness."""
    results = []
    # cache.json
    cache = check_json_file(FIFA_CACHE, "cache.json")
    results.append(cache)
    if cache["status"] == "ok":
        mtime = datetime.fromtimestamp(FIFA_CACHE.stat().st_mtime)
        hours_ago = (datetime.now() - mtime).total_seconds() / 3600
        cache["hours_stale"] = round(hours_ago, 1)

    # history.jsonl
    history = check_json_file(FIFA_HISTORY, "history.jsonl")
    results.append(history)

    return results


def check_timeline():
    """Check timeline database health."""
    results = []
    dbs = [
        (TIMELINE_DIR / "works.db", "works.db"),
        (TIMELINE_DIR / "poetry" / "poems.db", "poems.db"),
        (TIMELINE_DIR / "historical" / "events.db", "events.db"),
        (TIMELINE_DIR / "dynasties.db", "dynasties.db"),
    ]
    for path, name in dbs:
        results.append(check_sqlite_db(path, name))

    # index.json
    idx = check_json_file(TIMELINE_DIR / "index.json", "index.json")
    results.append(idx)

    return results


def main():
    json_output = "--json" in sys.argv

    results = {
        "timestamp": datetime.now().isoformat(),
        "fifa_dashboard": check_fifa_dashboard(),
        "timeline": check_timeline(),
    }

    # Overall health
    all_ok = True
    for section in ["fifa_dashboard", "timeline"]:
        for r in results[section]:
            if r["status"] != "ok":
                all_ok = False

    results["healthy"] = all_ok

    if json_output:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print("=" * 50)
        print("  [HealthCheck] System Health Report")
        print("=" * 50)
        print(f"\n  FIFA Dashboard:")
        for r in results["fifa_dashboard"]:
            status_icon = "[OK]" if r["status"] == "ok" else "[FAIL]"
            extra = ""
            if "hours_stale" in r:
                extra = f" (stale {r['hours_stale']}h)"
            if "lines" in r:
                extra = f" ({r['lines']} lines)"
            print(f"    {status_icon} {r['name']}: {r['status']}{extra}")

        print(f"\n  Timeline:")
        for r in results["timeline"]:
            status_icon = "[OK]" if r["status"] == "ok" else "[FAIL]"
            extra = ""
            if "size_mb" in r and r["size_mb"] > 0:
                extra = f" ({r['size_mb']}MB, {r.get('tables', 0)} tables)"
            if "keys" in r:
                extra = f" ({r['keys']} keys)"
            if "lines" in r:
                extra = f" ({r['lines']} lines)"
            print(f"    {status_icon} {r['name']}: {r['status']}{extra}")

        print(f"\n  Healthy: {'YES' if all_ok else 'NO'}")
        print("=" * 50)

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
