#!/usr/bin/env python3
"""
从 kg/ yaml 文件中构建干净的图数据。
处理：entity ID → name 解析、括号注释清洗、type 查找。
"""
import yaml, re, json, glob, os
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KG = os.path.join(ROOT, "kg")

def clean_name(name):
    if not name: return ""
    name = re.sub(r'\s*[\(（][^)）]*[\)）]\s*$', '', str(name)).strip()
    return name

# ============================================================
# 1. 建全局 entity ID → {name, type} 映射
# ============================================================
id_to_entity = {}  # key = "ch04-part1:E_001" or "E_001" etc.

entity_files = sorted(glob.glob(os.path.join(KG, "entities", "*.yaml")) +
                       glob.glob(os.path.join(KG, "poc", "*.yaml")))

for fpath in entity_files:
    fname = os.path.basename(fpath).replace('.yaml', '')

    # 确定 chapter prefix (用于 ch04 的 P1/P2/P3 映射)
    ch04_part = None
    if 'ch04-part1' in fname: ch04_part = 'P1'
    elif 'ch04-part2' in fname: ch04_part = 'P2'
    elif 'ch04-part3' in fname: ch04_part = 'P3'

    with open(fpath, 'r') as f:
        content = f.read()

    # 先尝试 yaml 解析
    try:
        data = yaml.safe_load(content)
    except:
        data = None

    items = {}

    if isinstance(data, dict):
        # 处理两种结构：
        # A: 顶层直接是 E_NNN: {name, type}
        # B: 有 entities: 字段
        entities_dict = data.get('entities', None)
        if entities_dict and isinstance(entities_dict, dict):
            items = entities_dict
        else:
            items = {k: v for k, v in data.items()
                     if isinstance(v, dict) and 'name' in v}

    # 如果 yaml 解析失败或 items 为空，用 regex 回退
    if not items:
        current_id = None
        for line in content.split('\n'):
            m = re.match(r'\s*(E_[A-Za-z]?\d+):', line)
            if m:
                current_id = m.group(1)
                items[current_id] = {}
                continue
            if current_id:
                m2 = re.match(r'\s+name:\s*(.+)', line)
                if m2:
                    items[current_id]['name'] = m2.group(1).strip().strip('"\'')
                m3 = re.match(r'\s+type:\s*(.+)', line)
                if m3:
                    items[current_id]['type'] = m3.group(1).strip().strip('"\'')
                # 空行或新 block → reset
                if line.strip() == '' or (line and not line.startswith(' ')):
                    current_id = None

    for eid, edata in items.items():
        name = clean_name(edata.get('name', ''))
        etype = str(edata.get('type', '')).strip()

        if not name:
            continue

        entry = {'name': name, 'type': etype}

        # 注册多种 ID 格式
        id_to_entity[eid] = entry                           # E_001
        id_to_entity[f"{fname}:{eid}"] = entry              # ch04-part1:E_001
        if ch04_part:
            id_to_entity[f"{ch04_part}.{eid}"] = entry      # P1.E_001

print(f"Entity ID map: {len(id_to_entity)} entries")

# 也建 name → type 映射（用于 fallback）
name_to_type = {}
for entry in id_to_entity.values():
    if entry['name'] and entry['type']:
        name_to_type[entry['name']] = entry['type']

print(f"Name→type map: {len(name_to_type)} entries")

# ============================================================
# 1.5 Build alias→canonical merge map (for dedup)
# ============================================================
alias_to_canonical = {}
for fpath in entity_files:
    with open(fpath, 'r') as f:
        content = f.read()
    current_name = None
    for line in content.split('\n'):
        m = re.match(r'\s+name:\s*(.+)', line)
        if m:
            current_name = clean_name(m.group(1).strip().strip('"\''))
        m2 = re.match(r'\s+aliases:\s*\[(.+)\]', line)
        if m2 and current_name:
            aliases = [clean_name(a.strip().strip('"\'')) for a in m2.group(1).split(',')]
            for alias in aliases:
                if alias and alias != current_name:
                    alias_to_canonical[alias] = current_name

# Manual merges for known duplicates not caught by alias files
alias_to_canonical.update({
    '贡巴绕色大师': '贡巴绕色',
    '龙钦巴': '无垢光尊者',
    '文殊': '文殊菩萨',
    '鲁墨大师': '鲁墨·赤诚西绕',
    '桑吉温波': '桑给嘉巴桑吉温波',
    '西绕炯内': '酿·西绕炯内',
    '巴够贝若札那': '贝若札那',
    '多昂丹增': '多昂丹增诺吾',
    # 地名限定词变体
    '印度金刚座': '金刚座',
    # 称号变体
    '圣天论师': '圣天',
    '帝释天王': '帝释天',
})

# Substring-based auto-merge: if A is a strict substring of B (len>=3) and both in alias map's values
# then merge shorter into longer (use shorter as canonical)
# This catches cases like 贡巴绕色 vs 贡巴绕色大师

def normalize_name(name):
    return alias_to_canonical.get(name, name)

print(f"Alias→canonical map: {len(alias_to_canonical)} entries")

# ============================================================
# 1.6 Load source texts for quote expansion
# ============================================================
source_texts = {}
chapter_files = {
    'ch01': os.path.join(ROOT, 'source/dudjom/chapter_md/01_佛教总况.md'),
    'ch02': os.path.join(ROOT, 'source/dudjom/chapter_md/02_金刚密乘.md'),
    'ch03': os.path.join(ROOT, 'source/dudjom/chapter_md/03_藏传佛法.md'),
    'ch04': os.path.join(ROOT, 'source/dudjom/chapter_md/04_内密三续.md'),
    'ch05': os.path.join(ROOT, 'source/dudjom/chapter_md/05_远传经幻心.md'),
    'ch06': os.path.join(ROOT, 'source/dudjom/chapter_md/06_近传伏藏史.md'),
    'ch07': os.path.join(ROOT, 'source/dudjom/chapter_md/07_遣除邪见.md'),
    'ch08': os.path.join(ROOT, 'source/dudjom/chapter_md/08_佛教年表与自传.md'),
}
for ch, fpath in chapter_files.items():
    if os.path.exists(fpath):
        with open(fpath, 'r') as f:
            raw = f.read()
        # 合并 PDF 硬换行：单个 \n 替换为空（同一段落内的换行），保留 \n\n（段落分隔）
        raw = raw.replace('\n\n', '<<PARA>>')
        raw = raw.replace('\n', '')
        raw = raw.replace('<<PARA>>', '\n')
        source_texts[ch] = raw

def expand_quote(short_quote, chapter_key, target_len=100):
    """扩展短引用：在源文本中找到位置，向前后扩展到句号。"""
    if not short_quote:
        return short_quote
    # 清理引用文本用于搜索
    search_q = short_quote.strip().strip('「」""')
    # 也去掉搜索词中的空格/换行（源文本已合并）
    search_q = search_q.replace('\n', '').replace(' ', '').replace('\u3000', '')
    if len(search_q) < 3:
        return short_quote

    text = source_texts.get(chapter_key, '')
    if not text:
        return short_quote

    pos = text.find(search_q)
    if pos == -1:
        # 逐步缩短搜索词尝试匹配
        for trylen in [20, 15, 10, 6]:
            if len(search_q) > trylen:
                pos = text.find(search_q[:trylen])
                if pos >= 0:
                    break
        if pos == -1:
            return short_quote

    # 向前找句号（最多 300 字）
    start = pos
    for i in range(pos - 1, max(pos - 300, 0) - 1, -1):
        if text[i] == '。':
            start = i + 1
            break

    # 向后找句号（最多 300 字）
    end = pos + len(search_q)
    for i in range(end, min(end + 300, len(text))):
        if text[i] == '。':
            end = i + 1  # 包含句号
            break

    expanded = text[start:end].strip()

    # 如果扩展后仍然太短（<60字），再向前多取一句
    if len(expanded) < 60 and start > 1:
        for i in range(start - 2, max(start - 300, 0) - 1, -1):
            if text[i] == '。':
                expanded = text[i+1:end].strip()
                break

    return expanded if expanded else short_quote

print(f"Source texts loaded: {list(source_texts.keys())}")

# ============================================================
# 2. 从 relations yaml 提取 links，解析 ID → name
# ============================================================
links = []
node_set = {}  # name → type
unresolved = []

for fpath in sorted(glob.glob(os.path.join(KG, "relations", "*.yaml"))):
    with open(fpath, 'r') as f:
        data = yaml.safe_load(f)

    if isinstance(data, dict):
        rels = data.get('relations', [])
    elif isinstance(data, list):
        rels = data
    else:
        rels = []

    for rel in rels:
        if not isinstance(rel, dict):
            continue

        src_raw = str(rel.get('source', '')).strip()
        tgt_raw = str(rel.get('target', '')).strip()
        raw_rtype = str(rel.get('type', '')).strip()
        # Normalize relation type to Chinese
        rtype_map = {
            'teacherOf': '师承', 'manifestationOf': '化身', 'formOf': '形态', 'form_of': '形态',
            'builtBy': '修建', 'foundedBy': '创立', 'rulerOf': '统治', 'fatherOf': '父子',
            'sonOf': '子父', 'consortOf': '配偶', 'consort': '配偶', 'ministerOf': '臣属',
            'siblingOf': '兄弟', 'translatedBy': '译经', 'revisedBy': '译校',
            'subduedBy': '降伏', 'protects': '守护', 'concealedBy': '埋藏',
            'revealedBy': '开取', 'revealedFrom': '掘藏地', 'memberOf': '归属',
            'belongsToSect': '宗派归属', 'locatedIn': '位于', 'cites': '引用',
            'refutes': '驳斥', 'reconciles': '调和', 'alternativeOf': '异说',
            'authorOf': '著作', 'lineageOf': '法脉',
        }
        rtype = rtype_map.get(raw_rtype, raw_rtype)
        raw_spec = rel.get('specialty', '') or ''
        if isinstance(raw_spec, list):
            specialty = ', '.join(str(s) for s in raw_spec)
        else:
            specialty = str(raw_spec).strip()
            # Clean up Python list repr: "['大圆满']" → "大圆满"
            if specialty.startswith('[') and specialty.endswith(']'):
                specialty = specialty[1:-1].replace("'", "").replace('"', '').strip()

        if not src_raw or not tgt_raw or not rtype:
            continue

        # 解析 source
        if src_raw in id_to_entity:
            src_entry = id_to_entity[src_raw]
            src_name = src_entry['name']
            src_type = src_entry['type']
        else:
            src_name = clean_name(src_raw)
            src_type = name_to_type.get(src_name, '')
            if not src_type:
                unresolved.append(('source', src_raw, src_name))

        # 解析 target
        if tgt_raw in id_to_entity:
            tgt_entry = id_to_entity[tgt_raw]
            tgt_name = tgt_entry['name']
            tgt_type = tgt_entry['type']
        else:
            tgt_name = clean_name(tgt_raw)
            tgt_type = name_to_type.get(tgt_name, '')
            if not tgt_type:
                unresolved.append(('target', tgt_raw, tgt_name))

        # Normalize names via alias map
        src_name = normalize_name(src_name)
        tgt_name = normalize_name(tgt_name)

        if not src_name or not tgt_name or src_name == tgt_name:
            continue

        raw_quote = rel.get('source_quote', '') or ''
        if isinstance(raw_quote, list):
            source_quote = '；'.join(str(s) for s in raw_quote)
        else:
            source_quote = str(raw_quote).strip()

        # Source: book > chapter
        fname_base = os.path.basename(fpath).replace('.yaml', '')
        chapter_map = {'ch01': '第一品 佛教总况', 'ch02': '第二品 金刚密乘', 'ch03': '第三品 藏传佛法', 'ch04': '第四品 内密三续', 'ch05': '第五品 远传经幻心', 'ch06': '第六品 近传伏藏史', 'ch07': '第七品 遣除邪见', 'ch08': '第八品 佛教年表与自传'}
        chapter = '《藏密佛教史》> ' + chapter_map.get(fname_base, fname_base)

        # Expand short quotes with surrounding context from source text
        source_quote = expand_quote(source_quote, fname_base)

        links.append({
            'source': src_name,
            'target': tgt_name,
            'type': rtype,
            'specialty': specialty,
            'quote': source_quote,
            'chapter': chapter,
        })

        if src_name not in node_set:
            node_set[src_name] = src_type
        if tgt_name not in node_set:
            node_set[tgt_name] = tgt_type

print(f"\nLinks: {len(links)}")
print(f"Unique nodes: {len(node_set)}")
print(f"Unresolved IDs: {len(unresolved)}")
if unresolved[:5]:
    print("  Examples:", unresolved[:5])

# ============================================================
# 3. 构建 nodes 数组
# ============================================================
def get_base_type(full_type):
    if not full_type: return "unknown"
    base = full_type.split('.')[0].strip()
    return base if base else "unknown"

# Manual type overrides for known entities not in yaml files
manual_types = {
    '噶玛噶举派': '教派',
    # 教法
    '灌顶': '仪轨', '伏藏': '教法', '伏藏必要': '教法', '伏藏本体': '教法',
    '宁玛伏藏': '教法', '帕单巴息法窍诀': '教法', '达波噶举六法大手印': '教法',
    '前译派六殊胜': '教法', '莲师出世': '教法',
    '上师、大圆满、大悲观音三种伏藏': '教法',
    # 经典
    '《三根本修法》': '经典', '《三根本修类》': '经典',
    '《上师集密意续论》': '经典', '《大圆满集普贤密意续》': '经典',
    '《教集后持明总集之法类七品祈祷修法》': '经典', '《普贤通彻密意》': '经典',
    '《长寿修法赐无死吉祥》': '经典',
    # 人物
    '依钦仁波切': '人物', '单真如巴': '人物', '多吉札巴': '人物', '扬攀塔益': '人物',
}

# Non-entity strings to filter out (debate topics from ch07, leaked descriptions)
non_entities = {
    "['大圆满', '大手印', '道果']",
    "['布敦大师舍置宁玛续之说', '布敦大师实修宁玛法之事']",
    '古拉则否定宁玛续之说', '大圆满是和尚宗之说', '大手印是刚波巴伪造之说',
    '宁玛与苯波意趣相同之说', '宁玛续在印度不存在之说', '宁玛续非正法之说',
    '后译续部优于前译之说', '佛法住世五千年说', '舍法之过', '苯波辨别',
    '龙钦巴弘法至海边', '藏地鬼神', '嘉滚罗珠塔益授记',
    '布敦大师舍置宁玛续之说', '布敦大师实修宁玛法之事',
}

# Filter out bad nodes: raw IDs, None, leaked descriptions
def is_valid_node(name):
    if not name or name == 'None':
        return False
    if re.match(r'^E_[A-Za-z]?\d+', name):  # raw entity ID
        return False
    if re.match(r'^P[123]\.\w+', name):  # prefixed ID
        return False
    if any(kw in name for kw in ['为', '至', '弘法', '化身']):
        if len(name) > 8:  # long strings with these keywords are descriptions
            return False
    if name == '授记':  # layer name, not entity
        return False
    if name in non_entities:
        return False
    return True

valid_nodes = {n for n in node_set if is_valid_node(n)}

nodes = []
unknown_count = 0
for name in sorted(valid_nodes):
    full_type = node_set[name] or name_to_type.get(name, '') or manual_types.get(name, '')
    base_type = get_base_type(full_type)
    if base_type == "unknown":
        unknown_count += 1
    nodes.append({
        'id': name,
        'type': base_type,
        'sub_type': full_type or "",
        'aliases': []
    })

# Filter links to only valid nodes
valid_names = {n['id'] for n in nodes}
links = [l for l in links if l['source'] in valid_names and l['target'] in valid_names]

print(f"Unknown type: {unknown_count}/{len(nodes)}")

# ============================================================
# 4. 输出 JS
# ============================================================
out_path = os.path.join(ROOT, "app", "prototype", "graph_data.js")
with open(out_path, 'w') as f:
    f.write(f"// Auto-generated: {len(nodes)} nodes, {len(links)} links\n")
    f.write(f"// Unknown type: {unknown_count}\n\n")
    f.write("const nodes = ")
    f.write(json.dumps(nodes, ensure_ascii=False, indent=2))
    f.write(";\n\nconst links = ")
    f.write(json.dumps(links, ensure_ascii=False, indent=2))
    f.write(";\n")

# ============================================================
# 4. 从 events yaml 提取事件，按参与者索引
# ============================================================
all_events = []  # list of {event_id, type, title, participants, location, time_info, layers, source_quote, chapter}
event_chapter_map = {'ch01': '第一品 佛教总况', 'ch02': '第二品 金刚密乘', 'ch03': '第三品 藏传佛法', 'ch04': '第四品 内密三续', 'ch05': '第五品 远传经幻心', 'ch06': '第六品 近传伏藏史', 'ch07': '第七品 遣除邪见', 'ch08': '第八品 佛教年表与自传'}

for fpath in sorted(glob.glob(os.path.join(KG, "events", "*.yaml")) + glob.glob(os.path.join(KG, "poc", "*.yaml"))):
    fname_base = os.path.basename(fpath).replace('.yaml', '')
    # Determine chapter
    ch_key = fname_base.split('-')[0]  # ch01-part1 → ch01
    ch_name = event_chapter_map.get(ch_key, ch_key)

    try:
        with open(fpath, 'r') as f:
            data = yaml.safe_load(f)
    except:
        continue

    events_list = []
    if isinstance(data, list):
        events_list = data
    elif isinstance(data, dict):
        # Could be {events: [...]} or {EVT_001: {...}, ...} or has 'facts' key (PoC)
        if 'events' in data:
            events_list = data['events'] if isinstance(data['events'], list) else []
        elif 'facts' in data:
            facts = data['facts']
            if isinstance(facts, list):
                events_list = facts
        else:
            events_list = [v for v in data.values() if isinstance(v, dict) and 'type' in v]

    for evt in events_list:
        if not isinstance(evt, dict):
            continue
        # Extract participant names
        participants = []
        raw_parts = evt.get('participants', []) or []
        if isinstance(raw_parts, list):
            for p in raw_parts:
                if isinstance(p, dict):
                    ename = clean_name(str(p.get('entity', p.get('name', ''))))
                    ename = normalize_name(ename)
                    role = str(p.get('role', '')).strip()
                    if ename:
                        participants.append({'entity': ename, 'role': role})

        # Get quote, expand it
        raw_quote = str(evt.get('source_quote', evt.get('quote', '')) or '').strip()
        quote = expand_quote(raw_quote, ch_key)

        all_events.append({
            'type': str(evt.get('type', '')).strip(),
            'title': str(evt.get('title', evt.get('description', '')) or '').strip(),
            'participants': participants,
            'location': clean_name(str(evt.get('location', '') or '')),
            'time_info': str(evt.get('time_info', '') or '').strip(),
            'layers': evt.get('layers', []) or [],
            'quote': quote,
            'chapter': '《藏密佛教史》> ' + ch_name,
        })

# Build entity → events index
entity_events = {}  # entity_name → list of event indices
for i, evt in enumerate(all_events):
    for p in evt['participants']:
        name = p['entity']
        if name not in entity_events:
            entity_events[name] = []
        entity_events[name].append(i)

print(f"Events: {len(all_events)}, entities with events: {len(entity_events)}")

# ============================================================
# 5. 输出 JS (nodes + links + events)
# ============================================================
with open(out_path, 'w') as f:
    f.write(f"// Auto-generated: {len(nodes)} nodes, {len(links)} links, {len(all_events)} events\n")
    f.write(f"// Unknown type: {unknown_count}\n\n")
    f.write("const nodes = ")
    f.write(json.dumps(nodes, ensure_ascii=False, indent=2))
    f.write(";\n\nconst links = ")
    f.write(json.dumps(links, ensure_ascii=False, indent=2))
    f.write(";\n\nconst allEvents = ")
    f.write(json.dumps(all_events, ensure_ascii=False))
    f.write(";\n\nconst entityEventIndex = ")
    f.write(json.dumps(entity_events, ensure_ascii=False))
    f.write(";\n")

print(f"\nWritten: {out_path}")
print(f"\nType distribution:")
for t, c in Counter(n['type'] for n in nodes).most_common():
    print(f"  {t}: {c}")
print(f"\nLink distribution:")
for t, c in Counter(l['type'] for l in links).most_common():
    print(f"  {t}: {c}")
