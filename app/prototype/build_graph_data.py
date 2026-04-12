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
        rtype = str(rel.get('type', '')).strip()
        specialty = str(rel.get('specialty', '') or '').strip()

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

        if not src_name or not tgt_name or src_name == tgt_name:
            continue

        links.append({
            'source': src_name,
            'target': tgt_name,
            'type': rtype,
            'specialty': specialty
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

print(f"\nWritten: {out_path}")
print(f"\nType distribution:")
for t, c in Counter(n['type'] for n in nodes).most_common():
    print(f"  {t}: {c}")
print(f"\nLink distribution:")
for t, c in Counter(l['type'] for l in links).most_common():
    print(f"  {t}: {c}")
