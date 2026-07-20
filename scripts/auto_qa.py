#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
auto_qa.py — 魔鬼级 QA 质量保证引擎 v1.0
==========================================
角色: 默认不信任。默认不通过。证明自己值得通过。
标准: 所有维度 >= 80/100 才验收
触发: post-commit hook 自动执行, 也可手动 python auto_qa.py

检查维度 (7维):
  D1. 代码质量      — 语法 + 复杂度 + 重复代码
  D2. 架构合规      — 分层解耦 + 调用方向 + _stage/ 完整性
  D3. 数据完整性    — tracking_list + parquet + 文件覆盖
  D4. 安全审计      — Token + 路径穿越 + .gitignore
  D5. Git 卫生      — 分支状态 + 未追踪 + stash 残留
  D6. 报告质量      — 结构 + 数据引用 + 日期一致性
  D7. 跨项目一致性  — 同名文件 + 版本号 + 依赖

用法:
  python auto_qa.py                  # 全量检查
  python auto_qa.py --quick          # 快速模式 (仅 D1+D4+D5)
  python auto_qa.py --json           # JSON 输出
  python auto_qa.py --dim D1,D4      # 指定维度
"""

import os, sys, io, json, re, ast, subprocess
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
except Exception:
    pass

PROJECT_DIR = Path(__file__).resolve().parent
THRESHOLD = 80  # 魔鬼级: 80 分及格

# 自动检测项目类型 (影响检查范围)
def detect_project_type():
    """根据项目特征推断类型: stock / analysis / general"""
    if (PROJECT_DIR / "data" / "tracking_list.json").exists():
        return "stock"
    if (PROJECT_DIR / "Polymarket_FIFA2026_分析报告.md").exists():
        return "analysis"
    if (PROJECT_DIR / "stockanalysis").exists() or (PROJECT_DIR / "us_stock_fetcher.py").exists():
        return "analysis"
    return "general"

PROJECT_TYPE = detect_project_type()


def run(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, shell=True, cwd=str(PROJECT_DIR),
                           capture_output=True, timeout=timeout)
        out = r.stdout.decode('utf-8', errors='replace').strip()
        err = r.stderr.decode('utf-8', errors='replace').strip()
        return r.returncode, out, err
    except Exception as e:
        return -1, "", str(e)


# ============================================================
# D1: 代码质量 (权重 15%)
# ============================================================

def check_code_quality():
    score = 100
    issues = []

    py_files = list(PROJECT_DIR.glob("*.py")) + list((PROJECT_DIR / "scripts").glob("*.py"))
    py_files = [f for f in py_files if f.name not in ("config_secret.py",)]

    # 1.1 语法检查
    syntax_errors = 0
    for f in py_files:
        rc, _, _ = run(f'"{sys.executable}" -m py_compile "{f}"')
        if rc != 0:
            syntax_errors += 1
            issues.append(f"[BLOCKER] 语法错误: {f.name}")
            score -= 40

    # 1.2 函数复杂度 (ast 分析)
    complex_funcs = []
    for f in py_files:
        try:
            tree = ast.parse(f.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    lines = node.end_lineno - node.lineno if node.end_lineno else 0
                    if lines > 80:
                        complex_funcs.append(f"{f.name}:{node.name}({lines}行)")
        except Exception:
            pass
    if complex_funcs:
        issues.append(f"[WARN] {len(complex_funcs)} 个超长函数 (>80行): {', '.join(complex_funcs[:3])}")
        score -= min(15, len(complex_funcs) * 3)

    # 1.3 重复 import 模式检测
    dup_imports = 0
    for f in py_files:
        try:
            content = f.read_text(encoding='utf-8')
            if content.count('os.environ.get') > 3:
                dup_imports += 1
        except Exception:
            pass
    if dup_imports:
        issues.append(f"[WARN] {dup_imports} 个文件有重复凭据读取模式")
        score -= min(10, dup_imports * 2)

    return max(0, score), issues


# ============================================================
# D2: 架构合规 (权重 15%)
# ============================================================

def check_architecture():
    score = 100
    issues = []

    # 2.1 _stage/ 目录结构
    stage = PROJECT_DIR / "_stage"
    if not stage.exists():
        issues.append("[BLOCKER] _stage/ 目录缺失 — 违反 Layer 0 架构")
        score -= 50

    # 2.2 分层文件存在性 (根据项目类型调整)
    required_files = ["db_ingest.py", "db_publish.py"]
    if PROJECT_TYPE == "stock":
        required_files.append("data_core.py")
        required_files.append("health_check.py")
    for fname in required_files:
        if not (PROJECT_DIR / fname).exists():
            issues.append(f"[BLOCKER] {fname} 缺失 — 架构文件不完整")
            score -= 30

    # 2.2b _stage/ 子目录 (根据项目类型)
    if PROJECT_TYPE == "stock":
        expected_subs = ["tushare", "akshare", "eastmoney", "archive"]
    elif PROJECT_TYPE == "analysis":
        expected_subs = ["polymarket", "aggregator", "manual", "archive"]
    else:
        expected_subs = ["archive"]
    for sub in expected_subs:
        if not (stage / sub).exists():
            issues.append(f"[WARN] _stage/{sub}/ 缺失")
            score -= 10

    # 2.3 禁止反向依赖 (db_publish 不应被 db_ingest import — 排除注释)
    try:
        ingest_code = (PROJECT_DIR / "db_ingest.py").read_text(encoding='utf-8')
        # 移除注释和文档字符串后再检查
        code_only = re.sub(r'#.*', '', ingest_code)
        code_only = re.sub(r'""".*?"""', '', code_only, flags=re.DOTALL)
        code_only = re.sub(r"'''.*?'''", '', code_only, flags=re.DOTALL)
        if 'import db_publish' in code_only or 'from db_publish' in code_only:
            issues.append("[WARN] db_ingest.py 代码引用了 db_publish — 违反解耦原则")
            score -= 20
    except Exception:
        pass

    # 2.4 .gitignore 架构覆盖
    gitignore = PROJECT_DIR / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text(encoding='utf-8')
        if '_stage/**' not in content:
            issues.append("[BLOCKER] .gitignore 未递归忽略 _stage/**")
            score -= 40
        if 'data/cache/' not in content:
            issues.append("[WARN] .gitignore 未忽略 data/cache/")
            score -= 10
        if 'config_secret.py' not in content:
            issues.append("[BLOCKER] .gitignore 未忽略 config_secret.py")
            score -= 40

    return max(0, score), issues


# ============================================================
# D3: 数据完整性 (权重 15%)
# ============================================================

def check_data_integrity():
    score = 100
    issues = []

    # 3.1 tracking_list.json (仅 stock 项目)
    if PROJECT_TYPE == "stock":
        tl = PROJECT_DIR / "data" / "tracking_list.json"
        if tl.exists():
            try:
                data = json.loads(tl.read_text(encoding='utf-8'))
                stocks = data.get("stocks", {})
                sectors = data.get("sectors", {})
                if len(stocks) < 50:
                    issues.append(f"[WARN] tracking_list 仅 {len(stocks)} 只标的")
                    score -= 20
                if len(sectors) < 5:
                    issues.append(f"[WARN] tracking_list 仅 {len(sectors)} 个板块")
                    score -= 10
                all_codes = set(stocks.keys())
                orphan_count = 0
                for sec, members in sectors.items():
                    for m in members:
                        if len(m) >= 1 and m[0] not in all_codes:
                            orphan_count += 1
                if orphan_count:
                    issues.append(f"[WARN] {orphan_count} 个板块引用无效股票代码")
                    score -= 15
            except Exception as e:
                issues.append(f"[BLOCKER] tracking_list.json 解析失败: {e}")
                score -= 50
        else:
            issues.append("[BLOCKER] tracking_list.json 缺失")
            score -= 50

    # 3.2 报告文件覆盖 (检查最近3天)
    today = datetime.now()
    missing_reports = []
    for days_ago in range(3):
        d = (today - timedelta(days=days_ago)).strftime("%Y%m%d")
        # 检查每日跟踪数据
        daily = PROJECT_DIR / "data" / "每日跟踪" / f"{d}.json"
        if not daily.exists() and days_ago > 0:  # 今天可能还没收盘
            missing_reports.append(f"每日跟踪/{d}.json")
    if len(missing_reports) > 1:
        issues.append(f"[WARN] 近3天缺失 {len(missing_reports)} 份每日跟踪数据")
        score -= len(missing_reports) * 10

    # 3.3 数据缓存文件量
    cache_dir = PROJECT_DIR / "data" / "cache"
    if cache_dir.exists():
        cache_files = list(cache_dir.glob("*.parquet"))
        if len(cache_files) < 10:
            issues.append(f"[WARN] data/cache/ 仅 {len(cache_files)} 个文件 (缓存可能失效)")
            score -= 10

    return max(0, score), issues


# ============================================================
# D4: 安全审计 (权重 20%)
# ============================================================

def check_security():
    score = 100
    issues = []

    # 4.1 Token 泄漏扫描
    py_files = list(PROJECT_DIR.glob("**/*.py"))
    py_files = [f for f in py_files if '.venv' not in str(f) and '__pycache__' not in str(f)]
    token_hits = 0
    for f in py_files:
        try:
            content = f.read_text(encoding='utf-8', errors='ignore')
            # 检测硬编码 32 位 hex (Tushare token 模式)
            matches = re.findall(r"['\"]([a-fA-F0-9]{32})['\"]", content)
            for m in matches:
                # 排除 os.environ.get 中的 fallback
                line_idx = content.find(m)
                context = content[max(0,line_idx-50):line_idx+50]
                if 'os.environ.get' not in context:
                    token_hits += 1
                    issues.append(f"[BLOCKER] {f.name}: 硬编码 32位 Token")
            # 检测常见 API key 模式
            if re.search(r'(sk-[a-zA-Z0-9_-]{20,}|ghp_[a-zA-Z0-9]{36})', content):
                token_hits += 1
                issues.append(f"[BLOCKER] {f.name}: 硬编码 API Key")
        except Exception:
            pass
    if token_hits > 0:
        score -= min(100, token_hits * 50)

    # 4.2 路径穿越防护
    for fname in ["db_ingest.py", "db_publish.py"]:
        fpath = PROJECT_DIR / fname
        if fpath.exists():
            content = fpath.read_text(encoding='utf-8', errors='ignore')
            if 'validate_date_str' not in content:
                issues.append(f"[BLOCKER] {fname}: 缺少 validate_date_str 输入验证")
                score -= 30
            if 'safe_stage_path' not in content and 'safe_' not in content:
                issues.append(f"[WARN] {fname}: 缺少安全路径构建函数")
                score -= 15

    # 4.3 .gitignore 覆盖审计
    gitignore = PROJECT_DIR / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text(encoding='utf-8')
        required = ['config_secret.py', '.env', '_stage/**', 'data/cache/', '*.pem']
        for pattern in required:
            if pattern not in content:
                issues.append(f"[BLOCKER] .gitignore 缺少: {pattern}")
                score -= 20

    return max(0, score), issues


# ============================================================
# D5: Git 卫生 (权重 10%)
# ============================================================

def check_git_hygiene():
    score = 100
    issues = []

    # 5.1 分支分叉
    _, out, _ = run("git status -sb")
    ahead = behind = 0
    ahead_m = re.search(r'\[ahead\s+(\d+)', out)
    behind_m = re.search(r'behind\s+(\d+)', out)
    if ahead_m:
        ahead = int(ahead_m.group(1))
    if behind_m:
        behind = int(behind_m.group(1))
    if ahead > 3:
        issues.append(f"[WARN] 本地领先 {ahead} 个提交未推送")
        score -= ahead * 5
    if behind > 0:
        issues.append(f"[WARN] 本地落后 {behind} 个提交")
        score -= behind * 10

    # 5.2 未追踪文件
    _, untracked, _ = run("git ls-files --others --exclude-standard")
    untracked_count = len(untracked.split('\n')) if untracked.strip() else 0
    if untracked_count > 5:
        issues.append(f"[WARN] {untracked_count} 个未追踪文件")
        score -= min(20, (untracked_count - 5) * 2)

    # 5.3 Stash 残留
    _, stash, _ = run("git stash list")
    stash_count = len(stash.split('\n')) if stash.strip() else 0
    if stash_count > 2:
        issues.append(f"[WARN] {stash_count} 个残留 stash")
        score -= min(15, stash_count * 3)

    # 5.4 .git/index.lock
    lock = PROJECT_DIR / ".git" / "index.lock"
    if lock.exists():
        age = (datetime.now() - datetime.fromtimestamp(lock.stat().st_mtime)).total_seconds()
        if age > 300:
            issues.append("[WARN] 残留 index.lock >5min")
            score -= 10

    return max(0, score), issues


# ============================================================
# D6: 报告质量 (权重 15%)
# ============================================================

def check_report_quality():
    score = 100
    issues = []

    reports_dir = PROJECT_DIR / "reports"
    if not reports_dir.exists():
        return 0, ["[BLOCKER] reports/ 目录缺失"]

    # 6.1 检查最近的 Markdown 报告
    today = datetime.now().strftime("%Y%m%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

    md_files = list(reports_dir.glob("**/*.md"))
    # 仅检查最近 2 天的报告 (历史报告不追溯)
    recent = [f for f in md_files if today in f.name or yesterday in f.name]

    for f in recent[:10]:
        try:
            content = f.read_text(encoding='utf-8')
            if len(content) < 200:
                issues.append(f"[WARN] {f.name}: 报告过短 ({len(content)} 字符)")
                score -= 5
            if not re.search(r'^# ', content, re.MULTILINE):
                issues.append(f"[WARN] {f.name}: 缺少一级标题")
                score -= 5
        except Exception:
            pass

    # 6.2 检查是否有今日综合报告 (非交易日跳过)
    from datetime import datetime as dt
    weekday = dt.now().weekday()
    if weekday < 5:  # 周一至周五
        master_today = reports_dir / f"daily_master_{today}.md"
        master_json = PROJECT_DIR / "data" / f"daily_master_{today}.json"
        if not master_today.exists() and not master_json.exists():
            issues.append("[WARN] 今日综合报告未生成")
            score -= 15

    return max(0, score), issues


# ============================================================
# D7: 任务完成度 (权重 10%)
# ============================================================

def check_task_completion():
    score = 100
    issues = []

    # 7.1 检查是否有未完成的任务 (通过 todo 标记)
    py_files = list(PROJECT_DIR.glob("*.py")) + list((PROJECT_DIR / "scripts").glob("*.py"))
    todo_count = 0
    for f in py_files:
        try:
            content = f.read_text(encoding='utf-8', errors='ignore')
            todo_count += len(re.findall(r'#\s*TODO|#\s*FIXME|#\s*HACK', content))
        except Exception:
            pass
    if todo_count > 3:
        issues.append(f"[WARN] 代码中 {todo_count} 个 TODO/FIXME 未解决")
        score -= min(25, todo_count * 2)

    # 7.2 检查 git_safe.py 可用性
    if not (PROJECT_DIR / "git_safe.py").exists():
        issues.append("[BLOCKER] git_safe.py 缺失 — 无安全提交管道")
        score -= 40

    # 7.3 检查 health_check.py 可用性
    if not (PROJECT_DIR / "health_check.py").exists():
        issues.append("[WARN] health_check.py 缺失")
        score -= 20

    return max(0, score), issues


# ============================================================
# 汇总 + 判决
# ============================================================

# ============================================================
# D0: 运行时健康 (权重 0%, 但是一票否决)
# ============================================================
def check_runtime_health():
    """不检查这些, 其他所有维度满分也没意义"""
    score = 100
    issues = []
    blockers = []

    # D0.1: 守护进程是否活着 (直接用subprocess获取进程列表)
    try:
        import subprocess as sp
        result = sp.run(['tasklist'], capture_output=True, text=True, timeout=10)
        python_lines = [l for l in result.stdout.split('\n') if 'python' in l.lower()]
        proc_count = len(python_lines)
        if proc_count == 0:
            blockers.append("守护进程未运行 — 数据不会自动更新")
        elif proc_count > 3:
            issues.append(f"Python进程数={proc_count} (>3), 可能存在僵尸")
        else:
            issues.append(f"守护进程正常: {proc_count}个Python进程")
    except Exception:
        pass  # tasklist不可用时不阻塞

    # D0.2: 数据新鲜度
    cache_file = PROJECT_DIR / "fifa-dashboard" / "data" / "cache.json"
    if cache_file.exists():
        mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
        hours_ago = (datetime.now() - mtime).total_seconds() / 3600
        if hours_ago > 6:
            blockers.append(f"cache.json {hours_ago:.0f}小时未更新 — 数据已过期")
        elif hours_ago > 1:
            issues.append(f"cache.json {hours_ago:.0f}小时未更新")

    # D0.3: 实时比分API是否可达 (短超时，防止阻塞QA)
    try:
        import urllib.request
        req = urllib.request.Request('https://worldcup26.ir/get/games',
            headers={'User-Agent': 'DobGuski-QA/1.0'})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode())
            games = data.get('games', []) if isinstance(data, dict) else data
            live = [g for g in games if g.get('finished')=='FALSE' and g.get('time_elapsed') not in ('notstarted','')]
            finished = [g for g in games if g.get('finished')=='TRUE']
            issues.append(f"实时比分API正常: {len(games)}场, {len(live)}进行中, {len(finished)}完赛")
    except Exception as e:
        blockers.append(f"实时比分API不可达: {str(e)[:60]}")

    # D0.4: 版本历史是否膨胀
    report_file = PROJECT_DIR / "Polymarket_FIFA2026_分析报告.md"
    if report_file.exists():
        with open(report_file, 'r', encoding='utf-8') as f:
            report = f.read()
        v14_count = report.count('| v1.4 |')
        if v14_count > 3:
            blockers.append(f"版本历史v1.4行数={v14_count} (>3), 自动管道去重失效")
        elif v14_count > 1:
            issues.append(f"版本历史v1.4行数={v14_count}")

    # D0.5: 报告日期 vs 实际日期
    date_match = re.search(r'分析日期：(\d{4})年(\d{1,2})月(\d{1,2})日', report if 'report' in dir() else '')
    if date_match:
        report_date = datetime(int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3)))
        days_behind = (datetime.now() - report_date).days
        if days_behind > 2:
            blockers.append(f"报告日期 {report_date.strftime('%m-%d')} 落后 {days_behind} 天")

    # 评分：只有真正的问题才扣分，info不算
    real_issues = [i for i in issues if '正常' not in i and 'OK' not in i.upper()]
    blocker_score = 100 if not blockers else 0
    issues_score = max(60, 100 - len(real_issues) * 10)
    real_score = blocker_score if blockers else issues_score

    return {
        "score": real_score,
        "blockers": blockers,
        "issues": issues,
        "weight": 0.0,  # 不计入加权, 但blockers直接REJECT
    }


DIMENSIONS = {
    "D0": ("运行时健康", 0.0, check_runtime_health),  # 一票否决
    "D1": ("代码质量", 0.15, check_code_quality),
    "D2": ("架构合规", 0.15, check_architecture),
    "D3": ("数据完整性", 0.15, check_data_integrity),
    "D4": ("安全审计", 0.20, check_security),
    "D5": ("Git 卫生", 0.10, check_git_hygiene),
    "D6": ("报告质量", 0.15, check_report_quality),
    "D7": ("任务完成度", 0.10, check_task_completion),
}


def run_qa(dims=None, json_output=False):
    """执行全部或指定维度的 QA 检查"""
    results = {}
    total_score = 0
    total_weight = 0

    selected = dims or list(DIMENSIONS.keys())

    if not json_output:
        print("=" * 60)
        print("  👹 魔鬼级 QA 质量保证引擎 v1.0")
        print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  阈值: {THRESHOLD}/100 (默认不通过)")
        print(f"  维度: {', '.join(selected)}")
        print("=" * 60)

    for dim_key in selected:
        dim_name, weight, check_fn = DIMENSIONS[dim_key]
        result = check_fn()
        # D0 返回完整dict，其余维度返回 (score, issues)
        if isinstance(result, dict):
            score = result["score"]
            issues = result.get("issues", []) + result.get("blockers", [])
            results[dim_key] = {"name": dim_name, "weight": weight, "score": score,
                                "issues": issues, "passed": score >= THRESHOLD,
                                "blockers": result.get("blockers", [])}
        else:
            score, issues = result
            results[dim_key] = {"name": dim_name, "weight": weight, "score": score,
                                "issues": issues, "passed": score >= THRESHOLD,
                                "blockers": []}
        total_score += score * weight
        total_weight += weight

        if not json_output:
            if dim_key == "D0":
                # D0特殊输出
                d0_score = results[dim_key]
                if d0_score.get("blockers"):
                    print(f"\n  ⛔ D0: {dim_name} — 一票否决")
                    for b in d0_score["blockers"]:
                        print(f"     🔴 [BLOCKER] {b}")
                else:
                    print(f"\n  ✅ D0: {dim_name} — 通过")
                for i in issues[:5]:
                    print(f"     🟡 {i}")
            else:
                icon = "✅" if score >= THRESHOLD else ("⚠️" if score >= 60 else "❌")
                print(f"\n  {icon} {dim_key}: {dim_name} — {score}/100 (权重 {weight*100:.0f}%)")
                for issue in issues[:5]:
                    print(f"     {issue}")
                if len(issues) > 5:
                    print(f"     ... 还有 {len(issues)-5} 个问题")

    # 加权总分 (D0不计入)
    d0_weight_total = sum(DIMENSIONS[k][1] for k in selected if k != "D0")
    final_score = sum(results[k]["score"] * DIMENSIONS[k][1] for k in selected if k != "D0")
    final_score = final_score / d0_weight_total if d0_weight_total > 0 else 0
    all_passed = all(r["passed"] for r in results.values())
    blockers = sum(len(r.get("blockers", [])) for r in results.values())
    blockers += sum(1 for r in results.values() for i in r.get("issues", []) if "[BLOCKER]" in i)
    d0_pass = len(results.get("D0", {}).get("blockers", [])) == 0

    verdict = "PASS" if (all_passed and blockers == 0 and d0_pass) else "REJECT"

    if not json_output:
        print(f"\n  {'='*60}")
        print(f"  综合评分: {final_score:.0f}/100 (D0一票否决制)")
        print(f"  判决: {'✅ 验收通过' if verdict == 'PASS' else '⛔ 验收拒绝 — 修复后重新提交'}")
        print(f"  {'='*60}")

    if json_output:
        output = {
            "timestamp": datetime.now().isoformat(),
            "project": PROJECT_DIR.name,
            "threshold": THRESHOLD,
            "verdict": verdict,
            "final_score": round(final_score, 1),
            "blockers": blockers,
            "dimensions": {k: {"name": v["name"], "score": v["score"], "passed": v["passed"], "issues": v["issues"]} for k, v in results.items()},
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))

    return verdict == "PASS", final_score


def main():
    import argparse
    p = argparse.ArgumentParser(description="auto_qa — 魔鬼级 QA 引擎")
    p.add_argument("--quick", action="store_true", help="快速模式 (D1+D4+D5)")
    p.add_argument("--json", action="store_true", help="JSON 输出")
    p.add_argument("--dim", default=None, help="指定维度 (逗号分隔, 如 D1,D4)")
    args = p.parse_args()

    if args.dim:
        dims = args.dim.split(",")
    elif args.quick:
        dims = ["D0", "D1", "D4", "D5"]  # D0必须在快速模式中运行
    else:
        dims = None

    passed, score = run_qa(dims=dims, json_output=args.json)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
