---
name: skill-05a
description: 藏传佛教典籍关系构建方法。从事件和实体中抽取持久关系（relations）。输入为 kg/entities/*.yaml + kg/events/*.yaml，输出为 kg/relations/<chapter_id>.yaml 关系记录。
---

# SKILL 05a: 关系构建 — 从事件与实体到结构化关系

> 从敦珠《藏密佛教史》第三品 PoC 中提炼，适用于藏传佛教汉译典籍的关系抽取。

---

## 一、概述

**输入**：`kg/entities/<chapter_id>.yaml` + `kg/events/<chapter_id>.yaml`
**输出**：`kg/relations/<chapter_id>.yaml` 关系记录
**何时使用**：事件识别（SKILL_04a）完成之后。

**核心目标**：从事件记录和实体属性中提取持久性关系，输出结构化 yaml。

**关系 vs 事件**：
- **事件**：一次性发生的、有时间锚点的行为（"莲师为赤松德赞灌顶"）
- **关系**：持久的、状态性的连接（"赤松德赞 teacherOf.灌顶 莲花生大士"）
- 一个事件可以产生一个或多个关系（灌顶事件 → teacherOf 关系）
- 一个关系也可以不来自事件（"X 是 Y 的化身" 是直接陈述的关系）

## 二、关系类型（从第三品归纳）

| 类别 | 关系 | 方向 | 说明 |
|---|---|---|---|
| 化身 | manifestationOf | 人物 → 圣众 | "X 是 Y 的化身" |
| 化身 | form_of | 圣众 → 圣众 | R2 形态实体（多吉卓罗 form_of 莲师） |
| 师承 | teacherOf | 师 → 徒 | + specialty 标签（见下） |
| 建寺 | builtBy | 寺院 → 人物 | 建造者 |
| 建寺 | foundedBy | 道场 → 人物 | 创立者（未必亲建） |
| 政治 | rulerOf | 人物 → 地名 | 统治 |
| 政治 | fatherOf | 人物 → 人物 | 父子 |
| 政治 | consort | 人物 ↔ 人物 | 配偶（对称） |
| 政治 | ministerOf | 人物 → 人物 | 大臣/法臣 |
| 政治 | siblingOf | 人物 ↔ 人物 | 兄弟姐妹（对称） |
| 译经 | translatedBy | 经典 → 人物 | 翻译者 |
| 译经 | revisedBy | 经典 → 人物 | 校勘/译校者 |
| 降伏 | subduedBy | 非人 → 人物 | 被降伏（仅具名非人） |
| 降伏 | protects | 非人 → 寺院/地名 | 护法守护对象 |
| 伏藏 | concealedBy | 经典 → 人物 | 埋藏者 |
| 伏藏 | revealedBy | 经典 → 人物 | 开取者 |
| 伏藏 | revealedFrom | 经典 → 地名 | 开取地点 |
| 归属 | memberOf | 人物 → 集合 | 成员归属 |
| 归属 | belongsToSect | 人物/寺院 → 教派 | 宗派归属 |
| 归属 | lineageOf | 教法/仪轨 → 教派 | 法脉归属 |
| 引文 | cites | 断言 → 经典 | 引用出处 |
| 引文 | refutes | 断言 → 断言 | 反驳 |
| 引文 | reconciles | 断言 → [断言] | 调和多说 |
| 引文 | alternativeOf | 断言 ↔ 断言 | 异说（对称） |

类型集合不封闭。后续章节如出现新类型，扩展此表。

**teacherOf 的 specialty 标签**：灌顶 / 口传 / 戒律 / 教授 / 大圆满 / 密法。师承是单一关系 + specialty 列表，不拆为 initiatedBy / ordainedBy / taughtBy 等多种关系。同一师徒可同时涉及多种 specialty。

第三品例：静命 teacherOf[戒律] 巴赤则；莲师 teacherOf[灌顶,密法] 赤松德赞；西日桑哈 teacherOf[大圆满] 贝若札那

## 三、关键规则

| # | 规则 | 说明 |
|---|---|---|
| 1 | 师承用 specialty 标签 | teacherOf 是单一关系，specialty 区分灌顶/口传/戒律/教授等，不拆多种关系 |
| 2 | 关系从事件推导 | 大部分关系来自事件：出家受戒事件 → teacherOf[戒律]；建寺事件 → builtBy |
| 3 | 直接陈述关系 | 部分关系不经事件直接从文本陈述获得：化身关系、父子关系 |
| 4 | 关系必须有文本支持 | 不从外部知识推导关系（原则 #12） |
| 5 | 对称关系存一条 | consort / siblingOf / alternativeOf 只存一条 record，标注 symmetric: true |
| 6 | 叙述层继承 | 从事件推导的关系继承事件的 layers；直接陈述的关系独立标注 layers |
| 7 | 化身关系在 SKILL_03a 已记录 | manifestationOf / form_of 在实体注册表中已有字段，本阶段生成对应的 relation record 作为冗余索引 |

## 四、Agent Prompt

以下是关系构建 Agent 的完整 prompt。

```
你是一个藏传佛教典籍关系构建 Agent。

## 任务
从实体注册表和事件记录中提取持久性关系，输出 yaml。

## 实体注册表
{ENTITIES_YAML}

## 事件记录
{EVENTS_YAML}

## 关系类型（可扩展）
化身: manifestationOf / form_of
师承: teacherOf + specialty (灌顶/口传/戒律/教授/大圆满/密法)
建寺: builtBy / foundedBy
政治: rulerOf / fatherOf / consort / ministerOf / siblingOf
译经: translatedBy / revisedBy
降伏: subduedBy / protects
伏藏: concealedBy / revealedBy / revealedFrom
归属: memberOf / belongsToSect / lineageOf
引文: cites / refutes / reconciles / alternativeOf

## 关键规则
- 师承 = teacherOf + specialty 标签列表，不拆多种关系类型
- 区分事件（一次性发生）和关系（持久状态）：只提取关系
- 关系必须有源文本支持，不猜外部知识
- 从事件推导关系时，继承事件的 layers 和 confidence
- 对称关系只存一条 record
- manifestationOf / form_of 在实体注册表中已有，这里生成冗余的关系 record
- **⚠️ 名字规范化（v0.2 修正）**：source/target 必须使用实体注册表中的 canonical name（`name` 字段值）。如果源文本使用了别名或变体（如"贡巴绕色大师""龙钦巴"），必须查找实体注册表找到其 canonical name（如"贡巴绕色""无垢光尊者"），使用后者。**不要直接抄文本里的原样名字——要先 normalize**
- **⚠️ 引文关系要丰富（v0.3 新增）**：cites 关系不仅记录"谁引用了什么经典"，还要记录：
  - `quoted_text`：引文的具体内容
  - `argument`：作者引用此经的论证目的（如"论证释迦牟尼佛的化身遍满一切世界"）
  - `about_entity`：引文主要关于哪个实体（如释迦牟尼佛）
  格式：
  ```yaml
  - rel_id: R_NNN
    type: cites
    source: 引文论证的上下文主题/作者观点
    target: 《经典名》
    quoted_text: "引文具体内容"
    argument: "论证目的"
    about_entity: 实体名
    layers: [典据]
    source_quote: "完整段落"
  ```

## 输出格式
每个关系一条 yaml record：
```yaml
REL_NNN:
  type: teacherOf
  source: 静命                # ← 实体的 name 字段值（人类可读名），不是 entity ID
  target: 巴绕那              # ← 同上，必须是 name 不是 E_NNN
  specialty: [灌顶, 密法]    # 仅 teacherOf 使用
  symmetric: false            # 对称关系标 true
  derived_from: EVT_NNN       # 来源事件（可选，直接陈述则 null）
  layers: [史传]
  author_stance: 中立
  confidence: 0.85
  source_quote: "原文引用片段"
  note: null
```

**⚠️ 关键规则（v0.2 修正）**：
- `source` 和 `target` 字段**必须使用实体的 name（人类可读名），不使用 entity ID**
- 原因：entity ID 在不同 chunk 间不唯一（E_014 在 ch03 和 ch04 指代不同实体），名字是跨文件稳定的标识符
- **不要在 source/target 中添加括号注释**——任何补充信息放到 `note` 字段
- 错误示例：`source: "堪布萨哲仁钦 (P2.E_020 龙钦巴 twelve岁出家)"` ← 禁止
- 正确示例：`source: 堪布萨哲仁钦` + `note: "P2.E_020, 龙钦巴十二岁出家之亲教师"`\n

## 执行步骤
1. 遍历事件记录，对每个事件判断是否产生持久关系
2. 扫描实体注册表中的 manifestationOf / form_of 字段，生成对应关系 record
3. 回扫源文本，检查是否有直接陈述的关系未被事件覆盖（如父子、配偶、宗派归属）
4. 去重合并：同一对 entity 之间的同类关系只保留一条，specialty 合并
5. 输出 yaml

## 源文本（用于回扫直接陈述关系）
{TEXT}
```

## 五、执行流程

```
1. 加载 kg/entities/<chapter_id>.yaml 和 kg/events/<chapter_id>.yaml
2. 遍历事件 → 推导关系：
   a. 出家受戒事件 → teacherOf[戒律]（亲教师→受戒者）
   b. 灌顶事件 → teacherOf[灌顶]
   c. 弘法/传法事件 → teacherOf[教授/口传/大圆满/密法]
   d. 建寺事件 → builtBy
   e. 译经事件 → translatedBy
   f. 降伏非人事件 → subduedBy（仅具名非人）
   g. 伏藏埋藏事件 → concealedBy
   h. 伏藏开取事件 → revealedBy + revealedFrom
   i. 关系继承事件的 layers / confidence / author_stance
3. 扫描实体注册表 → 补充关系：
   a. manifestation_of 字段 → manifestationOf 关系
   b. form_of 字段 → form_of 关系
   c. members 字段 → memberOf 关系
4. 回扫源文本 → 补充直接陈述关系：
   a. 父子/配偶/兄弟 → fatherOf / consort / siblingOf
   b. 统治 → rulerOf
   c. 大臣 → ministerOf
   d. 宗派归属 → belongsToSect
   e. 典据引用 → cites
   f. 异说/反驳 → alternativeOf / refutes / reconciles
5. 去重：同一 (source, target, type) 合并，specialty 合并
6. 输出 yaml 到 kg/relations/<chapter_id>.yaml
7. 运行质量检查（§六）
```

## 六、质量检查

| # | 检查 | 方法 |
|---|---|---|
| 1 | **entity_id 有效** | source/target 都能在实体注册表中找到 |
| 2 | **类型约束** | teacherOf 的 source 应为人物/圣众，target 应为人物；builtBy 的 source 应为寺院 |
| 3 | **specialty 仅限 teacherOf** | 非 teacherOf 关系不应有 specialty 字段 |
| 4 | **对称一致** | symmetric=true 的关系只有一条 record |
| 5 | **layer 必填** | 所有 record 的 layers 列表非空 |
| 6 | **重复关系** | 同一 (source, target, type) 不出现两次 |
| 7 | **事件推导回溯** | derived_from 引用的事件 id 在事件记录中存在 |
| 8 | **遗漏扫描** | 回扫源文本中的"之师""之徒""建造""翻译"等关键词，检查是否有关系遗漏 |

## 七、输出位置与命名

```
kg/
├── entities/
│   └── ch03.yaml
├── events/
│   └── ch03.yaml
├── relations/
│   ├── ch03.yaml                # 第三品全章关系
│   └── ...
```

## 八、已知局限

1. **师承 specialty 粒度**：灌顶/口传/戒律/教授/大圆满/密法 六类覆盖第三品，后续章节可能需要扩展
2. **隐含关系难捕捉**：文本未明言但可推导的关系（如同门师兄弟）不在本阶段处理
3. **通称非人无关系**：无名鬼神不建 entity，也不产生 subduedBy 关系；降伏通称非人只记录在事件 description 中
4. **引文关系（cites 等）初步**：异说/反驳/调和的结构化是后续 SKILL_07 的重点，本阶段仅做初步标注
5. **跨章关系**：同一关系若在多章提及，以首次出现为主 record

## 九、版本历史

| 版本 | 日期 | 改动 |
|---|---|---|
| v0.1 | 2026-04-11 | 首版，基于 entity-taxonomy v0.4 + narrative-layers v0.2 + SKILL_04a + PoC 经验编写 |
