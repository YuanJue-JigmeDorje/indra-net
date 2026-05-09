#!/usr/bin/env python3
"""
gazetteer_prescan.py — 预扫描源文本，用 buddhist-vocab.yaml 匹配候选实体

用途：在 SKILL_03a Agent 提取之前运行，产出候选实体清单，喂给 Agent 做精细分类+关系分析

输入:
  - doc/buddhist-vocab.yaml (术语词表)
  - source/dudjom/chapter_md/*.md (源文本)

输出:
  - kg/prescan/ch{NN}_candidates.yaml (每章的候选实体清单)
    每条含: term, type, occurrences [{position, context}]
"""

import re
import os
import json
import yaml
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent.parent
VOCAB_PATH = ROOT / "doc" / "buddhist-vocab.yaml"
CHAPTER_DIR = ROOT / "source" / "dudjom" / "chapter_md"
GRAPH_DATA = ROOT / "app" / "prototype" / "graph_data.js"
MERGED_GAZETTEER = ROOT / "resources" / "dictionaries" / "merged_gazetteer_st.txt"
OUT_DIR = ROOT / "kg" / "prescan"

CHAPTERS = [
    ("01", "01_佛教总况.md"),
    ("02", "02_金刚密乘.md"),
    ("03", "03_藏传佛法.md"),
    ("04", "04_内密三续.md"),
    ("05", "05_远传经幻心.md"),
    ("06", "06_近传伏藏史.md"),
    ("07", "07_遣除邪见.md"),
    ("08", "08_佛教年表与自传.md"),
]


def load_vocab():
    """Load all known terms from vocab + existing graph_data entities."""
    terms = {}  # name → type

    # 1. Buddhist vocab yaml (small curated list with types)
    if VOCAB_PATH.exists():
        with open(VOCAB_PATH) as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            for etype, names in data.items():
                if isinstance(names, list):
                    for n in names:
                        if isinstance(n, str) and len(n) >= 2:
                            terms[n] = etype

    # 1b. Merged gazetteer (82k terms from 丁福保+佛光, no type info)
    if MERGED_GAZETTEER.exists():
        with open(MERGED_GAZETTEER) as f:
            for line in f:
                t = line.strip()
                if t and len(t) >= 2 and t not in terms:
                    terms[t] = "未分类"  # type unknown, Agent will classify

    # 2. Existing graph_data.js entities
    if GRAPH_DATA.exists():
        with open(GRAPH_DATA) as f:
            text = f.read()
        try:
            ns = text.index('const nodes = ') + len('const nodes = ')
            ne = text.index(';\n', ns)
            nodes = json.loads(text[ns:ne])
            for n in nodes:
                if n.get("id") and len(n["id"]) >= 2:
                    terms[n["id"]] = n.get("type", "unknown")
                for a in (n.get("aliases") or []):
                    if a and len(a) >= 2:
                        terms[a] = n.get("type", "unknown")
        except:
            pass

    # 3. Auto-detect 《》 pattern (will be done per chapter)
    return terms


def clean_text(raw):
    """Merge PDF line breaks, strip footnotes."""
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    # Strip footnote markers
    raw = re.sub(r'(?<=[一-鿿）」、。]) ?\d{1,3}[\s]*(?=[一-鿿（「，。])', '', raw)
    # Merge single newlines
    raw = raw.replace('\n\n', '<<PARA>>')
    raw = raw.replace('\n', '')
    raw = raw.replace('<<PARA>>', '\n')
    return raw


def scan_chapter(ch_num, filename, terms):
    """Scan a chapter and return candidate entities with context."""
    fpath = CHAPTER_DIR / filename
    if not fpath.exists():
        return []

    with open(fpath) as f:
        raw = f.read()

    text = clean_text(raw)

    # Also detect 《》 in this chapter
    for m in re.findall(r'《([^》]+)》', text):
        name = m.strip()
        if name and len(name) >= 2 and name not in terms:
            terms[name] = "经典"
            terms[f"《{name}》"] = "经典"

    # Sort terms longest first for matching
    sorted_terms = sorted(terms.keys(), key=lambda x: -len(x))

    # Scan text for all occurrences
    candidates = defaultdict(lambda: {"type": "", "occurrences": []})

    for term in sorted_terms:
        if len(term) < 2:
            continue
        for m in re.finditer(re.escape(term), text):
            start = m.start()
            # Extract context (50 chars around)
            ctx_start = max(0, start - 30)
            ctx_end = min(len(text), start + len(term) + 30)
            context = text[ctx_start:ctx_end]

            entry = candidates[term]
            entry["type"] = terms.get(term, "unknown")
            if len(entry["occurrences"]) < 5:  # max 5 examples
                entry["occurrences"].append({
                    "position": start,
                    "context": context,
                })

    return dict(candidates)


def main():
    print("Loading vocabulary...")
    terms = load_vocab()
    print(f"  {len(terms)} terms loaded")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for ch_num, filename in CHAPTERS:
        print(f"\nScanning ch{ch_num}...")
        candidates = scan_chapter(ch_num, filename, terms.copy())

        # Filter: only keep terms that actually appeared
        found = {k: v for k, v in candidates.items() if v["occurrences"]}
        print(f"  {len(found)} candidate entities found")

        # Output
        out_path = OUT_DIR / f"ch{ch_num}_candidates.yaml"

        # Write as yaml
        output = {
            "chapter": ch_num,
            "source": filename,
            "total_candidates": len(found),
            "candidates": []
        }
        for name, info in sorted(found.items(), key=lambda x: -len(x[1]["occurrences"])):
            output["candidates"].append({
                "term": name,
                "type": info["type"],
                "count": len(info["occurrences"]),
                "examples": [occ["context"] for occ in info["occurrences"][:3]],
            })

        with open(out_path, 'w') as f:
            yaml.dump(output, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        print(f"  → {out_path}")

    # Also generate a summary for Agent prompts
    print("\n\nGenerating Agent-ready candidate summaries...")
    for ch_num, filename in CHAPTERS:
        cand_path = OUT_DIR / f"ch{ch_num}_candidates.yaml"
        if not cand_path.exists():
            continue
        with open(cand_path) as f:
            data = yaml.safe_load(f)

        # Generate concise summary for Agent prompt
        summary_path = OUT_DIR / f"ch{ch_num}_for_agent.txt"
        with open(summary_path, 'w') as f:
            f.write(f"# 第{int(ch_num)}品 候选实体清单（gazetteer 预扫描）\n")
            f.write(f"# 共 {data['total_candidates']} 个候选\n")
            f.write(f"# Agent 请确认类型并分析关系\n\n")
            for c in data.get("candidates", []):
                f.write(f"- {c['term']} [{c['type']}] (出现{c['count']}次)\n")
                if c.get("examples"):
                    f.write(f"  例: \"{c['examples'][0]}\"\n")
        print(f"  ch{ch_num}: {data['total_candidates']} candidates → {summary_path.name}")


if __name__ == "__main__":
    main()
