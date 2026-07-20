#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
enrich_gj_crossref.py — 建立古籍(gj)数据与 Timeline 人物/作品的关联
==================================================================
读取 _stage/shlib/gj/ 中已摄取的古籍实体，与 works.db 的 authors/works 表
进行智能匹配，生成 gj_timeline_crossref 关联表。

匹配策略:
  1. SHL person URI → 获取 chs/cht 标签 → 精确匹配 authors.name
  2. gj_instances.creator_text → 提取人名 → 模糊匹配 authors.name
  3. gj_works.title → 精确/模糊匹配 works.title
  4. 版本中的 creator URI 反向链接到 timeline 作者
"""
import json, sqlite3, shutil, re, sys, io, time
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

TIMELINE_DB = Path("D:/AI探索学习/timeline/data/works.db")
STAGE_DIR = Path("D:/AI探索学习/DobGuski/_stage/shlib/gj")

def log(level, msg):
    print(f"[{datetime.now():%H:%M:%S}] [XREF] [{level}] {msg}")

def load_json(filename):
    path = STAGE_DIR / filename
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding='utf-8'))

def backup():
    backup_path = TIMELINE_DB.parent / f"works_backup_xref_{datetime.now():%Y%m%d_%H%M%S}.db"
    shutil.copy2(TIMELINE_DB, backup_path)
    log("OK", f"备份: {backup_path.name}")

def extract_label(props):
    labels = props.get("http://bibframe.org/vocab/label", []) or \
             props.get("http://id.loc.gov/ontologies/bibframe/label", [])
    for lbl in labels:
        if lbl.get("lang") in ("chs", "cht"):
            return lbl["value"], lbl.get("lang", "chs")
    if labels:
        return labels[0]["value"], "unknown"
    return "", ""

def extract_names_from_creator_text(text):
    """从 '宋呂大防、蔡興宗、魯訔編' 中提取单独人名"""
    names = []
    text = re.sub(r'^[唐宋元明清朝民]', '', text)
    text = re.sub(r'(編|撰|著|纂|修|輯|校|注|訂|補|等)$', '', text)
    for part in re.split(r'[、，,\s]+', text):
        part = part.strip()
        if len(part) >= 2:
            names.append(part)
    return names

def main():
    print("=" * 60)
    print("  enrich_gj_crossref.py — 古籍↔Timeline 交叉关联")
    print(f"  {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 60)

    ins_data = load_json("instances_sample.json")
    wrk_data = load_json("works_sample.json")
    pmap_data = load_json("person_instance_map.json")

    conn = sqlite3.connect(str(TIMELINE_DB))
    backup()

    # ── Update gj tables with new data first ──
    # New instances
    existing_ins = set(r[0] for r in conn.execute("SELECT uri FROM gj_instances").fetchall())
    new_ins_added = 0
    if ins_data:
        for uri, entity in ins_data["data"].items():
            if uri in existing_ins:
                continue
            props = entity.get(uri, {})
            label, _ = extract_label(props)
            titles = props.get("http://purl.org/dc/elements/1.1/title", [])
            t_chs = t_cht = t_py = ""
            for t in titles:
                if t.get("lang") == "chs": t_chs = t["value"]
                elif t.get("lang") == "cht": t_cht = t["value"]
                elif t.get("lang") == "zh-pny": t_py = t["value"]

            work_uri = ""
            for w in props.get("http://bibframe.org/vocab/instanceOf", []):
                work_uri = w.get("value", ""); break

            creator = ""
            for c in props.get("http://purl.org/dc/elements/1.1/creator", []):
                creator = c.get("value", ""); break

            edition = ""
            for e in props.get("http://bibframe.org/vocab/edition", []):
                edition = e.get("value", "").split("/")[-1]; break

            cls_uri = ""
            for c in props.get("http://bibframe.org/vocab/classification", []):
                if c.get("type") == "uri": cls_uri = c.get("value", ""); break

            vol = ""
            for v in props.get("http://pmb.library.sh.cn/ontology/volumeName", []):
                vol = v.get("value", ""); break

            cat_id = ""
            for i in props.get("http://purl.org/dc/elements/1.1/identifier", []):
                cat_id = i.get("value", ""); break

            temporal = ""
            for t in props.get("http://www.library.sh.cn/ontology/temporalValue", []):
                temporal = t.get("value", ""); break

            try:
                conn.execute("""INSERT OR IGNORE INTO gj_instances
                    (uri,label,title_chs,title_cht,title_pinyin,work_uri,creator_text,edition_type,classification_uri,volume_name,catalog_id,temporal_label)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (uri, label, t_chs, t_cht, t_py, work_uri, creator, edition, cls_uri, vol, cat_id, temporal))
                new_ins_added += 1
            except: pass

    # New works
    existing_wrk = set(r[0] for r in conn.execute("SELECT uri FROM gj_works").fetchall())
    new_wrk_added = 0
    if wrk_data:
        for uri, entity in wrk_data["data"].items():
            if uri in existing_wrk:
                continue
            props = entity.get(uri, {})
            t_chs = t_cht = t_py = ""
            for t in props.get("http://purl.org/dc/elements/1.1/title", []):
                if t.get("lang") == "chs": t_chs = t["value"]
                elif t.get("lang") == "cht": t_cht = t["value"]
                elif t.get("lang") == "zh-pny": t_py = t["value"]
            try:
                conn.execute("INSERT OR IGNORE INTO gj_works(uri,title_chs,title_cht,title_pinyin) VALUES(?,?,?,?)",
                             (uri, t_chs, t_cht, t_py))
                new_wrk_added += 1
            except: pass

    # New person links
    existing_links = set()
    for r in conn.execute("SELECT instance_uri, person_uri FROM gj_work_persons").fetchall():
        existing_links.add((r[0], r[1]))
    new_links = 0
    if ins_data:
        for uri, entity in ins_data["data"].items():
            props = entity.get(uri, {})
            for pred in ["http://bibframe.org/vocab/creator", "http://bibframe.org/vocab/contribution"]:
                for ref in props.get(pred, []):
                    person_uri = ref.get("value", "")
                    if "entity/person" in person_uri and (uri, person_uri) not in existing_links:
                        role = "creator" if "creator" in pred else "contributor"
                        conn.execute("INSERT OR IGNORE INTO gj_work_persons(instance_uri,person_uri,role_type) VALUES(?,?,?)",
                                     (uri, person_uri, role))
                        new_links += 1
                        existing_links.add((uri, person_uri))

    log("OK", f"新增: {new_ins_added} 版本 + {new_wrk_added} 著作 + {new_links} 人物链接")

    # ── Build cross-reference table ──
    conn.execute("DROP TABLE IF EXISTS gj_timeline_crossref")
    conn.execute("""
        CREATE TABLE gj_timeline_crossref (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gj_entity_type TEXT,     -- instance/work/person
            gj_uri TEXT,
            gj_label TEXT,
            timeline_table TEXT,      -- authors/works
            timeline_id INTEGER,
            timeline_name TEXT,
            match_type TEXT,          -- person_exact/person_fuzzy/title_exact/title_contains
            match_confidence REAL DEFAULT 1.0,
            extra_info TEXT
        )
    """)

    # ── Crossref 1: Person URI → authors (via SHL labels already matched) ──
    # We use the person_instance_map from the expansion step
    xref_count = 0
    if pmap_data:
        for person_uri, inst_uris in pmap_data.items():
            # Look up the person entity to get their name
            person_file = STAGE_DIR / "persons_sample.json"
            person_name = ""
            if person_file.exists():
                persons = json.loads(person_file.read_text(encoding='utf-8')).get("data", {})
                if person_uri in persons:
                    entity = persons[person_uri]
                    props = entity.get(person_uri, {})
                    person_name, _ = extract_label(props)

            if not person_name:
                # Extract from URI
                person_name = person_uri.split("/")[-1]

            # Match against authors
            author = conn.execute("SELECT id, name, dynasty_id FROM authors WHERE name=?", (person_name,)).fetchone()
            if author:
                conn.execute("""INSERT INTO gj_timeline_crossref
                    (gj_entity_type, gj_uri, gj_label, timeline_table, timeline_id, timeline_name, match_type)
                    VALUES('person',?,?,'authors',?,?,'person_exact')""",
                    (person_uri, person_name, author[0], author[1]))
                xref_count += 1
                # Also link all instances by this person
                for inst_uri in inst_uris:
                    conn.execute("""INSERT OR IGNORE INTO gj_timeline_crossref
                        (gj_entity_type, gj_uri, gj_label, timeline_table, timeline_id, timeline_name, match_type, extra_info)
                        VALUES('instance',?,?,'authors',?,?,'via_person','editor/contributor')""",
                        (inst_uri, inst_uri.split("/")[-1], author[0], author[1]))
                    xref_count += 1

    # ── Crossref 2: gj_works.title → works.title ──
    gj_titles = conn.execute("SELECT uri, title_chs, title_cht FROM gj_works WHERE title_chs != '' OR title_cht != ''").fetchall()
    for uri, chs, cht in gj_titles:
        for term in [chs, cht]:
            if not term or len(term) < 3:
                continue
            # Exact match
            rows = conn.execute("SELECT id, title, dynasty FROM works WHERE title=?", (term,)).fetchall()
            for r in rows:
                conn.execute("""INSERT OR IGNORE INTO gj_timeline_crossref
                    (gj_entity_type, gj_uri, gj_label, timeline_table, timeline_id, timeline_name, match_type)
                    VALUES('work',?,?,'works',?,?,'title_exact')""",
                    (uri, term, r[0], r[1]))
                xref_count += 1

    # ── Crossref 3: instance creator_text → authors ──
    creators = conn.execute("SELECT uri, creator_text, title_chs FROM gj_instances WHERE creator_text != ''").fetchall()
    for uri, creator_text, title in creators:
        names = extract_names_from_creator_text(creator_text)
        for name in names:
            author = conn.execute("SELECT id, name FROM authors WHERE name=?", (name,)).fetchone()
            if author:
                conn.execute("""INSERT OR IGNORE INTO gj_timeline_crossref
                    (gj_entity_type, gj_uri, gj_label, timeline_table, timeline_id, timeline_name, match_type, extra_info)
                    VALUES('instance',?,?,'authors',?,?,'creator_text_exact',?)""",
                    (uri, title or uri.split("/")[-1], author[0], author[1], creator_text))
                xref_count += 1

    conn.commit()

    # ── Summary ──
    total_ins = conn.execute("SELECT COUNT(*) FROM gj_instances").fetchone()[0]
    total_wrk = conn.execute("SELECT COUNT(*) FROM gj_works").fetchone()[0]
    total_links = conn.execute("SELECT COUNT(*) FROM gj_work_persons").fetchone()[0]
    xref_total = conn.execute("SELECT COUNT(*) FROM gj_timeline_crossref").fetchone()[0]

    print(f"\n{'='*60}")
    print(f"  古籍数据总量: {total_ins} 版本 + {total_wrk} 著作 + {total_links} 人物链接")
    print(f"  交叉关联: {xref_count} 条")
    print(f"  {conn.execute('SELECT COUNT(DISTINCT timeline_id) FROM gj_timeline_crossref WHERE timeline_table=\"authors\"').fetchone()[0]} 位作者, "
          f"{conn.execute('SELECT COUNT(DISTINCT timeline_id) FROM gj_timeline_crossref WHERE timeline_table=\"works\"').fetchone()[0]} 部作品")
    print(f"{'='*60}")

    # Show top matches
    print("\nTop matched authors:")
    for r in conn.execute("""
        SELECT timeline_name, COUNT(*) as cnt, gj_entity_type
        FROM gj_timeline_crossref
        WHERE timeline_table='authors'
        GROUP BY timeline_name ORDER BY cnt DESC LIMIT 15
    """).fetchall():
        print(f"  {r[0]:12} → {r[2]:8} × {r[1]}")

    conn.close()

if __name__ == "__main__":
    main()
