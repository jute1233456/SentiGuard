# BettaFish 项目工作流程与提示词参考

> 本文档基于对 BettaFish 项目全部核心代码的深入研读，记录其完整工作流程和所有提示词设计，作为 SentiGuard 事实核查报告模块的参考。

---

## 一、整体架构：四引擎 + 论坛 + 报告引擎

```
用户输入 query
    │
    ├─→ InsightEngine (舆情数据库搜索)  ─┐
    ├─→ MediaEngine  (网络多媒体搜索)   ─┤
    └─→ QueryEngine  (通用联网搜索)      ─┘
                    │
                    ▼
            ForumEngine (三引擎讨论)
                    │
                    ▼
            ReportEngine (合成最终报告)
                    │
                    ▼
              最终 HTML 报告
```

**关键设计**：三个引擎**独立并行**运行，各自产出一份 Markdown 报告。ForumEngine 让三引擎互相讨论、交换意见。ReportEngine 以三引擎的报告 + 论坛日志为素材，合成一份最终 HTML 报告。

---

## 二、InsightEngine 工作流程（舆情数据库搜索）

### 2.1 流程图

```
Step 1: 生成报告结构
  LLM → 输出 5 个段落的 title + content（每个段落描述需要研究什么）
  Prompt: SYSTEM_PROMPT_REPORT_STRUCTURE
  输出: [{title, content}, ...]

Step 2: 逐段处理（对每个段落循环）
  Step 2.1: 首次搜索
    LLM → 输出 search_query + search_tool + reasoning
    Prompt: SYSTEM_PROMPT_FIRST_SEARCH
    执行搜索（从本地舆情数据库查）
    关键词优化中间件：原始query → LLM 拆分多个子关键词 → 多次搜索合并
    聚类采样：超过50条结果 → KMeans聚类 → 每簇取5条

  Step 2.2: 首次总结
    LLM → 基于搜索结果写段落摘要
    Prompt: SYSTEM_PROMPT_FIRST_SUMMARY
    要求：800-1200字，引用5-8条用户评论，包含情感分析数据

  Step 2.3: 反思循环（默认 3 次）
    每轮：
      LLM → 反思当前段落是否有信息缺口 → 生成新搜索query
      Prompt: SYSTEM_PROMPT_REFLECTION
      执行补充搜索
      LLM → 基于新搜索结果扩充段落
      Prompt: SYSTEM_PROMPT_REFLECTION_SUMMARY
      要求：保留70%原内容，新增不少于100%，最终1000-1500字

Step 3: 最终报告格式化
  LLM → 把所有段落拼成完整报告（不少于一万字）
  Prompt: SYSTEM_PROMPT_REPORT_FORMATTING
```

### 2.2 关键配置

| 参数 | 值 | 说明 |
|------|-----|------|
| MAX_REFLECTIONS | 3 | 每段反思搜索次数 |
| MAX_PARAGRAPHS | 6 | 最多段落数 |
| MAX_CLUSTERED_RESULTS | 50 | 聚类后最大结果数 |
| RESULTS_PER_CLUSTER | 5 | 每簇采样数 |
| MAX_CONTENT_LENGTH | 500000 | 传给 LLM 的搜索结果最大长度 |

### 2.3 如何判定信息是否充足

**没有显式的"充足判定"逻辑。** 采用**固定次数反思循环**：
- 每个段落固定执行 MAX_REFLECTIONS（默认3）次反思
- 每次反思 LLM 自己评估是否需要补充信息
- 反思节点的 prompt 引导 LLM 检查：是否过于官方化？是否缺乏真实民众声音？是否遗漏了重要观点？

---

## 三、MediaEngine 工作流程（网络多媒体搜索）

### 3.1 流程图

```
Step 1: 生成报告结构（最多5个段落）
  Prompt: SYSTEM_PROMPT_REPORT_STRUCTURE

Step 2: 逐段处理
  Step 2.1: 首次搜索
    LLM → 输出 search_query + search_tool + reasoning
    5种搜索工具：comprehensive_search / web_search_only /
                search_for_structured_data / search_last_24_hours /
                search_last_week
    每次搜索结果取前10条

  Step 2.2: 首次总结（800-1200字）
    整合网页、图片、AI总结、结构化数据

  Step 2.3: 反思循环（默认 MAX_REFLECTIONS 次）
    补充搜索 + 扩充段落

Step 3: 最终报告格式化（不少于一万字）
```

### 3.2 与 InsightEngine 的关键差异

| 方面 | InsightEngine | MediaEngine |
|------|--------------|-------------|
| 数据源 | 本地舆情数据库（5种DB工具） | 网络搜索 API（Bocha/Anspire） |
| 情感分析 | 内置情感分析器 | 无 |
| 搜索工具 | search_hot_content等 | comprehensive_search等 |
| 关键词优化 | 有（拆分+多次搜索） | 无 |
| 聚类采样 | 有（KMeans） | 无 |

---

## 四、ForumEngine（多Agent讨论）

### 4.1 工作机制

```
ForumHost (LLM: Qwen3)
    │
    ├─→ 解析三引擎的发言内容
    ├─→ 构建 system prompt（主持人角色设定）
    ├─→ 生成主持人发言（引导、总结、提问）
    └─→ 循环多轮讨论
```

主持人从三引擎的日志中解析出各 Agent 的发言，然后引导讨论。讨论日志最终作为 ReportEngine 的输入之一。

---

## 五、ReportEngine 工作流程（最终报告合成）

### 5.1 流程图

```
输入：三引擎报告 + 论坛日志 + 用户query

Step 1: 模板选择
  LLM 从 6 种 Markdown 模板中选最合适的
  Prompt: SYSTEM_PROMPT_TEMPLATE_SELECTION

Step 2: 模板切片
  parse_template_sections() → List[TemplateSection]
  解析 Markdown 模板的 #/##/### 标题层级

Step 3: 文档布局设计
  LLM → 设计 title/subtitle/hero/tocPlan/themeTokens
  Prompt: SYSTEM_PROMPT_DOCUMENT_LAYOUT
  输出：标题、Hero区（摘要+KPI+亮点）、目录规划（每章anchor+描述）

Step 4: 篇幅规划
  LLM → 为每章分配字数（总约40000字）
  Prompt: SYSTEM_PROMPT_WORD_BUDGET
  输出：totalWords + chapters[{targetWords/minWords/maxWords/emphasis}]

Step 5: 逐章生成（每个章节独立调用 LLM）
  LLM → 生成结构化 JSON blocks
  Prompt: SYSTEM_PROMPT_CHAPTER_JSON
  每章独立调用，每次只拿到：
    - 该章的 section 信息（title/outline/order）
    - 全局上下文（query/templateName/themeTokens）
    - 三引擎报告原文
    - 论坛日志
    - 该章的字数约束
  不传 KPI/摘要等全局数据给章节 LLM！

  支持的 18 种 block 类型：
    heading, paragraph, list, table, swotTable, pestTable,
    blockquote, engineQuote, hr, code, math, figure,
    callout, kpiGrid, widget, toc

  容错机制：
    - JSON 解析失败 → json_repair 库修复 → 跨引擎 LLM 修复 → 占位章节
    - 内容不足（<600字/2个非标题块）→ 重新生成
    - 结构校验失败 → LLM 修复 → 占位

Step 6: 章节装订
  DocumentComposer.build_document() → Document IR

Step 7: HTML 渲染
  HTMLRenderer.render(document_ir) → 完整 HTML
  按 block type 分派渲染，包含：
    - Chart.js 图表、词云
    - 暗色模式、打印/PDF 导出
    - 吸顶导航栏、目录
```

### 5.2 ReportEngine 章节规划方式

**不是硬编码的章节列表！** 而是：

1. **模板驱动**：从 6 种 Markdown 模板中 LLM 选择一个，然后解析模板的 `#`/`##` 标题作为章节骨架
2. **LLM 设计目录**：DocumentLayoutNode 基于模板骨架 + 三引擎内容，动态设计 tocPlan（每章 anchor、display名称、描述、是否允许 SWOT/PEST）
3. **LLM 分配字数**：WordBudgetNode 基于内容密度为每章分配目标字数

### 5.3 关键设计原则

1. **每章 LLM 看不到全局 KPI/摘要** — 只拿到该章的 section 信息 + 原始素材
2. **章节之间不跨引用** — 每章独立生成，不知道其他章写了什么
3. **结构化 IR 作为中间层** — LLM 输出 JSON，渲染器精确渲染，不做 Markdown→HTML 正则转换
4. **多层容错** — JSON 修复 → LLM 修复 → 占位章节，单章失败不影响其他章

---

## 六、全部提示词汇总

### 6.1 InsightEngine 提示词

#### SYSTEM_PROMPT_REPORT_STRUCTURE
```
你是一位专业的舆情分析师和报告架构师。给定一个查询，你需要规划一个全面、深入的舆情分析报告结构。

**报告规划要求：**
1. **段落数量**：设计5个核心段落，每个段落都要有足够的深度和广度
2. **内容丰富度**：每个段落应该包含多个子话题和分析维度
3. **逻辑结构**：从宏观到微观、从现象到本质、从数据到洞察的递进式分析
4. **多维分析**：确保涵盖情感倾向、平台差异、时间演变、群体观点、深度原因等多个维度

**段落设计原则：**
- **背景与事件概述**
- **舆情热度与传播分析**
- **公众情感与观点分析**
- **不同群体与平台差异**
- **深层原因与社会影响**

每个段落的content字段应描述该段落需要包含的具体内容，至少3-5个子分析点。
输出 JSON: [{title, content}, ...]
```

#### SYSTEM_PROMPT_FIRST_SEARCH
```
你是一位专业的舆情分析师。你将获得报告中的一个段落（title + content）。
你可以使用以下6种专业的本地舆情数据库查询工具：
1. search_hot_content - 查找热点内容
2. search_topic_globally - 全局话题搜索
3. search_topic_by_date - 按日期搜索话题（需要start_date/end_date）
4. get_comments_for_topic - 获取话题评论
5. search_topic_on_platform - 平台定向搜索（需要platform参数）
6. analyze_sentiment - 多语言情感分析

**你的核心使命：挖掘真实的民意和人情味**
**搜索词设计核心原则**：
- 避免官方术语（不要用"舆情传播"、"公众反应"）
- 使用网民真实表达
- 包含情感词汇
- 考虑网络文化

输出 JSON: {search_query, search_tool, reasoning}
```

#### SYSTEM_PROMPT_FIRST_SUMMARY
```
你是一位专业的舆情分析师和深度内容创作专家。
**你的核心任务：创建信息密集、数据丰富的舆情分析段落**
**撰写标准（每段不少于800-1200字）：**
1. 开篇框架：2-3句话概括核心问题
2. 数据详实呈现：引用至少5-8条代表性评论，精确数据统计
3. 多层次深度分析：现象→数据→观点→深层洞察
4. 具体引用要求：直接引用用户原始评论，标注来源平台和数量
5. 每100字至少包含1-2个具体数据点或用户引用

输出 JSON: {paragraph_latest_state}
```

#### SYSTEM_PROMPT_REFLECTION
```
你是一位资深的舆情分析师。你负责深化舆情报告的内容。
**反思的核心目标：让报告更有人情味和真实感**
你的任务是：
1. 深度反思内容质量：是否过于官方化？是否缺乏真实的民众声音？
2. 识别信息缺口：缺少哪个平台的用户观点？缺少哪个时间段的舆情变化？
3. 精准补充查询：设计接地气的搜索关键词
**搜索词优化示例**：
- ❌ "争议事件" → ✅ "出事了"、"翻车"、"炸了"
- ❌ "情感倾向" → ✅ "支持"、"反对"、"心疼"、"666"

输出 JSON: {search_query, search_tool, reasoning}
```

#### SYSTEM_PROMPT_REFLECTION_SUMMARY
```
你是一位资深的舆情分析师和内容深化专家。
**你的核心任务：大幅丰富和深化段落内容**
**内容扩充策略（目标：每段1000-1500字）：**
1. 保留精华，大量补充：保留70%核心内容，新增不少于100%
2. 数据密集化处理：新增5-10条用户评论，情感分析升级
3. 每200字至少包含3-5个具体数据点
4. 每段至少包含8-12条用户评论引用

输出 JSON: {updated_paragraph_latest_state}
```

#### SYSTEM_PROMPT_REPORT_FORMATTING
```
你是一位资深的舆情分析专家和报告编撰大师。
**你的核心使命：创建一份深度挖掘民意、洞察社会情绪的专业舆情分析报告，不少于一万字**
报告结构包含：执行摘要、各段落深度分析、舆情态势综合分析、深层洞察与建议、数据附录
特色要求：情感可视化（emoji/颜色）、民意声音突出（引用块）、数据故事化

输出：完整 Markdown 报告
```

### 6.2 MediaEngine 提示词

#### SYSTEM_PROMPT_REPORT_STRUCTURE
```
你是一位深度研究助手。给定一个查询，你需要规划一个报告的结构和其中包含的段落。最多5个段落。
确保段落的排序合理有序。
输出 JSON: [{title, content}, ...]
```

#### SYSTEM_PROMPT_FIRST_SEARCH
```
你是一位深度研究助手。你可以使用以下5种多模态搜索工具：
1. comprehensive_search - 全面综合搜索（网页+图片+AI总结）
2. web_search_only - 纯网页搜索
3. search_for_structured_data - 结构化数据查询
4. search_last_24_hours - 24小时内最新信息
5. search_last_week - 本周信息

输出 JSON: {search_query, search_tool, reasoning}
```

#### SYSTEM_PROMPT_FIRST_SUMMARY
```
你是一位专业的多媒体内容分析师和深度报告撰写专家。
**每段不少于800-1200字**
要求：多源信息整合（网页+图片+AI总结+结构化数据）
每100字至少包含2-3个来自不同信息源的具体信息点
```

#### SYSTEM_PROMPT_REPORT_FORMATTING
```
不少于一万字的多媒体分析报告
包含：全景概览、各段落多模态信息画像、视觉内容深度解析、跨媒体综合分析
```

### 6.3 ReportEngine 提示词（最核心）

#### SYSTEM_PROMPT_TEMPLATE_SELECTION
```
你是一个智能报告模板选择助手。根据用户的查询内容和报告特征，从可用模板中选择最合适的一个。
可用模板类型：
- 企业品牌声誉分析报告模板
- 市场竞争格局舆情分析报告模板
- 日常或定期舆情监测报告模板
- 特定政策或行业动态舆情分析报告
- 社会公共热点事件分析报告模板
- 突发事件与危机公关舆情报告模板

输出 JSON: {template_name, selection_reason}
```

#### SYSTEM_PROMPT_DOCUMENT_LAYOUT
```
你是报告首席设计官，需要结合模板大纲与三个分析引擎的内容，为整本报告确定最终的标题、导语区、目录样式与美学要素。
目标：
1. 生成 title/subtitle/tagline
2. 给出 hero：summary、highlights、actions、kpis
3. 输出 tocPlan，一级目录用中文数字（一、二、三），二级用"1.1/1.2"
4. themeTokens / layoutNotes 字体、字号、留白建议
5. 不随意增删章节，仅优化命名或描述
6. SWOT/PEST 使用规则：全文最多一个章节允许

输出 JSON: {title, subtitle, tagline, tocTitle, hero{summary,highlights,kpis,actions}, themeTokens, tocPlan[{chapterId,anchor,display,description,allowSwot,allowPest}], layoutNotes}
```

#### SYSTEM_PROMPT_WORD_BUDGET
```
你是报告篇幅规划官，给每章及其子主题分配字数。
要求：
1. 总字数约40000字，可上下浮动5%
2. chapters 每章包含 targetWords/min/max、emphasis、sections
3. rationale 必须解释该章篇幅配置理由

输出 JSON: {totalWords, tolerance, globalGuidelines, chapters[{chapterId,title,targetWords,minWords,maxWords,emphasis,rationale,sections}]}
```

#### SYSTEM_PROMPT_CHAPTER_JSON（最重要）
```
你是Report Engine的"章节装配工厂"，负责把不同章节的素材铣削成符合《可执行JSON契约(IR)》的章节JSON。

要求：
1. 完全遵循IR版本结构，严禁输出HTML或Markdown
2. 仅使用以下Block类型：heading, paragraph, list, table, swotTable, pestTable, blockquote, engineQuote, hr, code, math, figure, callout, kpiGrid, widget, toc
3. 所有段落放入paragraph.inlines，混排样式通过marks表示（bold/italic/color/link等）
4. 所有heading必须包含anchor
5. SWOT块：只在constraints.allowSwot为true时使用
6. PEST块：只在constraints.allowPest为true时使用
7. engineQuote仅用于呈现单Agent的原话，engine取insight/media/query
8. 一级标题用中文数字（一、二、三），二级用阿拉伯数字（1.1、1.2）
9. 段落混排通过marks表达，禁止残留Markdown语法
10. 善用callout、kpiGrid、表格、widget提升版面丰富度
11. 输出JSON自检：禁止缺少逗号、列表嵌套过深、未闭合括号
12. 任何block都必须声明合法type

输出格式：{"chapter": {...遵循Schema的章节JSON...}}
```

---

## 七、对 SentiGuard 的启发

### 7.1 可以借鉴的设计

1. **反思循环（Reflection Loop）**：不是一次搜索就结束，而是多次反思"我还缺什么信息？"→ 补充搜索 → 丰富内容。我们的 evidence_seeker 目前只搜索一次。

2. **逐段/逐章独立生成**：BettaFish 每个章节独立调用 LLM，每章 LLM 只拿到该章的素材。我们的报告模块已经这样做了。

3. **结构化 IR**：LLM 输出 JSON blocks 而非 Markdown。我们已经实现了。

4. **信息充足判定**：BettaFish 用**固定次数反思**而非显式判定。每次反思 LLM 自己判断是否需要补充。我们也应该用固定次数（如2次）的反思循环来确保证据充足。

5. **关键词优化**：InsightEngine 用 LLM 把原始 query 拆分成多个子关键词，然后分别搜索，再合并去重。我们的 evidence_seeker 可以借鉴。

### 7.2 不适合直接复用的

1. **三引擎架构**：BettaFish 有三套不同的搜索引擎（舆情DB + 网络搜索 + 通用搜索），我们只有一个 Anspire 搜索引擎。
2. **论坛讨论**：ForumEngine 是三引擎互相讨论，我们的 FactAgent 内部节点是顺序流水线，没有多 Agent 讨论。
3. **40000 字报告**：舆情分析报告确实可以很长，但事实核查报告不需要这么长。我们的报告 1500-3000 字即可。
4. **6 种模板**：事实核查不需要 6 种模板，标准模板就够。
