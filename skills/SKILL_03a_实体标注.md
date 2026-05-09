---
name: skill-03a
description: 藏传佛教典籍实体抽取方法。当需要从源典文本中提取人物、圣众、非人、寺院、地名、经典、教法、教派、仪轨、法器、集合等实体时使用。输入为 chapter_md 文本，输出为 yaml 格式的实体注册表。
---

# SKILL 03a: 实体标注 — 从源文本到结构化实体注册表

> 从敦珠《藏密佛教史》第三品 PoC 中提炼，适用于藏传佛教汉译典籍的命名实体识别与抽取。

---

## 一、概述

**输入**：
- `source/<book>/chapter_md/<NN>_<title>.md` 分章文本
- **（v0.3 新增）候选实体列表**：由 gazetteer 预扫描产出的"已在文本中匹配到的术语清单"
  
**输出**：`kg/entities/<chapter_id>.yaml` 实体注册表  
**何时使用**：每一章/节进入 KG 管线时的第一步。

**核心目标**：
1. **确认和分类** gazetteer 提供的候选实体（它们已经被找到了，Agent 只需判断类型）
2. **发现新实体** gazetteer 没有的（人名、地名、经典等）
3. 去重归一，输出结构化 yaml

**v0.3 工作流——双轨并行**：

```
轨道1（gazetteer）: 佛学辞典/术语表预扫描 → 候选A（通用术语，高确定性）
轨道2（Agent NER）: 上下文判断 → 候选B（藏传专名，辞典里没有的）
→ 合并 A+B = 完整实体列表
```

**Agent 有两个明确任务**：
1. **确认 gazetteer 候选**的类型（这些词已被匹配到，不需要你"发现"它们）
2. **发现 gazetteer 没有的新实体**——尤其是藏传佛教专有名词：
   - 藏地人名（酿·西绕炯内、奘·达玛布德、香切札巴...）
   - 藏地地名（札马翁布园、嘉绒岩怙主静处...）
   - 藏地寺院（邬金敏珠朗佛学院...）
   - 密法法本（《空行心滴》《上师心滴如意宝》...）
   - 这些词不在任何辞典里，只能靠上下文判断
   
两类实体合并输出到同一份 yaml。

## 二、标注规则速查

完整规则见 `doc/entity-taxonomy.md` v0.4。这里是 Agent 执行时需要记住的**最关键子集**：

### 2.1 类目（11 个）

人物 / 圣众 / 非人 / 寺院 / 地名 / 经典 / 教法 / 教派 / 仪轨 / 法器圣物 / 集合

### 2.2 核心原则（执行时最常用的）

| # | 原则 | 执行要点 |
|---|---|---|
| 3 | 化身关系不自动重叠类目 | "X 是观音化身" → manifestationOf 关系，不改 X 的 type |
| 5 | 别名严格定义 | 异译/法名/尊号 = alias；"印度瑜伽师""亲教师" = NOT alias |
| 12 | 不从外部知识填字段 | 文本没说就留空，不猜 |
| 15 | 文本忠实度 > 外部知识 | 不追求 100% 准确，承认不完整 |
| 16 | 通称非人不建 entity | "凶神恶煞""鬼神" 无名 → 不建 entity |
| 17 | 修证状态是属性 | "六通" → entity.attainments 字段 |
| 19 | 任何 entity 可作事件主体 | 佛像开口说话 → 佛像是 subject |
| 22 | **《》包裹必提取** | 凡文本中出现 `《XXX》` 的，XXX 必须作为经典类实体提取（除非明确是仪轨/咒语）。这是最容易漏掉的实体类型——Agent 必须扫描全文所有《》并逐一确认是否已在输出中 |
| 23 | **忽略脚注序号** | 源文本含 PDF 脚注标记（如"俱胝 10 四洲 11"中的 10、11），这些**不是实体**。识别实体时应先mentally strip掉这些孤立数字。不要把"菩萨 13"中的 13 当作实体的一部分 |

### 2.3 判定规则

**R1（多类目共存）**：仅当文本同时以凡常 mode + 圣众 mode 描述该 entity 时添加 additional_types。不用外部知识。

**R2（form entity 升级）**：若文本引入新名描述某 entity 的身相/化身形态，且该形态有独立修法/造像 → 创建独立 entity（type=圣众.大乘.本尊），form_of 指向主 entity。

**R3（顶级 vehicle 留空）**：若教法 entity 本身是九乘之一（或其 alias 是），vehicle 字段留空。

## 三、Agent Prompt

以下是标注 Agent 的完整 prompt。在 Claude Code session 中，对每一章/节执行此 prompt。

```
你是一个藏传佛教典籍知识抽取 Agent。

## 任务
阅读以下源文本，提取所有具名实体，输出 yaml 格式的实体注册表。

## 分类体系（11 类）
1. 人物 (Person) — 子类: 帝王/王妃/大臣/法师/空行母/其他
   - 法师的 specialty 属性 (多选): 班智达/堪布/上师/比丘/译师/伏藏师/持藏/金刚持/瑜伽士/阿阇黎/大成就者
2. 圣众 (Holy Beings) — 子类: 声闻圣众(四果)/缘觉圣众/大乘圣众(佛/菩萨/本尊/空行/护法)
3. 非人 (Non-human) — 子类: 天部/阿修罗/旁生/饿鬼/地狱/护法(世间)/通称
4. 寺院 (Monastery) — 子类: 寺庙/王宫/道场/修行处
5. 地名 (Place) — 子类: 国/区域/圣地/神话地名/自然地理
6. 经典 (Text) — 子类: 经/律/论/密续(远传/岩藏(地/意/虚空))/净相法/史籍/教言集/经典集合
7. 教法 (Teaching) — 子类: 教法体系/教言法门/戒律体系/修法元素
   - 正交属性: vehicle(九乘)/turn(三转)/section(显密前后译)/sect_affiliation
8. 教派 (Sect) — 子类: 藏传宗派/印度部派/子派
9. 仪轨 (Ritual) — 子类: 灌顶/修法/供养/占卜/戒律/法事/咒语
10. 法器/圣物 (Object) — 子类: 佛像/法器/圣物
11. 集合 (Collective) — 子类: 上师集合/弟子集合/王族集合/人物集合/其他

## 关键规则
- 别名只放 true alternative names（异译/法名/尊号），不放 generic role
- "X 是 Y 菩萨的化身" → manifestationOf 关系，X 的 type 不变
- 文本没提到的字段留空（不猜外部知识）
- "鬼神""妖魔鬼怪" 等无名非人不建 entity
- 修证状态（六通等）作为 attainments 属性
- 多类目共存（R1）：仅当文本同时用凡常 + 圣众两种 mode 描述时
- 祖师身相（R2）：有独立修法的 form → 独立 entity
- 九乘本身的教法（R3）：vehicle 留空

## ⚠️ 最易漏提取的实体类型
1. **《》包裹的经典名**：必须扫描全文所有《XXX》，每个都提取为经典类实体。原文中可能连续出现多部经典（如"《A》《B》《C》中说"），每部都要单独提取
2. **被动提及的地名**：如"在XX地方""前往XX"中的地名
3. **并列出现的人名**：如"A、B、C三位"中每个人都要提取

## 输出格式
每个 entity 一条 yaml record：
```yaml
E_NNN:
  name: 主名（最简洁/最常用）
  aliases: [别名1, 别名2]            # 严格定义
  type: 类目.子类
  sub_type: 更细子类（可选）
  specialty: [tag1, tag2]             # 仅 人物.法师
  origin: 地名（可选）
  sect_affiliation: [派别]            # 文本支持时
  manifestation_of: [entity_id]       # 化身来源
  manifested_forms: [entity_id]       # 化身目标
  form_of: entity_id                  # R2 形态实体
  additional_types: [类目.子类]        # R1
  additional_types_source: text|manual
  attainments: [修证状态]              # 六通等
  cardinality: N                      # 集合/伏藏等
  members: [entity_id, ...]           # 集合
  concealed_by: entity_id             # 伏藏
  subdued_by: entity_id               # 非人.护法
  related_oq: OQ-NNN                  # 未决问题引用
  note: 备注
  appearances: [行号]                  # 首次/重要出现位置
```\n

## 源文本
{TEXT}
```

## 四、执行流程

```
1. 读取整章/整节文本
2. 逐段扫描，识别所有具名/可命名实体
3. 对每个新 entity：
   a. 检查是否已在注册表中（name 或 alias 匹配）→ 是则更新，否则新建
      **⚠️ 跨 chunk 去重（v0.2 修正）**：如果本 chunk 之前有其他 chunk
      已经提取过实体（如 ch04-part1 先于 ch04-part2），必须检查已有 chunk
      的注册表。匹配规则：
        - 完全匹配 name → 同一实体
        - 名字 A 是名字 B 的子串且长度 ≥ 3 → 可能同一实体（如"贡巴绕色"⊂"贡巴绕色大师"）→ 使用较短的 canonical name
        - 名字出现在已有实体的 aliases 列表中 → 同一实体
      如果判定为同一实体，使用已有的 canonical name，不创建新 entry
   b. 判定 type（11 类 → 子类）
   c. 若 人物.法师 → 填 specialty（多选）
   d. 若文本提到化身关系 → 填 manifestation_of（不改 type）
   e. R1 检查：该 entity 在文本中是否有凡常 + 圣众双模式描述？
      是 → additional_types
   f. R2 检查：该 entity 是否是某个更大 entity 的独立身相/形态？
      是 → 独立 entity + form_of
   g. R3 检查：该教法是否是九乘之一？
      是 → vehicle 留空
4. 输出 yaml 到 kg/entities/<chapter_id>.yaml
5. 运行质量检查（§五）
```

## 四 bis、实体名作为跨文件标识符（v0.2 修正）

**entity 的 `name` 字段是全局标识符**——下游的事件（SKILL_04a）和关系（SKILL_05a）都用 name（不是 entity ID）来引用实体。

原因：entity ID（如 E_001）在不同提取 chunk 中会重复（ch03 和 ch04 各自有 E_014 但指代不同人物），无法跨文件解析。name 是人类可读的、跨文件稳定的标识符。

**要求**：
- `name` 必须是该实体最通用、最简洁的称呼
- 同一个实体在不同 chunk 中的 `name` 必须完全一致（"莲花生大士"，不是一处"莲师"另一处"莲花生大士"）
- 变体放在 `aliases`，不要用变体作 name
- **不要在 name 中添加括号注释**（如 `"堪布萨哲仁钦 (P2.E_020)"` ← 禁止）

## 五、质量检查

提取完成后，Agent 自检以下项目：

| # | 检查 | 方法 |
|---|---|---|
| 1 | **无 type 的 entity** | grep 所有 entity record，检查 type 字段是否非空 |
| 2 | **alias 不当** | 检查 aliases 中是否含 generic role（"亲教师""译师"等）→ 若 alias 字串也是 specialty 取值集合中的词，可能是误入 |
| 3 | **外部知识泄漏** | 检查 sect_affiliation/origin/manifestation_of 等字段，是否有值在源文本中完全未出现 |
| 4 | **通称非人泄漏** | 检查是否有 name 为"鬼神""凶神恶煞""妖魔鬼怪"等通称的 entity → 应删除 |
| 5 | **R1 误触发** | 检查 additional_types 非空的 entity：其 additional_types_source 是否为 text，且文本中确有双模式描述 |
| 6 | **去重** | 检查是否有两个 entity 的 name 或 alias 有交集 → 合并 |
| 7 | **cardinality 一致** | 集合 entity 的 members 列表长度是否 = cardinality |

## 六、输出位置与命名

```
kg/
├── entities/
│   ├── ch03.yaml                # 第三品全章
│   ├── ch03-01-涅赤赞普.yaml    # 可选：按子节拆分
│   ├── ch03-02-拉托托日涅赞.yaml
│   └── ...
└── poc/                         # PoC 产出（保留作参考）
    └── ch3-shijunsanzun.yaml
```

全章 vs 子节：首次提取按全章出一个文件；如果 entity 数量 > 200，拆成子节文件。

## 七、已知局限（诚实声明）

1. **不追求 100% 准确**：藏传佛教术语浩瀚，Claude 不可能全部正确分类
2. **外部知识不进管线**：有些 entity 在传统中有重要地位（如贝若札那的 sadhana），但文本未提及就不会体现
3. **通称非人丢失**：大量"鬼神""罗刹"等通称不入 entity，它们的参与通过事件（SKILL_04）间接体现
4. **消歧不在本阶段**：同名异人、指代消解在 SKILL_03b 处理
5. **关系不在本阶段**：师承、建寺、译经等关系在 SKILL_05 处理；本阶段只记录 manifestationOf 和 form_of（因为它们影响 entity type）

## 八、版本历史

| 版本 | 日期 | 改动 |
|---|---|---|
| v0.1 | 2026-04-11 | 首版，基于 entity-taxonomy v0.4 + PoC 经验编写 |
