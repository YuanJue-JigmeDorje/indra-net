# 因陀罗之网 — 佛教知识图谱汇集

> *华严经云：因陀罗网中，每颗宝珠映照一切宝珠。知识图谱亦如是——每个实体通过关系映射全局。*

**Indra's Net** 是一个用 AI 将藏传佛教典籍系统性转化为结构化知识图谱的项目。

## 在线体验

- 🌐 **[星图浏览器](https://yuanjue-jigmedorje.github.io/indra-net/app/prototype/index.html)** — 力导向图，全书实体关系一览
- 🌳 **[传承谱系](https://yuanjue-jigmedorje.github.io/indra-net/app/prototype/lineage.html)** — 搜索任意上师，查看师承上下
- 📖 **[阅读视图](https://yuanjue-jigmedorje.github.io/indra-net/app/reader/index.html)** — 全文阅读，实体标注可点击

## 当前数据

首部典籍：第二世敦珠法王《藏密佛教史》（索达吉堪布译）

| 维度 | 数量 |
|---|---|
| 实体 | ~3,000+ |
| 关系 | ~3,000 |
| 事件 | ~3,600+ |
| 覆盖 | 全书八品 |

## 方法论

本项目的知识构建管线借鉴了 [shiji-kb](https://github.com/baojie/shiji-kb)（西瓜/鲍捷的《史记》知识库项目），并针对藏传佛教典籍的特殊性做了改造。

### 管线架构（V2 三层 Agent）

```
gazetteer 预扫描（82k 佛学术语）
       ↓ 候选清单
段落级 Agent × N（并行，100行/段 + 候选实体）
       ↓ 实体 + 事件 + 关系
章级汇总 Agent（去重 + 跨段关系）
       ↓
完整知识图谱
```

### 核心规范文档

| 文档 | 内容 |
|---|---|
| [叙述层标签](doc/narrative-layers.md) | 7 种叙述层（史传/典据/授记/宗派/神变/证境/传闻） |
| [实体分类](doc/entity-taxonomy.md) | 11 类实体 + 21 条原则 + 3 条判定规则 |
| [事件 Schema](doc/event-schema.md) | 14+ 种事件类型（含引文论证） |
| [关系类型](doc/relation-types.md) | 22+ 种关系类型（师承用 specialty 标签） |

### 管线 SKILL

| SKILL | 功能 |
|---|---|
| [SKILL_03a](skills/SKILL_03a_实体标注.md) | 实体标注（双轨：gazetteer + NER） |
| [SKILL_04a](skills/SKILL_04a_事件识别.md) | 事件识别（含引文论证） |
| [SKILL_05a](skills/SKILL_05a_关系构建.md) | 关系构建（cites 含 quoted_text） |

## 版权声明

**源典译本不在本仓库内**。本项目使用的汉译典籍受版权保护：

- 敦珠法王《藏密佛教史》索达吉堪布译本，版权归译者及原出版方所有

仓库公开内容仅限：
- 本项目自行开发的知识图谱产物
- 方法论文档
- 可视化应用
- 必要时引用的少量片段（在合理使用范围内）

## 致谢

- **[shiji-kb](https://github.com/baojie/shiji-kb)**（西瓜/鲍捷）— 方法论母本
- 佛学辞典：丁福保《佛学大辞典》、佛光大辞典 — gazetteer 数据源
- 索达吉堪布 — 译本

## License

MIT
