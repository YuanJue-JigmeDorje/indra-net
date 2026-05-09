#!/usr/bin/env python3
"""
build_reader.py  --  Generate annotated reader HTML from chapter markdown files.

Reads entity data from graph_data.js, reads each chapter .md file,
merges PDF hard line-breaks, annotates known entities with clickable
<span> tags, and writes ch01..ch08.html + index.html into app/reader/.
"""

import json
import yaml
import os
import re
import html as html_mod
from pathlib import Path

# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent.parent          # project root
GRAPH_DATA = ROOT / "app" / "prototype" / "graph_data.js"
CHAPTER_DIR = ROOT / "source" / "dudjom" / "chapter_md"
OUT_DIR = ROOT / "app" / "reader"

CHAPTERS = [
    ("01", "01_佛教总况.md",      "佛教总况"),
    ("02", "02_金刚密乘.md",      "金刚密乘"),
    ("03", "03_藏传佛法.md",      "藏传佛法"),
    ("04", "04_内密三续.md",      "内密三续"),
    ("05", "05_远传经幻心.md",    "远传经幻心"),
    ("06", "06_近传伏藏史.md",    "近传伏藏史"),
    ("07", "07_遣除邪见.md",      "遣除邪见"),
    ("08", "08_佛教年表与自传.md", "佛教年表与自传"),
]

ENTITY_TYPES = {
    "人物", "圣众", "非人", "寺院", "地名",
    "经典", "教法", "教派", "仪轨", "法器圣物", "集合",
}

MIN_NAME_LEN = 2  # skip single-char entity names

# max annotations of the same entity per paragraph
MAX_ANNOTATIONS_PER_ENTITY = 3

# ---------------------------------------------------------------------------
# 1. Parse entities from graph_data.js
# ---------------------------------------------------------------------------
def load_entities():
    """Return list of dicts: {id, type, aliases}."""
    text = GRAPH_DATA.read_text(encoding="utf-8")
    m = re.search(r"const nodes = (\[.*?\]);", text, re.DOTALL)
    if not m:
        raise RuntimeError("Could not find 'const nodes = [...]' in graph_data.js")
    nodes = json.loads(m.group(1))
    entities = []
    for n in nodes:
        if n["type"] in ENTITY_TYPES:
            entities.append({
                "id": n["id"],
                "type": n["type"],
                "aliases": n.get("aliases", []),
            })
    return entities


def auto_detect_texts_from_source(chapter_files: list[str], existing_entities: list) -> list:
    """
    Scan all chapter source texts for 《XXX》 patterns.
    Any book title not already in the entity list gets added as 经典.
    """
    known_names = set()
    for ent in existing_entities:
        known_names.add(ent["id"])
        for a in ent.get("aliases", []):
            known_names.add(a)

    new_entities = []
    seen = set()
    for fpath in chapter_files:
        if not os.path.exists(fpath):
            continue
        with open(fpath, "r") as f:
            raw = f.read()
        # Merge line breaks inside 《》 (PDF page breaks)
        raw = re.sub(r'《([^》]*)\n([^》]*)》', lambda m: '《' + m.group(1) + m.group(2) + '》', raw)
        raw = re.sub(r'《([^》]*)\n([^》]*)》', lambda m: '《' + m.group(1) + m.group(2) + '》', raw)  # twice for nested
        matches = re.findall(r'《([^》]+)》', raw)
        for m in matches:
            name = m.strip()
            if not name or len(name) < 2:
                continue
            full = '《' + name + '》'
            if name in known_names or full in known_names or name in seen:
                continue
            seen.add(name)
            new_entities.append({"id": full, "type": "经典", "aliases": [name]})
            known_names.add(name)
            known_names.add(full)

    return new_entities


def load_buddhist_vocab(vocab_path: str) -> list:
    """Load Buddhist vocabulary gazetteer as supplementary entities."""
    if not os.path.exists(vocab_path):
        return []
    with open(vocab_path, 'r') as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        return []
    entities = []
    for etype, names in data.items():
        if not isinstance(names, list):
            continue
        for name in names:
            if isinstance(name, str) and len(name) >= 2:
                entities.append({"id": name, "type": etype, "aliases": []})
    return entities


def load_merged_gazetteer(gazetteer_path: str) -> list:
    """Load the large merged gazetteer (82k terms, no type info).
    Terms are added as '未分类' — they provide matching coverage
    but won't have colored type annotations until classified."""
    if not os.path.exists(gazetteer_path):
        return []
    entities = []
    with open(gazetteer_path, 'r') as f:
        for line in f:
            name = line.strip()
            if name and len(name) >= 2:
                entities.append({"id": name, "type": "佛学术语", "aliases": []})
    return entities


def build_name_index(entities):
    """
    Return a dict mapping surface_form -> {canonical_id, type}.
    Also return a sorted list of surface forms (longest first).
    """
    index = {}
    for ent in entities:
        names = [ent["id"]] + ent.get("aliases", [])
        for name in names:
            # strip book brackets for the index key too -- we match both
            # with and without brackets in text
            if len(name) < MIN_NAME_LEN:
                continue
            if name not in index:
                index[name] = {"id": ent["id"], "type": ent["type"]}
            # For 经典: index both 《name》 and bare name forms
            bare = name.strip("《》")
            if bare != name and len(bare) >= MIN_NAME_LEN:
                # Has brackets → also index without
                if bare not in index:
                    index[bare] = {"id": ent["id"], "type": ent["type"]}
            elif ent["type"] == "经典" and not name.startswith("《") and len(name) >= MIN_NAME_LEN:
                # No brackets → also index with brackets
                bracketed = "《" + name + "》"
                if bracketed not in index:
                    index[bracketed] = {"id": ent["id"], "type": ent["type"]}
    # sort longest first so greedy matching works
    sorted_names = sorted(index.keys(), key=lambda x: -len(x))
    return index, sorted_names


# ---------------------------------------------------------------------------
# 2. Text pre-processing: merge PDF hard line-breaks
# ---------------------------------------------------------------------------
def preprocess_text(raw: str) -> list[str]:
    """
    LOSSLESS preprocessing: every character from source appears in output.
    Merge PDF hard wraps (single \\n) into continuous text.
    Split into paragraphs at sentence-ending punctuation followed by blank line.
    If a blank line appears mid-sentence, ignore it (PDF page break).
    """
    SENT_END = set('。！？；」）】…"\'')
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")

    # Step 0: clean footnote markers (e.g., "俱胝 10\n四洲" → "俱胝四洲")
    # Footnote numbers may be followed by \n (PDF line break), so include \n in the pattern
    raw = re.sub(r'(?<=[一-鿿）」、。]) ?\d{1,3}[\s]*(?=[一-鿿（「，。])', '', raw)

    # Step 1: merge all lines, tracking where blank lines were
    lines = raw.split("\n")
    merged = ""
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line == "":
            # Blank line: check if we should break paragraph
            if merged and merged[-1] in SENT_END:
                # Sentence ended → paragraph break
                merged += "\n\n"
            # else: mid-sentence page break → just continue (no insertion)
        else:
            merged += line
        i += 1

    # Step 2: split into paragraphs by \n\n
    parts = merged.split("\n\n")
    return [p.strip() for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# 3. Entity annotation
# ---------------------------------------------------------------------------
def annotate_paragraph(text: str, name_index: dict, sorted_names: list[str]) -> str:
    """
    Find entity mentions in *text* and wrap them with <span>.
    Longest-match-first, max MAX_ANNOTATIONS_PER_ENTITY per entity per para.
    """
    # We'll work with a list of (start, end, surface, canonical_id, type) matches.
    matches = []
    used_ranges = []  # (start, end) of already-matched spans
    entity_counts = {}  # canonical_id -> count

    for name in sorted_names:
        if len(name) < MIN_NAME_LEN:
            continue
        # escape for regex
        pattern = re.escape(name)
        for m in re.finditer(pattern, text):
            s, e = m.start(), m.end()
            # check overlap with existing matches
            if any(not (e <= us or s >= ue) for us, ue in used_ranges):
                continue
            info = name_index[name]
            cid = info["id"]
            # enforce per-entity limit
            entity_counts.setdefault(cid, 0)
            if entity_counts[cid] >= MAX_ANNOTATIONS_PER_ENTITY:
                continue
            entity_counts[cid] += 1
            matches.append((s, e, m.group(), cid, info["type"]))
            used_ranges.append((s, e))

    if not matches:
        return html_mod.escape(text)

    # sort by start position
    matches.sort(key=lambda x: x[0])

    parts = []
    prev = 0
    for s, e, surface, cid, etype in matches:
        parts.append(html_mod.escape(text[prev:s]))
        safe_surface = html_mod.escape(surface)
        safe_cid = html_mod.escape(cid)
        safe_type = html_mod.escape(etype)
        parts.append(
            f'<span class="entity entity-{safe_type}" '
            f'data-entity="{safe_cid}" title="{safe_type}">'
            f'{safe_surface}</span>'
        )
        prev = e
    parts.append(html_mod.escape(text[prev:]))
    return "".join(parts)


# ---------------------------------------------------------------------------
# 4. HTML generation
# ---------------------------------------------------------------------------

# CSS & JS are shared across all pages -- inlined for portability.

def css():
    return r"""
/* ---- reset & base ---- */
*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }

:root {
  --bg: #0f0f1a;
  --fg: #d0c8b0;
  --fg-muted: #8a8478;
  --surface: #1a1a2e;
  --border: #2a2a3e;
  --accent: #d4af37;
  --max-w: 800px;
  --line-h: 2.0;
  --font-size: 18px;
  --para-gap: 1.5em;
}

[data-theme="light"] {
  --bg: #f8f5ee;
  --fg: #2a2a2a;
  --fg-muted: #6a6a6a;
  --surface: #ffffff;
  --border: #d8d0c4;
  --accent: #8b6914;
}

html { font-size: var(--font-size); }
body {
  background: var(--bg);
  color: var(--fg);
  font-family: "PingFang SC", "Noto Serif SC", "Source Han Serif SC",
               "Microsoft YaHei", serif;
  line-height: var(--line-h);
  transition: background .3s, color .3s;
}

/* ---- nav ---- */
nav {
  position: sticky; top: 0; z-index: 100;
  display: flex; align-items: center; gap: 12px;
  padding: 10px 20px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  font-size: 14px;
  flex-wrap: wrap;
  transition: background .3s, border-color .3s;
}
nav a {
  color: var(--accent);
  text-decoration: none;
  white-space: nowrap;
}
nav a:hover { text-decoration: underline; }
nav .spacer { flex: 1; }
#theme-toggle {
  cursor: pointer;
  padding: 4px 12px;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 13px;
  color: var(--fg-muted);
  user-select: none;
  transition: border-color .3s, color .3s;
}
#theme-toggle:hover { border-color: var(--accent); color: var(--accent); }

/* ---- article ---- */
article {
  max-width: var(--max-w);
  margin: 40px auto 80px;
  padding: 0 24px;
}
article h1 {
  font-size: 1.8rem;
  font-weight: 600;
  color: var(--accent);
  margin-bottom: 1.5em;
  letter-spacing: 3px;
  text-align: center;
}
.paragraph {
  margin-bottom: var(--para-gap);
  text-indent: 2em;
  text-align: justify;
}

/* ---- entity spans ---- */
.entity {
  cursor: pointer;
  padding: 1px 3px;
  border-radius: 3px;
  border-bottom: 2px solid;
  transition: background .15s, color .15s;
}
/* type colours: text + bg tint + underline */
.entity-人物   { color: #9ccbee; background: rgba(126,184,218,0.12); border-bottom-color: rgba(126,184,218,0.4); }
.entity-人物:hover { background: rgba(126,184,218,0.3); }
.entity-圣众   { color: #dfc07a; background: rgba(201,169,110,0.12); border-bottom-color: rgba(201,169,110,0.4); }
.entity-圣众:hover { background: rgba(201,169,110,0.3); }
.entity-非人   { color: #d08080; background: rgba(176,90,90,0.12); border-bottom-color: rgba(176,90,90,0.4); }
.entity-非人:hover { background: rgba(176,90,90,0.3); }
.entity-寺院   { color: #85c4a5; background: rgba(107,163,134,0.12); border-bottom-color: rgba(107,163,134,0.4); }
.entity-寺院:hover { background: rgba(107,163,134,0.3); }
.entity-地名   { color: #a0b0c0; background: rgba(136,149,167,0.10); border-bottom-color: rgba(136,149,167,0.3); }
.entity-地名:hover { background: rgba(136,149,167,0.25); }
.entity-经典   { color: #b8a0c8; background: rgba(154,133,168,0.12); border-bottom-color: rgba(154,133,168,0.4); }
.entity-经典:hover { background: rgba(154,133,168,0.3); }
.entity-教法   { color: #d4a87a; background: rgba(196,149,106,0.12); border-bottom-color: rgba(196,149,106,0.4); }
.entity-教法:hover { background: rgba(196,149,106,0.3); }
.entity-教派   { color: #c0a890; background: rgba(160,144,128,0.12); border-bottom-color: rgba(160,144,128,0.3); }
.entity-教派:hover { background: rgba(160,144,128,0.25); }
.entity-仪轨   { color: #b0a890; background: rgba(154,144,128,0.12); border-bottom-color: rgba(154,144,128,0.3); }
.entity-仪轨:hover { background: rgba(154,144,128,0.25); }
.entity-法器圣物 { color: #a8a888; background: rgba(138,138,120,0.12); border-bottom-color: rgba(138,138,120,0.3); }
.entity-法器圣物:hover { background: rgba(138,138,120,0.25); }
.entity-集合   { color: #c0c098; background: rgba(180,180,138,0.10); border-bottom-color: rgba(180,180,138,0.3); }
.entity-集合:hover { background: rgba(180,180,138,0.25); }
.entity-佛学术语 { color: #b0a898; background: rgba(160,150,130,0.08); border-bottom-color: rgba(160,150,130,0.2); }
.entity-佛学术语:hover { background: rgba(160,150,130,0.2); }
/* Light theme entity overrides */
body.light .entity-人物   { color: #2a6a9a; background: rgba(126,184,218,0.15); }
body.light .entity-圣众   { color: #8a6510; background: rgba(201,169,110,0.15); }
body.light .entity-非人   { color: #903030; background: rgba(176,90,90,0.12); }
body.light .entity-寺院   { color: #306850; background: rgba(107,163,134,0.15); }
body.light .entity-地名   { color: #506070; background: rgba(136,149,167,0.12); }
body.light .entity-经典   { color: #6a4a7a; background: rgba(154,133,168,0.15); }
body.light .entity-教法   { color: #8a5a2a; background: rgba(196,149,106,0.15); }
body.light .entity-教派   { color: #6a5a48; background: rgba(160,144,128,0.12); }
body.light .entity-仪轨   { color: #6a5a48; background: rgba(154,144,128,0.12); }
body.light .entity-法器圣物 { color: #5a5a40; background: rgba(138,138,120,0.12); }
body.light .entity-集合   { color: #5a5a30; background: rgba(180,180,138,0.12); }
body.light .entity-佛学术语 { color: #6a6050; background: rgba(160,150,130,0.10); }

.entity-集合   { border-bottom-color: #90887a; }
.entity-集合:hover { background: rgba(144,136,122,0.15); }

/* ---- entity card ---- */
#entity-card {
  display: none;
  position: fixed;
  right: 20px;
  top: 60px;
  z-index: 200;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 20px;
  width: 380px;
  max-height: calc(100vh - 100px);
  overflow-y: auto;
  box-shadow: 0 8px 32px rgba(0,0,0,0.4);
  transition: background .3s, border-color .3s;
}
.card-close {
  position: absolute; top: 8px; right: 12px;
  cursor: pointer; color: var(--fg-muted); font-size: 1.2rem;
}
.card-close:hover { color: var(--fg); }
#entity-card h3 {
  font-size: 1.1rem;
  color: var(--accent);
  margin-bottom: 4px;
  padding-right: 20px;
}
#entity-card .card-type {
  font-size: 0.85rem;
  color: var(--fg-muted);
  margin-bottom: 12px;
}
#card-relations, #card-events {
  margin-bottom: 12px;
}
.card-section-title {
  font-size: 0.75rem;
  color: var(--fg-muted);
  letter-spacing: 1px;
  margin-bottom: 6px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--border);
}
.card-rel-item {
  font-size: 0.85rem;
  padding: 5px 0;
  border-bottom: 1px solid rgba(128,128,128,0.1);
  line-height: 1.6;
}
.card-rel-type {
  font-size: 0.7rem;
  padding: 1px 5px;
  border-radius: 3px;
  background: rgba(212,175,55,0.12);
  color: var(--accent);
  margin-right: 4px;
}
.card-rel-target {
  color: #7eb8da;
  cursor: pointer;
}
.card-rel-target:hover { text-decoration: underline; }
.card-rel-quote {
  font-size: 0.78rem;
  color: var(--fg-muted);
  margin-top: 3px;
  padding-left: 8px;
  border-left: 2px solid rgba(212,175,55,0.3);
  line-height: 1.5;
}
.card-rel-chapter {
  font-size: 0.65rem;
  color: rgba(128,128,128,0.6);
}
.card-evt-item {
  font-size: 0.85rem;
  padding: 5px 0;
  border-bottom: 1px solid rgba(128,128,128,0.1);
  cursor: pointer;
  line-height: 1.6;
}
.card-evt-item:hover { background: rgba(212,175,55,0.05); }
.card-evt-type {
  font-size: 0.7rem;
  padding: 1px 5px;
  border-radius: 3px;
  background: rgba(106,174,214,0.12);
  color: #6aaed6;
  margin-right: 4px;
}
.card-evt-quote {
  font-size: 0.78rem;
  color: var(--fg-muted);
  margin-top: 3px;
  display: none;
  padding-left: 8px;
  border-left: 2px solid rgba(106,174,214,0.3);
  line-height: 1.5;
}
.card-evt-item.expanded .card-evt-quote { display: block; }
#entity-card .card-btns {
  display: flex; gap: 8px; margin-top: 12px;
}
#entity-card .card-btns a {
  flex: 1;
  text-align: center;
  padding: 6px 0;
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--accent);
  text-decoration: none;
  font-size: 0.8rem;
  transition: background .15s;
}
#entity-card .card-btns a:hover {
  background: rgba(212,175,55,0.1);
  border-color: var(--accent);
}

/* ---- legend ---- */
.legend {
  max-width: var(--max-w);
  margin: 0 auto 24px;
  padding: 0 24px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px 18px;
  font-size: 0.8rem;
  color: var(--fg-muted);
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
}
.legend-swatch {
  width: 18px;
  height: 3px;
  border-radius: 1px;
}

/* ---- footer ---- */
footer {
  text-align: center;
  padding: 24px;
  font-size: 0.8rem;
  color: var(--fg-muted);
}

/* ---- stats bar ---- */
.stats {
  max-width: var(--max-w);
  margin: 0 auto 8px;
  padding: 0 24px;
  font-size: 0.75rem;
  color: var(--fg-muted);
  text-align: right;
}
"""


def js():
    return r"""
(function(){
  // -- theme toggle --
  const toggle = document.getElementById('theme-toggle');
  const root = document.documentElement;
  const saved = localStorage.getItem('reader-theme');
  if (saved === 'light') {
    root.setAttribute('data-theme', 'light');
    toggle.textContent = '深色';
  }
  toggle.addEventListener('click', function(){
    if (root.getAttribute('data-theme') === 'light') {
      root.removeAttribute('data-theme');
      toggle.textContent = '浅色';
      localStorage.setItem('reader-theme', 'dark');
    } else {
      root.setAttribute('data-theme', 'light');
      toggle.textContent = '深色';
      localStorage.setItem('reader-theme', 'light');
    }
  });

  // -- entity card --
  const card = document.getElementById('entity-card');
  const cardName = document.getElementById('card-name');
  const cardType = document.getElementById('card-type');
  const linkGraph = document.getElementById('link-graph');
  const linkLineage = document.getElementById('link-lineage');

  const cardRels = document.getElementById('card-relations');
  const cardEvts = document.getElementById('card-events');

  // Helper: get source/target name from link (D3 may have mutated to objects)
  function lsrc(l) { return (typeof l.source === 'object' ? l.source.id : l.source) || ''; }
  function ltgt(l) { return (typeof l.target === 'object' ? l.target.id : l.target) || ''; }

  function showEntityCard(eid, etype) {
    cardName.textContent = eid;
    cardType.textContent = etype;
    linkGraph.href = '../prototype/index.html?highlight=' + encodeURIComponent(eid);
    linkLineage.href = '../prototype/lineage.html?highlight=' + encodeURIComponent(eid);

    // -- Relations --
    var relHTML = '';
    if (typeof links !== 'undefined') {
      var rels = links.filter(function(l) {
        return lsrc(l) === eid || ltgt(l) === eid;
      });
      if (rels.length > 0) {
        relHTML = '<div class="card-section-title">关系 (' + rels.length + ')</div>';
        rels.slice(0, 20).forEach(function(l) {
          var src = lsrc(l), tgt = ltgt(l);
          var other = (src === eid) ? tgt : src;
          var dir = (src === eid) ? '→' : '←';
          var q = l.quote || '';
          var qShort = q.length > 80 ? q.substring(0, 80) + '…' : q;
          relHTML += '<div class="card-rel-item">'
            + '<span class="card-rel-type">' + (l.type || '') + '</span>'
            + dir + ' <span class="card-rel-target" onclick="highlightInText(\'' + other.replace(/'/g,"\\'") + '\')">' + other + '</span>'
            + (l.specialty ? ' <span style="font-size:0.7rem;color:var(--fg-muted)">[' + l.specialty + ']</span>' : '')
            + (qShort ? '<div class="card-rel-quote">「' + qShort + '」<span class="card-rel-chapter">' + (l.chapter || '') + '</span></div>' : '')
            + '</div>';
        });
        if (rels.length > 20) relHTML += '<div style="color:var(--fg-muted);font-size:0.8rem">...及更多 ' + (rels.length-20) + ' 条</div>';
      }
    }
    // If no relations AND no events, show hint
    var hasData = false;
    cardRels.innerHTML = relHTML;
    if (relHTML) hasData = true;

    // -- Events --
    var evtHTML = '';
    if (typeof allEvents !== 'undefined' && typeof entityEventIndex !== 'undefined' && entityEventIndex[eid]) {
      var indices = entityEventIndex[eid];
      evtHTML = '<div class="card-section-title">相关事件 (' + indices.length + ')</div>';
      indices.slice(0, 15).forEach(function(idx) {
        var evt = allEvents[idx];
        if (!evt) return;
        var q = evt.quote || '';
        evtHTML += '<div class="card-evt-item" onclick="this.classList.toggle(\'expanded\')">'
          + '<span class="card-evt-type">' + (evt.type || '') + '</span>'
          + (evt.title || '')
          + '<div class="card-evt-quote">「' + q + '」<div class="card-rel-chapter">' + (evt.chapter || '') + '</div></div>'
          + '</div>';
      });
      if (indices.length > 15) evtHTML += '<div style="color:var(--fg-muted);font-size:0.8rem">...及更多 ' + (indices.length-15) + ' 条</div>';
    }
    cardEvts.innerHTML = evtHTML;
    if (evtHTML) hasData = true;

    // No data hint
    if (!hasData) {
      cardRels.innerHTML = '<div style="color:var(--fg-muted);font-size:0.8rem;padding:8px 0;">此实体来自术语词表自动匹配，尚未经 Agent 提取关系和事件。<br>完整管线重跑后将补充。</div>';
    }

    card.style.display = 'block';
  }

  // Highlight entity name in text (scroll to first occurrence)
  window.highlightInText = function(name) {
    var spans = document.querySelectorAll('.entity[data-entity="' + name + '"]');
    if (spans.length > 0) {
      spans[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
      spans[0].style.outline = '2px solid var(--accent)';
      setTimeout(function() { spans[0].style.outline = ''; }, 2000);
      showEntityCard(name, spans[0].getAttribute('title') || '');
    }
  };

  document.addEventListener('click', function(e) {
    var evtItem = e.target.closest('.card-evt-item');
    if (evtItem) return; // let toggle work

    const span = e.target.closest('.entity');
    if (span) {
      const eid = span.getAttribute('data-entity');
      const etype = span.getAttribute('title');
      showEntityCard(eid, etype);
      e.stopPropagation();
      return;
    }
    // click outside card -> close
    if (!card.contains(e.target)) {
      card.style.display = 'none';
    }
  });
})();
"""


def build_nav(ch_num: str):
    """Build navigation HTML for a chapter page."""
    idx = int(ch_num)
    parts = ['<nav>']
    parts.append('<a href="index.html">目录</a>')
    parts.append('<a href="../prototype/index.html">星图</a>')
    parts.append('<a href="../prototype/lineage.html">传承谱系</a>')
    parts.append('<span class="spacer"></span>')
    if idx > 1:
        parts.append(f'<a href="ch{idx-1:02d}.html">&larr; 上一品</a>')
    else:
        parts.append('<span style="color:var(--fg-muted)">&larr; 上一品</span>')
    if idx < 8:
        parts.append(f'<a href="ch{idx+1:02d}.html">下一品 &rarr;</a>')
    else:
        parts.append('<span style="color:var(--fg-muted)">下一品 &rarr;</span>')
    parts.append('<span id="theme-toggle">浅色</span>')
    parts.append('</nav>')
    return "\n  ".join(parts)


LEGEND_TYPES = [
    ("人物", "#7eb8da"),
    ("圣众", "#c9a96e"),
    ("非人", "#b05a5a"),
    ("寺院", "#6ba386"),
    ("地名", "#8895a7"),
    ("经典", "#9a85a8"),
    ("教法", "#c4956a"),
    ("教派", "#a09080"),
    ("仪轨", "#9a9080"),
    ("法器圣物", "#8a8a78"),
    ("集合", "#90887a"),
]


def build_legend():
    items = []
    for label, color in LEGEND_TYPES:
        items.append(
            f'<span class="legend-item">'
            f'<span class="legend-swatch" style="background:{color}"></span>'
            f'{label}</span>'
        )
    return '<div class="legend">' + "".join(items) + '</div>'


def build_chapter_html(ch_num: str, title: str, paragraphs: list[str],
                       name_index: dict, sorted_names: list[str]) -> str:
    idx = int(ch_num)
    # The title (e.g. "第一品 佛教总况") may be merged into the first paragraph.
    # Strip ONLY the exact title prefix, keep everything else.
    body_paragraphs = list(paragraphs)
    if body_paragraphs:
        first = body_paragraphs[0]
        # Known chapter title prefixes (hardcoded — only 8 chapters)
        known_titles = [
            '第一品 佛教总况', '第一品 佛教总况', '第二品 金刚密乘',
            '第三品 藏传佛法', '第四品 内密三续', '第五品 远传经幻心',
            '第六品 近传伏藏史', '第七品 遣除邪见', '第八品 略说佛教年表',
            # Also without space
            '第一品佛教总况', '第二品金刚密乘', '第三品藏传佛法',
            '第四品内密三续', '第五品远传经幻心', '第六品近传伏藏史',
            '第七品遣除邪见', '第八品略说佛教年表',
        ]
        for t in sorted(known_titles, key=len, reverse=True):
            if first.startswith(t):
                rest = first[len(t):].strip()
                if rest:
                    body_paragraphs[0] = rest
                else:
                    body_paragraphs = body_paragraphs[1:]
                break

    # Count entities for stats
    entity_count = 0
    annotated_parts = []
    for p in body_paragraphs:
        annotated = annotate_paragraph(p, name_index, sorted_names)
        annotated_parts.append(annotated)
        entity_count += annotated.count('class="entity ')

    stats = f'<div class="stats">本品标注 {entity_count} 处实体</div>'

    sections = []
    for ap in annotated_parts:
        sections.append(f'    <section class="paragraph"><p>{ap}</p></section>')
    body_html = "\n".join(sections)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>第{idx}品 {html_mod.escape(title)} — 藏密佛教史</title>
<style>{css()}</style>
</head>
<body>
  {build_nav(ch_num)}

  {build_legend()}
  {stats}

  <article>
    <h1>第{idx}品 {html_mod.escape(title)}</h1>
{body_html}
  </article>

  <div id="entity-card">
    <span class="card-close" onclick="document.getElementById('entity-card').style.display='none'">&times;</span>
    <h3 id="card-name"></h3>
    <div class="card-type" id="card-type"></div>
    <div id="card-relations"></div>
    <div id="card-events"></div>
    <div class="card-btns">
      <a id="link-graph" href="#">在星图中查看</a>
      <a id="link-lineage" href="#">在传承谱系中查看</a>
    </div>
  </div>

  <footer>藏密佛教史 知识图谱 &middot; 阅读视图</footer>

  <script src="../prototype/graph_data.js"></script>
  <script src="../prototype/events_data.js"></script>
  <script>{js()}</script>
</body>
</html>"""


def build_index_html() -> str:
    items = []
    for ch_num, _, title in CHAPTERS:
        idx = int(ch_num)
        items.append(
            f'      <a class="toc-item" href="ch{ch_num}.html">'
            f'<span class="ch-num">第{idx}品</span>'
            f'<span class="ch-title">{html_mod.escape(title)}</span></a>'
        )
    toc = "\n".join(items)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>藏密佛教史 — 阅读视图</title>
<style>{css()}

/* ---- index-specific ---- */
.index-header {{
  text-align: center;
  padding: 60px 24px 20px;
}}
.index-header h1 {{
  font-size: 2rem;
  color: var(--accent);
  letter-spacing: 6px;
  margin-bottom: 8px;
}}
.index-header .subtitle {{
  font-size: 0.9rem;
  color: var(--fg-muted);
  letter-spacing: 2px;
}}
.toc {{
  max-width: var(--max-w);
  margin: 40px auto 80px;
  padding: 0 24px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}}
.toc-item {{
  display: flex;
  align-items: baseline;
  gap: 16px;
  padding: 16px 20px;
  text-decoration: none;
  border-radius: 6px;
  transition: background .15s;
}}
.toc-item:hover {{
  background: rgba(212,175,55,0.08);
}}
.ch-num {{
  font-size: 0.9rem;
  color: var(--fg-muted);
  min-width: 60px;
}}
.ch-title {{
  font-size: 1.15rem;
  color: var(--accent);
  letter-spacing: 1px;
}}
.nav-links {{
  max-width: var(--max-w);
  margin: 0 auto 60px;
  padding: 0 24px;
  display: flex;
  gap: 20px;
  justify-content: center;
}}
.nav-links a {{
  color: var(--fg-muted);
  text-decoration: none;
  font-size: 0.9rem;
  padding: 8px 16px;
  border: 1px solid var(--border);
  border-radius: 4px;
  transition: border-color .15s, color .15s;
}}
.nav-links a:hover {{
  border-color: var(--accent);
  color: var(--accent);
}}
</style>
</head>
<body>
  <nav>
    <a href="../prototype/index.html">星图</a>
    <a href="../prototype/lineage.html">传承谱系</a>
    <span class="spacer"></span>
    <span id="theme-toggle">浅色</span>
  </nav>

  <div class="index-header">
    <h1>藏密佛教史</h1>
    <div class="subtitle">敦珠法王 著 &middot; 知识图谱阅读视图</div>
  </div>

  <div class="nav-links">
    <a href="../prototype/index.html">星图可视化</a>
    <a href="../prototype/lineage.html">传承谱系</a>
  </div>

  <div class="toc">
{toc}
  </div>

  <footer>藏密佛教史 知识图谱 &middot; 阅读视图</footer>

  <div id="entity-card" style="display:none"></div>
  <script>
  (function(){{
    const toggle = document.getElementById('theme-toggle');
    const root = document.documentElement;
    const saved = localStorage.getItem('reader-theme');
    if (saved === 'light') {{
      root.setAttribute('data-theme', 'light');
      toggle.textContent = '深色';
    }}
    toggle.addEventListener('click', function(){{
      if (root.getAttribute('data-theme') === 'light') {{
        root.removeAttribute('data-theme');
        toggle.textContent = '浅色';
        localStorage.setItem('reader-theme', 'dark');
      }} else {{
        root.setAttribute('data-theme', 'light');
        toggle.textContent = '深色';
        localStorage.setItem('reader-theme', 'light');
      }}
    }});
  }})();
  </script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# 5. Main
# ---------------------------------------------------------------------------
def main():
    print("Loading entities from graph_data.js ...")
    entities = load_entities()
    print(f"  {len(entities)} entities loaded from graph_data.js")

    # Load Buddhist vocabulary gazetteer (curated, with types)
    vocab_path = str(ROOT / "doc" / "buddhist-vocab.yaml")
    vocab_entities = load_buddhist_vocab(vocab_path)
    existing_names = {e["id"] for e in entities}
    for a in entities:
        for al in a.get("aliases", []):
            existing_names.add(al)
    new_vocab = [v for v in vocab_entities if v["id"] not in existing_names]
    entities.extend(new_vocab)
    for v in new_vocab:
        existing_names.add(v["id"])
    print(f"  +{len(new_vocab)} from buddhist-vocab.yaml → {len(entities)} entities")

    # NOTE: merged_gazetteer_st.txt (82k terms) is NOT loaded here.
    # It's used by gazetteer_prescan.py to generate candidate lists for Agents.
    # Only Agent-confirmed entities should appear in the reader view.
    # Direct gazetteer → reader annotation is anti-NER (no classification, no relations).

    # Auto-detect 《》 book titles from source texts
    chapter_paths = [str(CHAPTER_DIR / fn) for _, fn, _ in CHAPTERS]
    auto_texts = auto_detect_texts_from_source(chapter_paths, entities)
    entities.extend(auto_texts)
    print(f"  +{len(auto_texts)} auto-detected 《》 texts → {len(entities)} total entities")

    name_index, sorted_names = build_name_index(entities)
    print(f"  {len(sorted_names)} surface forms indexed (longest first)")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for ch_num, filename, title in CHAPTERS:
        src = CHAPTER_DIR / filename
        print(f"\nProcessing ch{ch_num}: {title}")
        raw = src.read_text(encoding="utf-8")
        paragraphs = preprocess_text(raw)
        print(f"  {len(paragraphs)} paragraphs")

        html_content = build_chapter_html(ch_num, title, paragraphs,
                                          name_index, sorted_names)
        out_path = OUT_DIR / f"ch{ch_num}.html"
        out_path.write_text(html_content, encoding="utf-8")
        print(f"  -> {out_path}")

    # index page
    index_html = build_index_html()
    index_path = OUT_DIR / "index.html"
    index_path.write_text(index_html, encoding="utf-8")
    print(f"\n-> {index_path}")

    print("\nDone!  Generated files:")
    for f in sorted(OUT_DIR.glob("*.html")):
        size_kb = f.stat().st_size / 1024
        print(f"  {f.name:16s}  {size_kb:7.1f} KB")


if __name__ == "__main__":
    main()
