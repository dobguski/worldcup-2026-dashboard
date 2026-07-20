#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
enrich_gj.py — 将上海图书馆古籍(gj)数据写入 Timeline works.db
==============================================================
数据来源: _stage/shlib/gj/*.json (由 ingest_shlib_gj.py 生成)
目标: D:\AI探索学习\timeline\data\works.db

新增表:
  - gj_classifications  — 古籍分类体系 (经/史/子/集/叢 + 特殊类别)
  - gj_works            — 著作实体 (Work: 杜工部年谱等)
  - gj_instances        — 版本实体 (Instance: 四部叢刊本/清光緒刻本等, 含馆藏编号)
  - gj_work_persons     — 著作-人物关联 (作者/编者/贡献者)

设计: 遵循 discipline.md 分层架构, 先备份再写入
"""
import json, sqlite3, shutil, os, sys, io
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

TIMELINE_DB = Path("D:/AI探索学习/timeline/data/works.db")
STAGE_DIR = Path("D:/AI探索学习/DobGuski/_stage/shlib/gj")

def log(level, msg):
    print(f"[{datetime.now():%H:%M:%S}] [GJ] [{level}] {msg}")

def load_json(filename):
    path = STAGE_DIR / filename
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding='utf-8'))

def backup():
    backup_path = TIMELINE_DB.parent / f"works_backup_gj_{datetime.now():%Y%m%d_%H%M%S}.db"
    shutil.copy2(TIMELINE_DB, backup_path)
    log("OK", f"备份: {backup_path.name}")
    return True

def extract_label(props):
    """从 JSON-LD props 中提取首选标签"""
    labels = props.get("http://bibframe.org/vocab/label", []) or \
             props.get("http://id.loc.gov/ontologies/bibframe/label", [])
    for lbl in labels:
        if lbl.get("lang") == "chs":
            return lbl["value"]
    if labels:
        return labels[0]["value"]
    return ""

def extract_title(props):
    """提取书名 (chs/cht/pinyin)"""
    titles = props.get("http://purl.org/dc/elements/1.1/title", [])
    result = {"chs": "", "cht": "", "pinyin": ""}
    for t in titles:
        lang = t.get("lang", "")
        if lang == "chs": result["chs"] = t["value"]
        elif lang == "cht": result["cht"] = t["value"]
        elif lang == "zh-pny": result["pinyin"] = t["value"]
    if not result["chs"] and titles:
        result["chs"] = titles[0]["value"]
    return result

def enrich():
    conn = sqlite3.connect(str(TIMELINE_DB))

    # ── Drop old gj tables ──
    for t in ["gj_instances", "gj_works", "gj_classifications", "gj_work_persons"]:
        conn.execute(f"DROP TABLE IF EXISTS {t}")

    # ── Create tables ──
    conn.execute("""
        CREATE TABLE gj_classifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uri TEXT UNIQUE NOT NULL,
            label TEXT NOT NULL,
            category TEXT,      -- 经/史/子/集/叢/特殊
            parent_uri TEXT,
            source TEXT DEFAULT 'shlib_gj'
        )
    """)
    conn.execute("""
        CREATE TABLE gj_works (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uri TEXT UNIQUE NOT NULL,
            title_chs TEXT,
            title_cht TEXT,
            title_pinyin TEXT,
            category TEXT,
            source TEXT DEFAULT 'shlib_gj'
        )
    """)
    conn.execute("""
        CREATE TABLE gj_instances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uri TEXT UNIQUE NOT NULL,
            label TEXT,
            title_chs TEXT,
            title_cht TEXT,
            title_pinyin TEXT,
            work_uri TEXT REFERENCES gj_works(uri),
            creator_text TEXT,
            edition_type TEXT,
            classification_uri TEXT,
            volume_name TEXT,
            catalog_id TEXT,
            temporal_label TEXT,
            source TEXT DEFAULT 'shlib_gj'
        )
    """)
    conn.execute("""
        CREATE TABLE gj_work_persons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            instance_uri TEXT,
            person_uri TEXT,
            role_type TEXT,      -- creator/contributor
            source TEXT DEFAULT 'shlib_gj'
        )
    """)

    # ── Populate Classifications ──
    cls_data = load_json("classifications.json")
    cls_count = 0
    if cls_data:
        for c in cls_data["data"]:
            label = c.get("label", "")
            uri = c.get("uri", "")
            # Determine category
            cat = "特殊"
            if label in ("經",): cat = "經"
            elif label in ("史",): cat = "史"
            elif label in ("子",): cat = "子"
            elif label in ("集",): cat = "集"
            elif label in ("叢",): cat = "叢"

            conn.execute(
                "INSERT OR IGNORE INTO gj_classifications(uri, label, category) VALUES(?,?,?)",
                (uri, label, cat))
            cls_count += 1
        log("OK", f"gj_classifications: {cls_count} rows")

    # ── Populate Works ──
    wrk_data = load_json("works_sample.json")
    wrk_count = 0
    if wrk_data:
        for uri, entity in wrk_data["data"].items():
            props = entity.get(uri, {})
            title = extract_title(props)
            conn.execute(
                "INSERT OR IGNORE INTO gj_works(uri, title_chs, title_cht, title_pinyin) VALUES(?,?,?,?)",
                (uri, title["chs"], title["cht"], title["pinyin"]))
            wrk_count += 1
        log("OK", f"gj_works: {wrk_count} rows")

    # ── Populate Instances ──
    ins_data = load_json("instances_sample.json")
    ins_count = 0
    person_links = []
    if ins_data:
        for uri, entity in ins_data["data"].items():
            props = entity.get(uri, {})
            label = extract_label(props)
            title = extract_title(props)

            # Work link
            work_uri = ""
            iof = props.get("http://bibframe.org/vocab/instanceOf", [])
            if iof:
                work_uri = iof[0].get("value", "")

            # Creator text
            creator = ""
            creators = props.get("http://purl.org/dc/elements/1.1/creator", [])
            if creators:
                creator = creators[0].get("value", "")

            # Edition
            edition = ""
            editions = props.get("http://bibframe.org/vocab/edition", [])
            if editions:
                edition = editions[0].get("value", "").split("/")[-1]

            # Classification
            cls_uri = ""
            clss = props.get("http://bibframe.org/vocab/classification", []) or \
                   props.get("http://pmb.library.sh.cn/ontology/classification", [])
            # classif can be literal or uri
            for c in clss:
                if c.get("type") == "uri":
                    cls_uri = c.get("value", "")

            # Volume name
            vol = ""
            vols = props.get("http://pmb.library.sh.cn/ontology/volumeName", [])
            if vols: vol = vols[0].get("value", "")

            # Catalog ID
            cat_id = ""
            ids = props.get("http://purl.org/dc/elements/1.1/identifier", [])
            if ids: cat_id = ids[0].get("value", "")

            # Temporal
            temporal = ""
            temps = props.get("http://www.library.sh.cn/ontology/temporalValue", [])
            if temps: temporal = temps[0].get("value", "")

            conn.execute("""
                INSERT OR IGNORE INTO gj_instances(uri, label, title_chs, title_cht, title_pinyin,
                    work_uri, creator_text, edition_type, classification_uri, volume_name, catalog_id, temporal_label)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (uri, label, title["chs"], title["cht"], title["pinyin"],
                 work_uri, creator, edition, cls_uri, vol, cat_id, temporal))
            ins_count += 1

            # Collect person links
            for pred, person_refs in [
                ("http://bibframe.org/vocab/creator", "creator"),
                ("http://bibframe.org/vocab/contribution", "contributor"),
            ]:
                for ref in props.get(pred, []):
                    person_uri = ref.get("value", "")
                    if person_uri and "entity/person" in person_uri:
                        person_links.append((uri, person_uri, person_refs[1]))

        log("OK", f"gj_instances: {ins_count} rows")

    # ── Populate Person Links ──
    for inst_uri, person_uri, role in person_links:
        conn.execute(
            "INSERT OR IGNORE INTO gj_work_persons(instance_uri, person_uri, role_type) VALUES(?,?,?)",
            (inst_uri, person_uri, role))
    log("OK", f"gj_work_persons: {len(person_links)} links")

    conn.commit()

    # ── Verify ──
    for t in ["gj_classifications", "gj_works", "gj_instances", "gj_work_persons"]:
        cnt = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {cnt} rows")

    conn.close()
    return True

def main():
    print("=" * 60)
    print("  enrich_gj.py — 古籍数据 → works.db")
    print(f"  {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 60)

    cls = load_json("classifications.json")
    wrk = load_json("works_sample.json")
    ins = load_json("instances_sample.json")
    log("INFO", f"数据: 分类{len(cls['data']) if cls else 0} + "
                f"著作{len(wrk['data']) if wrk else 0} + "
                f"版本{len(ins['data']) if ins else 0}")

    if not cls and not ins:
        log("FATAL", "无数据, 先运行 ingest_shlib_gj.py")
        return

    backup()
    enrich()

    print(f"\n扩充完成! 古籍数据已写入 works.db")

if __name__ == "__main__":
    main()
