#!/usr/bin/env python3
"""Goal Scorers Data Pipeline — real-time + daily refresh
- Phase 1 (real-time): Parse cup.txt goal details after each sync
- Phase 2 (daily): Scrape Wikipedia for comprehensive list
- Merge: Wikipedia as base, cup.txt supplements new goals
"""
import json, re, sys, io, os, urllib.request, gzip, ssl
from collections import Counter
if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

def ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def parse_cuptxt_goals(cup_path=None):
    """Parse goal scorers from cup.txt detail lines.

    Handles:
      - Standard:      (Player Name 23', Other Name 45')
      - Injury time:   (Player 90+4')
      - Single name:   (Mauricio 73')
      - Penalty/OG:    (Player 17'(p))  (Player 7'(og))
      - Multi-goal:    (Player 31', 45+5')  — comma-separated minutes
      - Multi-line:    scorers spanning multiple lines
      - Hyphenated:    (Hwang In-Beom 67')
      - Particles:     (Virgil van Dijk 51')
    """
    if cup_path is None:
        cup_path = os.path.join(REPO, '2026--usa', 'cup.txt')
    goals = Counter()
    if not os.path.exists(cup_path):
        return goals

    with open(cup_path, encoding='utf-8') as f:
        lines = f.readlines()

    # Merge continuation lines: lines that continue a goal-detail block from
    # the previous line (no UTC/@ markers, contains ', starts with whitespace+capital).
    merged_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if (merged_lines and
            re.match(r'^\s+[A-ZÁÉÍÓÚÜÑ]', line) and
            "'" in line and
            '@' not in line and
            'UTC' not in line):
            merged_lines[-1] = merged_lines[-1].rstrip() + ' ' + line.strip()
        else:
            merged_lines.append(line)
        i += 1

    skip_names = {'Penalty', 'Extra', 'Time', 'Half', 'Full', 'Goal', 'Kick',
                  'Own', 'Own Goal', 'Pen', 'Penalty Kick', 'Free Kick',
                  'Corner', 'Corner Kick', 'Header', 'Volley'}

    for line in merged_lines:
        if "'" not in line:
            continue

        # Preprocess: replace nested parens like (p), (og), (pen), (aet), (o.g.)
        # with placeholder tokens so they don't break outer-paren matching.
        line_clean = re.sub(
            r'\((?:p|og|pen|aet|o\.?g\.?|pen\.?)\)',
            '[MARKER]', line, flags=re.IGNORECASE)

        # Find outermost parenthesized goal blocks by counting paren depth
        pos = 0
        while pos < len(line_clean):
            start = line_clean.find('(', pos)
            if start == -1:
                break
            # Find matching close paren
            depth = 1
            end = start + 1
            while end < len(line_clean) and depth > 0:
                if line_clean[end] == '(':
                    depth += 1
                elif line_clean[end] == ')':
                    depth -= 1
                end += 1
            if depth != 0:
                pos = start + 1
                continue

            block = line_clean[start+1:end-1]
            # Restore markers to their original form (for correct parsing)
            block = block.replace('[MARKER]', '')

            # Only process if block contains minute markers
            if "'" not in block:
                pos = end
                continue

            # Find all minute markers: digits or digits+digits followed by '
            minute_matches = list(re.finditer(r'(\d+(?:\+\d+)?)\'', block))

            # Find all name candidates (sequences of capitalized words,
            # possibly separated by lowercase particles like van, de, der).
            # Pattern: CapWord (space [particle space]? CapWord)*
            # CapWord allows internal capitals (McGinn, In-Beom) and hyphens.
            cap_word = r'[A-ZÁÉÍÓÚÜÑ][-A-ZÁÉÍÓÚÜÑa-záéíóúüñ]+'
            lc_particle = r'(?:van|de|der|den|ter|von|van der|van de|van den|el|al|di|da|dos|las|los|del|della|delle|dello|dei|degli)'
            name_pattern = re.compile(
                rf'{cap_word}'
                rf'(?:\s+(?:{lc_particle}\s+)?{cap_word})*')

            name_matches = list(name_pattern.finditer(block))

            # Map each minute to its closest preceding name
            for mm in minute_matches:
                mpos = mm.start()
                best_name = None
                best_dist = 999
                for nm in name_matches:
                    if nm.end() <= mpos:
                        dist = mpos - nm.end()
                        # Allow comma/space/semicolon/paren between name and minute
                        between = block[nm.end():mpos]
                        if re.match(r'^[\s,\';\-]*$', between) and dist < best_dist:
                            best_dist = dist
                            best_name = nm.group().strip()

                if best_name and len(best_name) > 2 and best_name not in skip_names:
                    goals[best_name] += 1

            pos = end

    return goals

def fetch_name_cn_map():
    """Build English → Chinese name mapping from player_details.json."""
    details_path = os.path.join(REPO, 'player_details.json')
    name_cn = {}
    if os.path.exists(details_path):
        players = json.load(open(details_path, encoding='utf-8'))
        for en, p in players.items():
            if p.get('name_cn'):
                name_cn[en] = p['name_cn']
    return name_cn

def _normalize_name(name: str) -> str:
    """Strip accents and special chars for dedup comparison.
    'Kylian Mbappé' → 'Kylian Mbappe'
    'Ousmane Dembélé' → 'Ousmane Dembele'
    """
    import unicodedata
    nfkd = unicodedata.normalize('NFKD', name)
    return nfkd.encode('ascii', 'ignore').decode('ascii')


def update_goalscorers(cuptxt_goals: Counter, name_cn: dict) -> dict:
    """Update goalscorers.json: merge cup.txt goals into existing data."""
    gpath = os.path.join(REPO, 'goalscorers.json')

    try:
        goals = json.load(open(gpath, encoding='utf-8'))
    except Exception:
        goals = {'wc2026': [], 'all_time': [], 'total_2026_scorers': 0, 'total_2026_goals': 0}

    # Build index by normalized name for dedup
    existing = {}  # normalized_name -> index
    for i, p in enumerate(goals.get('wc2026', [])):
        norm = _normalize_name(p['name'])
        if norm not in existing:
            existing[norm] = i
        else:
            # Duplicate: merge into first occurrence, keep accented version
            first_idx = existing[norm]
            # Prefer accented version for display
            if len(p['name']) > len(goals['wc2026'][first_idx]['name']):
                goals['wc2026'][first_idx]['name'] = p['name']
            if p.get('name_cn') and not goals['wc2026'][first_idx].get('name_cn'):
                goals['wc2026'][first_idx]['name_cn'] = p['name_cn']

    # Update existing entries with cup.txt counts
    for name, count in cuptxt_goals.items():
        norm = _normalize_name(name)
        if norm in existing:
            idx = existing[norm]
            goals['wc2026'][idx]['goals'] = max(goals['wc2026'][idx]['goals'], count)
            # Prefer accented version
            if len(name) > len(goals['wc2026'][idx]['name']):
                goals['wc2026'][idx]['name'] = name
        else:
            cn = name_cn.get(name, '')
            goals['wc2026'].append({'name': name, 'goals': count, 'name_cn': cn})
            existing[norm] = len(goals['wc2026']) - 1

    # Remove entries that were merged as duplicates
    seen_norms = set()
    deduped = []
    for p in goals['wc2026']:
        norm = _normalize_name(p['name'])
        if norm not in seen_norms:
            seen_norms.add(norm)
            deduped.append(p)
        else:
            # Merge goal counts
            for dp in deduped:
                if _normalize_name(dp['name']) == norm:
                    dp['goals'] = max(dp['goals'], p['goals'])
                    break

    # Re-sort
    deduped.sort(key=lambda x: -x['goals'])
    goals['wc2026'] = deduped
    goals['total_2026_scorers'] = len(deduped)
    goals['total_2026_goals'] = sum(p['goals'] for p in deduped)

    from datetime import datetime
    goals['updated'] = datetime.now().strftime('%Y-%m-%d %H:%M')

    json.dump(goals, open(gpath, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    return goals

def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--cup-only', action='store_true', help='Only parse cup.txt, skip Wikipedia')
    args = p.parse_args()

    # Phase 1: Real-time from cup.txt
    cuptxt = parse_cuptxt_goals()
    name_cn = fetch_name_cn_map()
    result = update_goalscorers(cuptxt, name_cn)

    new_from_cup = sum(1 for p in result['wc2026'] if p['name'] in cuptxt)
    print(f'[GOALS] cup.txt: {len(cuptxt)} new scorers | total: {len(result["wc2026"])} players | {result["total_2026_goals"]} goals')
    return result

if __name__ == '__main__':
    main()
