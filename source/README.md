# source/

源文本工作区——**本目录下的实际文本内容均不入 git**（见根目录 `.gitignore`）。

## 子目录约定

每部典籍占一个独立子目录，按译者/版本命名（小写、连字符）：

```
source/
└── <book-slug>/
    ├── raw/            # 原始 PDF / OCR 输出 / 扫描件（不入库）
    ├── collated/       # 校勘后的纯文本底本（不入库）
    └── chapter_md/     # 分章带标注的 Markdown（不入库）
```

## 当前典籍

- `dudjom/` — 第二世敦珠法王《藏密佛教史》（索达吉堪布译）

## 处理流程

1. PDF 放入 `<book>/raw/`
2. 文本提取与清洗 → `<book>/collated/full.md`
3. 分章并加结构化标注 → `<book>/chapter_md/NN_title.md`
4. 进入 `kg/` 阶段（实体/事件/关系标注与构造）

知识图谱产物（在 `kg/` 下）会进入 git，源文本本身不会。
