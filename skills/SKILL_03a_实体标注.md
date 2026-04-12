---
name: skill-03a
description: 藏传佛教典籍实体抽取方法。当需要从源典文本中提取人物、圣众、非人、寺院、地名、经典、教法、教派、仪轨、法器、集合等实体时使用。输入为 chapter_md 文本，输出为 yaml 格式的实体注册表。
---

# SKILL 03a: 实体标注 — 从源文本到结构化实体注册表

> 从敦珠《藏密佛教史》第三品 PoC 中提炼，适用于藏传佛教汉译典籍的命名实体识别与抽取。

---

## 一、概述

**输入**：`source/<book>/chapter_md/<NN>_<title>.md` 分章文本  
**输出**：`kg/entities/<chapter_id>.yaml` 实体注册表  
**何时使用**：每一章/节进入 KG 管线时的第一步。在结构分析（SKILL_02）之后、事件抽取（SKILL_04）和关系抽取（SKILL_05）之前。

**核心目标**：从文本中识别所有具名实体，去重归一，按 entity-taxonomy v0.4 分类，输出结构化 yaml。

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
   a. 检查是否已在注册表中（alias 匹配）→ 是则更新，否则新建
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
