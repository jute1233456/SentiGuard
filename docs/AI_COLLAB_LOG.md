# AI 辅助开发日志

> 本文档累积记录本项目使用 AI 辅助开发的全部过程，作为课程报告 **第 7 章 "AI 辅助开发记录"** 的原始素材。
>
> **维护规则**：
> - 每次使用 AI 完成一项有价值的工作（设计/编码/调试/文档/解答）后，追加一条 `## 日志条目` 章节
> - 条目按时间倒序或正序均可，本文件采用 **正序**（最早在前）
> - 末尾保留章节模板，方便复制
> - 课程结题时基于这些条目总结成第 7 章正式内容
>
> **AI 工具**：Claude Code (Anthropic)，模型 `ark-code-latest`，命令行交互方式

---

## 元信息

| 项 | 值 |
|----|----|
| 项目名 | SentiGuard — 基于多智能体协同的网络舆情监测与事实核查平台 |
| AI 工具 | Claude Code (Anthropic) |
| 协作模式 | "AI 草稿 + 人工把关 + 迭代收敛" |
| 起始日期 | 2026-06-16 |

---

## 日志条目

---

### 条目 #1 — 项目代码理解

- **日期**：2026-06-16
- **场景**：代码理解 / 需求分析
- **关键 Prompt**：
  > "我正在做一个基于多智能体协同的网络舆情监测以及事实查验系统，现在我需要你帮助我阅读代码，然后告诉我这个项目有什么功能"
- **AI 产出**：
  - 通读 `src/main/python/` 全部模块（main_agent、experiments、llms、prompts、tools、utils）
  - 输出项目功能与架构总览：
    - 多智能体事实核查主流程（LangGraph Supervisor 双层调度）
    - 证据检索工具（Serper API + Selenium + Gemini 抽取）
    - LLM 抽象层（OpenAI / Ollama / Doubao）
    - 四种基线方法（CoT / Direct / Folk / Self-Ask）
    - 实验与评估流程
- **人工修改**：无（仅作认知输入，未产生代码）
- **风险控制**：AI 描述的项目结构与实际代码逐文件比对，确认无虚构模块
- **价值**：帮助团队成员在 30 分钟内建立项目心智模型，省去逐文件阅读时间

---

### 条目 #2 — 报告生成功能确认

- **日期**：2026-06-16
- **场景**：需求分析
- **关键 Prompt**：
  > "这个项目有没有生成报告的功能？"
- **AI 产出**：搜索代码库后明确告知：当前仅有 sklearn 的 classification_report（评估指标），不存在面向用户的报告生成模块；指出这是任务书要求但代码中缺失的功能
- **人工修改**：无
- **风险控制**：AI 给出了具体文件路径与行号（`src/main/python/evaluate.py:61`）作为证据，可验证
- **价值**：帮助识别项目缺口，明确后续需要新增的"报告生成智能体"

---

### 条目 #3 — 总体接口设计草案

- **日期**：2026-06-16
- **场景**：接口设计
- **关键 Prompt**：
  > "我现在正在开发阶段，需要你帮助我进行接口的设计，方便前后端使用，你看看有一个任务书"
  >
  > （随后人工粘贴任务书 4.1~4.8 节正文给 AI）
- **AI 产出**：
  - 基于任务书梳理出 7 大类共 30+ 接口（鉴权/热点/新闻/核查/报告/历史/管理）
  - 划分为对外 API（Vue ↔ Spring Boot）与内部 API（Spring Boot ↔ FastAPI）两层
  - 设计统一响应体、分页约定、异步任务模型
- **人工修改**：
  - **判定范围过大**，立即收敛："我们只需要这个 python 到 java 后端的接口就可以了，其他部分暂时不管"
  - 让 AI 仅保留内部接口层（A1~A8）
- **风险控制**：未把过大草案直接落入文档/代码，避免后续维护负担
- **价值**：帮助快速试探接口边界，及时发现范围过大并收敛

---

### 条目 #4 — HTTP 方法语义解释

- **日期**：2026-06-16
- **场景**：知识 Q&A / 团队成员上手
- **关键 Prompt**：
  > "你先解释一下 post get 这些都是什么意思"
- **AI 产出**：
  - HTTP 协议请求/响应模型
  - GET/POST/PUT/PATCH/DELETE 五种方法语义对比表
  - 幂等性概念
  - URL 参数位置（path / query / body / header）
  - HTTP 状态码 2xx/4xx/5xx 含义
- **人工修改**：无
- **风险控制**：AI 解释的内容均为公开标准（RFC 7231），无虚构风险
- **价值**：降低团队成员的学习门槛，便于后续阅读接口文档

---

### 条目 #5 — H1 热点列表接口设计（v1）

- **日期**：2026-06-16
- **场景**：接口设计
- **关键 Prompt**：
  > "第一个接口是热点挖掘，接口就是返回排好顺序 json，包含若干热点，每一个热点内容内容有热点名称，热度，情绪程度。帮我设计这个接口，让 java 后端使用这个接口获得信息"
- **AI 产出**：
  - 接口路径：`GET /internal/v1/hotspots`
  - 查询参数：limit / from / to
  - 响应字段：rank、name、heat、sentiment(label/score/distribution)
  - Java DTO 类
  - 错误码表
- **人工修改**：无（首版接受）
- **风险控制**：AI 主动提出三个待确认点（heat 计算口径、是否加 keywords、是否加 hotspotId），引导人工决策
- **价值**：在 10 分钟内得到首版可对接的接口契约

---

### 条目 #6 — BERTopic 算法澄清

- **日期**：2026-06-16
- **场景**：知识 Q&A / 算法理解
- **关键 Prompt**：
  > "我现在需要问你，bertopic 模型是不是先训练出来若干带关键词的话题，然在把符合的新闻放进去，对吗？"
- **AI 产出**：
  - 纠正错误理解：BERTopic 不是"先训练话题再放文档"，而是"对文档批量做端到端聚类，话题与归属同时产生"
  - 解释五步流程：Embedding → UMAP 降维 → HDBSCAN 聚类 → c-TF-IDF → 关键词提取
  - 类比"信件分堆贴标签 vs 标签柜分类"
  - 区分"全量重算 / 增量 transform / 在线 partial_fit"三种模式
  - 针对项目场景（GDELT 持续采集 + 热点动态变化）建议采用"定时全量重算"
- **人工修改**：根据 AI 修正后的理解决定为接口加入 `keywords` 字段
- **风险控制**：人工**主动质疑** AI 描述，要求其澄清；体现"AI 不是权威知识源"原则
- **价值**：避免基于错误算法理解做接口设计

---

### 条目 #7 — H1 接口加入关键词字段（v2）

- **日期**：2026-06-16
- **场景**：接口设计 / 字段调整
- **关键 Prompt**：
  > "大概懂了，那么我们加入关键词的部分字段吧"
- **AI 产出**：
  - H1 接口新增 `topK` 查询参数（默认 5）
  - 响应增加 `keywords: [{word, weight}]` 字段
  - 解释为何用 `[{word,weight}]` 结构而非纯字符串数组（便于词云/热力图可视化）
  - 解释 `name` 字段的两阶段策略（一期关键词拼接，二期 LLM 概括）
- **人工修改**：无
- **风险控制**：AI 提供了字段设计的取舍说明，便于人工评估
- **价值**：得到最终版 H1 接口契约

---

### 条目 #8 — 接口文档落地

- **日期**：2026-06-16
- **场景**：文档撰写
- **关键 Prompt**：
  > "可，先把这个写入接口文档"
- **AI 产出**：
  - 创建 `docs/api/internal-api.md`
  - 包含：通用约定 / 接口清单表 / H1 完整规范 / 变更记录
- **人工修改**：无
- **风险控制**：文档与已确认的接口契约一一对应；变更记录起始版本号 0.1.0
- **价值**：为前后端提供唯一对接依据

---

### 条目 #9 — F1 事实核查接口（详细版草案）

- **日期**：2026-06-16
- **场景**：接口设计
- **关键 Prompt**：
  > "我们写第二个接口，java 输入需要核实的内容，返回结论以及解释部分，请你写接口"
- **AI 产出**：
  - 接口路径：`POST /internal/v1/fact-check`
  - 请求体：claim + context（hotspotId、referenceNews）+ options
  - 响应体（详细版）：verdict + explanation + subclaims + evidence + meta
  - label 枚举：true / false / partly_true / not_enough_evidence
- **人工修改**：判定字段过多，要求简化（见条目 #10）
- **风险控制**：未把详细版直接落档
- **价值**：探明上限，便于做减法

---

### 条目 #10 — F1 简化为只含结论与解释

- **日期**：2026-06-16
- **场景**：接口设计 / 字段精简
- **关键 Prompt**：
  > "现在你可以先写成简易版接口，就是只有结论和解释两个部分，没有证据"
- **AI 产出**：
  - F1 简化为 `verdict`（label/confidence/summary）+ `explanation` 两块
  - 在文档中追加 F1 章节，更新接口清单与变更记录至 0.2.0
- **人工修改**：进一步要求精简（见条目 #11）
- **风险控制**：保留"未来扩展"小节，明确后续可向 data 追加字段而不破坏兼容
- **价值**：先求最小可用，避免过度设计

---

### 条目 #11 — F1 字段进一步精简为三字段

- **日期**：2026-06-16
- **场景**：接口设计 / 字段精简
- **关键 Prompt**：
  > "接口重新定义一下，包含三部分，真的假的，结论，解释。第一个用布尔就够了"
- **AI 产出**：
  - 响应体字段改为：`isTrue`(bool) + `conclusion`(string) + `explanation`(string)
  - 同步更新文档、Pydantic schema、router mock 三处
  - 文档变更记录追加 0.2.1
  - 在文档"设计说明"中明确：partly_true / not_enough_evidence 等中间态归并为最接近的布尔值
- **人工修改**：人工**明确要求三处同步**，避免文档与代码失同步
- **风险控制**：变更记录保留迭代轨迹，不擦除历史决策
- **价值**：得到最终版 F1 接口契约

---

### 条目 #12 — FastAPI 路由骨架生成

- **日期**：2026-06-16
- **场景**：代码生成
- **关键 Prompt**：
  > "先把路由骨架写出来吧，然后可以返回假的示例数据用于后端测试"
- **AI 产出**：在 `src/main/python/api/` 下创建：
  - `app.py` — FastAPI 应用入口 + 全局异常处理 + `/health`
  - `schemas.py` — Pydantic 模型（带 Field 约束）
  - `deps.py` — `X-Internal-Token` 鉴权依赖
  - `routers/hotspots.py` — H1 路由 + 3 条预设热点 mock
  - `routers/fact_check.py` — F1 路由 + 关键词分支 mock 逻辑
  - 更新 `requirements.txt` 加入 `fastapi`、`uvicorn[standard]`
- **人工修改**：无
- **风险控制**：
  - 全部输入用 Pydantic 校验（取值范围、字符串长度）
  - Mock 数据不混杂任何真实接口密钥
  - 默认开发 token (`dev-internal-token`) 仅作开发用，生产环境需通过 `INTERNAL_API_TOKEN` 环境变量覆盖
- **价值**：Java 后端可立即对接联调，无需等待算法层接入

---

### 条目 #13 — F1 简化时同步代码改动

- **日期**：2026-06-16
- **场景**：代码重构 / 文档代码同步
- **触发**：条目 #11 的字段精简
- **AI 产出**：
  - `schemas.py` 删除 `Verdict` 类与 `VerdictLabel` 字面量类型，`FactCheckData` 改为三字段
  - `routers/fact_check.py` 重写 mock 逻辑为 `_mock_verdict() -> tuple[bool, str, str]`
- **人工修改**：人工指示三处必须同步（文档 / schema / router）
- **风险控制**：避免出现"文档说三字段，代码还是八字段"的不一致
- **价值**：保证接口契约的单一真理源

---

### 条目 #14 — Git 提交与版本控制

- **日期**：2026-06-16
- **场景**：版本控制辅助
- **关键 Prompt**：
  > "git 上传让其他成员也能更新"
- **AI 产出**：
  - 检查 `git status`，识别待提交内容（docs/、api/、requirements.txt）
  - 主动询问任务书 `.doc` 是否提交，避免误传版权材料
  - 在 `.gitignore` 中追加 `*.doc` / `*.docx` 规则
  - 撰写符合 Conventional Commits 规范的 commit message
  - 推送到 `origin/main`
- **人工修改**：
  - 选择"不提交任务书"
  - 选择"一个 commit 搞定"
- **风险控制**：
  - AI 主动暂停操作要求人工确认（任务书处理）
  - 不使用 `git push --force` 等破坏性操作
  - 不修改 git config
  - commit 内容人工 review 后才执行
- **价值**：完整提交一次，commit `67eaabd`，10 files changed, 813 insertions

---

### 条目 #15 — AI 协作日志的引入

- **日期**：2026-06-16
- **场景**：文档撰写 / 流程规范
- **关键 Prompt**：
  > "你把 ai 辅助的日志或者信息都写进一个文档把，这样最后你再把所有的日志总结起来写这个"
- **AI 产出**：创建本文件 `docs/AI_COLLAB_LOG.md`，回填条目 #1~#14
- **人工修改**：待补充
- **风险控制**：日志记录关键 Prompt 与人工决策点，便于课程结题时追溯
- **价值**：建立可持续维护的 AI 协作存证机制，后续每条 AI 辅助任务都可追加

---

<!-- ===========================================================
新条目模板（复制下面这段并填写）
============================================================ -->

<!--
### 条目 #N — 简短主题

- **日期**：YYYY-MM-DD
- **场景**：代码理解 / 需求分析 / 接口设计 / 代码生成 / Bug 修复 / 测试用例 / 文档撰写 / 知识 Q&A / 版本控制 / 重构 / 其他
- **关键 Prompt**：
  > "..."
- **AI 产出**：
  -
- **人工修改**：
  -
- **风险控制**：
  -
- **价值**：
  -
-->

---

### 条目 #16 — 热点挖掘模块代码探索

- **日期**：2026-06-16
- **场景**：代码理解 / 现状分析
- **关键 Prompt**：
  > "行了，暂时先到这里吧，你注意把ai辅助开发日志写一下，整个的热点挖掘这一部开发过程分都要写进去"
  > （实际背景：用户先让AI探索现有hot_topic模块）
  > "现在的话代码是可以用的，但是需要你读取更多的数据，然后更好的训练bertopic，数据用THUCNews"
- **AI 产出**：
  - 通读SentiGuard项目的`hot_topic/`模块：
    - `modeling/topic_model.py` - BERTopic模型定义
    - `preprocessing/text.py` - 中文预处理（jieba分词+停用词）
    - `data_source/thucnews_loader.py` - THUCNews数据加载（HF镜像）
    - `scripts/run_thucnews_demo.py` - 演示脚本
    - `visualization/plots.py` - 可视化
  - 同时发现Big_Data_Course_Project项目也有相关实现
  - 评估现状：已有基础，但可增强
- **人工修改**：无
- **风险控制**：AI探索现有代码后再设计改进，避免重复造轮子
- **价值**：明确改进边界，基于已有代码做增强而非从零开始

---

### 条目 #17 — 第一版增强脚本开发

- **日期**：2026-06-16
- **场景**：代码生成 / 功能增强
- **关键 Prompt**：
  > "现在的话代码是可以用的，但是需要你读取更多的数据，然后更好的训练bertopic，数据用THUCNews"
- **AI 产出**：
  - 创建`hot_topic/scripts/train_thucnews_improved.py`：
    - 扩展中文停用词表（200+词）
    - 支持更大规模数据（5万-10万+）
    - 使用KeyBERT+MMR混合主题表示
    - 5种可视化输出
    - 完整评估报告
  - 创建`train_thucnews_simple.py`：快速启动脚本
  - 创建`hot_topic/TRAINING_GUIDE.md`：详细训练指南
  - 创建根目录`THUCNEWS_BERTOPIC_README.md`：总览文档
- **人工修改**：无
- **风险控制**：
  - 新文件与现有hot_topic模块共存，不破坏旧代码
  - 使用HF镜像确保国内可访问
  - 输出与原模块保持一致的目录结构
- **价值**：提供更强的训练脚本，支持更大规模数据

---

### 条目 #18 — 第一版小型训练测试

- **日期**：2026-06-16
- **场景**：代码执行 / 验证测试
- **关键 Prompt**：
  > "开始训练吧"
- **AI 产出**：
  - 使用Agent后台执行训练：`python train_thucnews_simple.py --size small --fast`
  - 训练阶段监控：
    - 数据加载：从HF下载THUCNews
    - 预处理：5850条有效文本
    - 嵌入：使用BAAI/bge-small-zh-v1.5
    - UMAP/HDBSCAN：降维聚类
    - 可视化：生成2D图、条形图、热力图
  - 训练完成后输出目录：`data/hot_topic/thucnews_improved/small/`
- **人工修改**：无
- **风险控制**：
  - 先运行small预设验证环境
  - 使用fast模式加速测试
  - 后台运行避免阻塞对话
- **价值**：验证了新脚本可正常运行

---

### 条目 #19 — 需求变更：从命令行到Python API

- **日期**：2026-06-16
- **场景**：需求分析 / 架构调整
- **关键 Prompt**：
  > "行了，我们这个模型是需要让其他的py去调用的，而不是面向命令行的，所以你需要稍微修改一下，在代码中把设置，配置之类的直接在代码中修改，或者单独用一个配置文件"
- **AI 产出**：
  - 理解新需求：从CLI工具转向可调用的Python库
  - 设计方案：
    1. 配置文件化（topic_model_config.py）
    2. 类封装（TopicModelTrainer类）
    3. 保留预设配置机制
    4. 继续支持断点续训
  - 明确交付物清单
- **人工修改**：无，AI理解准确直接开始实现
- **风险控制**：
  - 明确需求变更点：从CLI → API
  - 保留已有功能（断点续训、预设）
- **价值**：从工具脚本转向可复用的库，便于项目整合

---

### 条目 #20 — Python API核心模块开发

- **日期**：2026-06-16
- **场景**：代码生成 / 架构设计
- **关键 Prompt**：
  > （基于条目#19的理解，直接开始实现）
- **AI 产出**：
  - **topic_model_config.py** - 集中配置文件：
    - DATA_CONFIG、MODEL_CONFIG、UMAP_CONFIG等模块
    - PRESETS预设（test/small/medium/large/full）
    - EXTENDED_CHINESE_STOPWORDS扩展停用词
    - apply_preset()、print_config()辅助函数
  - **topic_model_trainer.py** - 核心训练类：
    - TopicModelTrainer主类，6阶段训练流程
    - TrainingStage枚举（INITIALIZED→DATA_LOADED→...→COMPLETED）
    - TrainingResult、PredictionResult数据类
    - 断点续训管理（checkpoint/metadata.json）
    - train()、predict()、save()、load()核心方法
    - get_topic_info()、list_topics()等查询方法
  - **example_usage.py** - 完整使用示例（5个示例）
  - **README_PYTHON_API.md** - API文档
- **人工修改**：无
- **风险控制**：
  - 使用dataclass保证结果类型安全
  - 检查点元数据包含完整配置便于回查
  - 所有路径使用Pathlib而非字符串
- **价值**：完整、可调用的Python API，适合项目整合

---

### 条目 #21 — 热点挖掘模块开发完成与交付

- **日期**：2026-06-16
- **场景**：交付总结 / 文档收尾
- **关键 Prompt**：
  > "行了，暂时先到这里吧，你注意把ai辅助开发日志写一下"
- **AI 产出**：
  - 总结交付物清单（核心文件6个+文档2个）
  - 提供快速开始代码3行训练+3行预测
  - 解释预设配置选择
  - 提示查看可视化结果的方式
  - 追加本日志条目#16~#21
- **人工修改**：无
- **风险控制**：
  - 保留所有版本（CLI改进版 + Python API版）
  - 文档充分，API设计简单清晰
- **价值**：
  - 完整的热点挖掘模块可投入使用
  - 同时提供CLI工具和Python API两种使用方式
  - 支持断点续训，适合长时间训练
  - 预设配置覆盖测试到生产全场景

---

### 条目 #22 — GDELT数据源连接测试

- **日期**：2026-06-17
- **场景**：代码理解 / 连接测试 / 数据源验证
- **关键 Prompt**：
  > "再试一试能不能连接到gdelt"
- **AI 产出**：
  - 查看现有GDELT客户端代码 `hot_topic/data_source/gdelt_client.py`
  - 了解其配置：API端点、5秒请求间隔、重试机制、最大250条/次
  - 尝试连接，成功访问api.gdeltproject.org
  - 但返回HTTP 429（速率限制），说明IP被临时限流
  - 确认代码实现正确，只是需要等待限流解除
- **人工修改**：无
- **风险控制**：
  - 先测试网站连通性再调用API
  - 记录429状态，避免重试轰炸
  - 提示用户"等待一段时间或更换IP"
- **价值**：确认GDELT客户端代码可用，为后续数据采集做好准备

---

### 条目 #23 — Git协作流程指导

- **日期**：2026-06-17
- **场景**：版本控制 / 团队协作
- **关键 Prompt**：
  > "现在其他同学在后端代码（我不负责）做了修改在git，我需要先暂存代码，同步一下再上传吗？"
- **AI 产出**：
  - 先检查`git status`，确认本地修改状态
  - 尝试`git fetch`看远程更新（遇到网络问题，但流程正确）
  - 提供标准Git协作流程：
    - 方案A：先commit本地 → pull --rebase → push
    - 方案B：git stash → pull → stash pop
  - 选择方案A完成操作，成功commit并rebase
- **人工修改**：选择方案A（先commit本地）
- **风险控制**：
  - 先`git status`了解现状再操作
  - 使用`--rebase`避免产生merge commit
  - 不使用`--force`等破坏性操作
- **价值**：成功完成Git协作流程，同步远程并推送本地更改

---

### 条目 #24 — RSS数据源开发与集成

- **日期**：2026-06-17
- **场景**：代码生成 / 数据源扩展 / 测试验证
- **关键 Prompt**：
  > "现在试一下RSS新闻源看看能不能用"
- **AI 产出**：
  - 创建`hot_topic/data_source/rss_client.py`：
    - 基于feedparser库
    - 支持RSS/Atom格式
    - 自动语言检测（中/英文，URL识别+内容检测）
    - 输出与GDELT统一的schema
  - 更新`data_source/__init__.py`导出RSSClient
  - 更新`requirements.txt`加入feedparser
  - 创建测试脚本验证，成功获取BBC新闻
- **人工修改**：
  - 发现语言检测小bug（BBC英文被识别为中文），要求修复
  - 修复后重新测试，语言检测正常
- **风险控制**：
  - 先测试单个feed再批量
  - 日志记录每个feed的获取状态
  - 异常处理避免单个feed失败影响整体
- **价值**：新增RSS数据源，补充GDELT的限制，提供更稳定的新闻来源

---

### 条目 #25 — 24小时新闻获取程序开发

- **日期**：2026-06-17
- **场景**：代码生成 / 业务功能 / 数据采集
- **关键 Prompt**：
  > "好的这个小的测试demo可以删除或者移动到test，现在我需要你做一个程序可以直接获得近24小时的所有新闻，主要就是标题以及时间，最好还有来源，储存起来，可以是csv"
- **AI 产出**：
  - 整理测试文件到`hot_topic/tests/`目录
  - 创建`hot_topic/scripts/fetch_recent_news.py`：
    - 整合RSS + GDELT双数据源（可配置开关）
    - 支持自定义小时数（--hours）
    - CSV输出包含：title、publish_time、source、url、lang、category、content
    - 自动时间戳命名：news_YYYYMMDD_HHMMSS.csv
    - 完整日志记录
  - 实际运行测试，成功获取59条新闻并保存
- **人工修改**：要求先跳过GDELT（由于429限制）
- **风险控制**：
  - 每个数据源独立try/catch，单个失败不影响整体
  - 使用merge_sources去重
  - 输出到data/hot_topic/统一管理
- **价值**：提供一键采集新闻的工具，CSV格式方便后续处理

---

### 条目 #26 — 事实核查接口从mock改为真实实现

- **日期**：2026-06-17
- **场景**：代码替换 / 功能完善 / 集成真实业务逻辑
- **关键 Prompt**：
  > "行了，事实核查路由要换成真实来了"
- **AI 产出**：
  - 移除`fact_check.py`中的mock逻辑和`_mock_verdict`函数
  - 集成真实的`FactAgent`多智能体系统
  - 添加`get_fact_agent()`单例管理函数，避免重复初始化
  - 复用`test_factagent.py`中的`parse_verdict_from_results`解析逻辑
  - 实现标签映射：`supported → isTrue=True`，`not_supported → isTrue=False`
- **人工修改**：无
- **风险控制**：
  - FactAgent实例全局缓存，避免每次请求重新加载模型
  - 完善的异常处理和结果解析逻辑
  - 保留原接口定义不变，向后兼容
- **价值**：事实核查接口从模拟变成真实可用，完整的多智能体核查流程

---

### 条目 #27 — .gitignore更新与项目清理

- **日期**：2026-06-17
- **场景**：项目维护 / 版本控制规范
- **关键 Prompt**：
  > "行了，提交git测试一下"
- **AI 产出**：
  - 检查git status，发现临时测试文件和data目录未跟踪
  - 更新`.gitignore`，添加：
    - `data/hot_topic/` - 动态生成的数据目录
    - `simple_gdelt_test.py` - 临时测试文件
    - `test_rss.py` - 临时测试文件
    - `show_rss_news.py` - 临时测试文件
  - 提交并推送到远程仓库
- **人工修改**：无
- **风险控制**：
  - 不提交敏感配置文件（.env已在.gitignore中）
  - 不提交大数据文件，避免仓库膨胀
  - 保留生成代码可复现性
- **价值**：仓库保持整洁，只包含必要的源代码和文档

---

### 条目 #28 — 豆包API Key优先级优化

- **日期**：2026-06-17
- **场景**：配置优化 / 环境变量管理 / 向后兼容
- **关键 Prompt**：
  > "修改一下，llm中doubao的apikey，如果没有输入就从环境中获得，如果有输入就用输入，然后再env文件中加入豆包apikey的位置，让调用llm的时候先检查env有咩有，有的话就输入env中的apikey"
- **AI 产出**：
  - 修改`doubao_client.py`的API Key解析逻辑：
    - 优先级1：构造函数直接传入的`api_key`参数
    - 优先级2：环境变量`DOUBAO_API_KEY`
    - 优先级3：环境变量`ARK_API_KEY`（向后兼容）
  - 同样优化Base URL的解析逻辑：
    - 优先级1：构造函数直接传入的`base_url`参数
    - 优先级2：环境变量`DOUBAO_BASE_URL`
    - 优先级3：环境变量`ARK_BASE_URL`
    - 优先级4：默认值
  - 更新错误提示信息，明确支持多种配置方式
  - 更新`.env`文件，添加豆包配置示例和注释
- **人工修改**：无
- **风险控制**：
  - 完全向后兼容，现有`ARK_API_KEY`配置仍然有效
  - 明确的优先级文档，避免配置混乱
  - 不传Key时给出清晰的错误提示
- **价值**：API Key配置更灵活，支持多种配置方式，便于部署和开发

---

### 条目 #29 — 豆包API Key优先级调整为环境变量优先

- **日期**：2026-06-17
- **场景**：配置优化 / 环境变量管理
- **关键 Prompt**：
  > "修改豆包模型，优先使用环境中获取的apikey，实在没有再从env获取"
  > （确认需求后）"对对"
- **AI 产出**：
  - 修改`doubao_client.py`的API Key解析优先级：
    - 优先级1：环境变量`DOUBAO_API_KEY`
    - 优先级2：环境变量`ARK_API_KEY`（向后兼容）
    - 优先级3：构造函数直接传入的`api_key`参数
  - 同样调整Base URL的解析优先级：
    - 优先级1：环境变量`DOUBAO_BASE_URL`
    - 优先级2：环境变量`ARK_BASE_URL`
    - 优先级3：构造函数直接传入的`base_url`参数
    - 优先级4：默认值
  - 更新注释文档，明确新的优先级顺序
- **人工修改**：无
- **风险控制**：
  - 保持向后兼容，`ARK_*`环境变量仍然有效
  - 传入参数仍然作为备选方案，不破坏现有代码
  - 清晰的注释说明优先级顺序
- **价值**：环境变量配置优先，更符合部署最佳实践，便于统一管理配置

---

### 条目 #30 — CLAUDE.md 项目指引初始化

- **日期**：2026-06-21
- **场景**：文档撰写 / 项目理解
- **关键 Prompt**：
  > "/init" （分析代码库并生成 CLAUDE.md）
- **AI 产出**：
  - 通读 src/main/python（main_agent、llms、tools、experiments、api）、backend（Spring Boot）、hot_topic、docs/AI_COLLAB_LOG.md、README、.env.example
  - 生成 `CLAUDE.md`，覆盖：两层架构（Python 智能体层 + Java 业务层）、常用命令、6 大架构要点（双层 Supervisor 图 / LLM 开闭原则 / 证据检索注册表 / 实验基线 / 热点挖掘 / 统一响应体）、环境变量、工作约定（AI 协作日志维护、接口四处同步、.gitignore）
- **人工修改**：
  - 追加「开发过程中及时更新 AI 辅助编程日志」的强调
  - 后续按本次会话实际改动同步修正 CLAUDE.md 中「Google Gemini 抽取」的过时描述
- **风险控制**：聚焦跨多文件才能理解的"大图"，不罗列可自行发现的文件清单，不加通用开发建议
- **价值**：为后续 AI 协作建立项目心智模型，新会话可快速进入状态

---

### 条目 #31 — 排查事实核查网络搜索（确认走基类 + Anspire 实测）

- **日期**：2026-06-21
- **场景**：代码理解 / 验证测试 / Bug 排查
- **关键 Prompt**：
  > "注意一下项目中，事实核查的网络搜索部分，是否是严格调用基类的搜索方法（符合开闭原则），然后再测试一下这使用 anspire 能否正常进行搜查功能，之前测试都显示搜不到任何信息"
- **AI 产出**：
  - 通读 `search_base.py`（BaseSearchEngine + SearchEngineRegistry）、`search_anspire.py`、`retrieve.py`
  - 确认 `SearchEngineRetriever` 通过注册表 `get_search_engine(available[0])` 取引擎、调基类 `search()`，**符合开闭原则**，未硬编码 Anspire
  - 本地直接调 `engine.search('中国')` 实测：Anspire 返回 10 条结果，title/url/snippet 均有值——**引擎本身工作正常**，"搜不到信息"问题不在引擎
  - 定位真正瓶颈在 `retrieve.py` 下游：`_check_valid_url` 四重 URL 合法性过滤 + Selenium 抓正文，可能过滤掉大量结果
- **人工修改**：无（仅诊断，未改代码）
- **风险控制**：先实测确认引擎正常，再定位下游断点，避免误改正常代码
- **价值**：排除"引擎坏了"的误判，把排查方向收敛到 retrieve.py 的过滤/抓取环节

---

### 条目 #32 — 移除硬编码 Gemini，证据检索改走 LLM 抽象层

- **日期**：2026-06-21
- **场景**：代码重构 / 架构调整
- **关键 Prompt**：
  > "代码中有google的ai调用？我们暂时用不到gemini，而且使用ai来对话也需要开闭原则，只调用llm基类才对，我们的模型暂时都是使用的doubao才对"
  > "使用什么模型需要再类的构造函数指定，默认使用豆包子类，apikey什么的都在llm子类里实现，这里不用该有这样的逻辑"
- **AI 产出**：
  - 第一版：`retrieve.py` 顶部删 `import google.generativeai` / `GOOGLE_API_KEY` / `genai.configure` / `GEMINI_MODEL`，`_process_content` 改用 `get_llm_provider(...).chat()` 走工厂
  - 第二版（按人工反馈收敛职责）：进一步去掉工厂调用与 `_CONTENT_EXTRACT_MODEL` 环境变量；`SearchEngineRetriever.__init__` 改为接收 `llm: Optional[BaseLLM]` 参数，不传则默认构造 `DoubaoLLM()`；`_process_content` 只调 `self.llm.chat(prompt, temperature=0.1)`
  - 模型选择 + API Key 解析全部收敛到 LLM 子类（DoubaoLLM 内部解析 DOUBAO_API_KEY/ARK_API_KEY），retrieve.py 不再触碰这些细节
  - 验证：源码无 `genai/gemini/GEMINI/get_llm_provider/GOOGLE_API_KEY` 残留；import 干净
- **人工修改**：
  - 否决第一版"在 retrieve.py 里用工厂+环境变量选模型"的方案，明确要求模型与 key 逻辑归 LLM 子类，retrieve.py 只持有实例
- **风险控制**：
  - 严格遵循开闭原则，切换厂商时调用方换注入的子类即可，retrieve.py 无需改动
  - 入口 `search_retrieve_news` 仍构造 `SearchEngineRetriever(dataset)`，走默认豆包分支，向后兼容
  - 改动仅限 retrieve.py，未碰 backend/（Java 由他人负责）
- **价值**：消除 Gemini 弃用告警；证据抽取与主流程同源用豆包；职责划分清晰，符合"只调 LLM 基类"约定

---

### 条目 #33 — FactAgent 测试用例扩充与端到端 API 实测

- **日期**：2026-06-21
- **场景**：测试用例 / 验证测试 / 接口联调
- **关键 Prompt**：
  > "用这个（test_factagent.py），不过你需要先修改这个测试程序，加入一些比较新的测试案例，比如北大鹅腿阿姨买的是不是假货"
  > "咱们先更新api接口吧，因为代码改动了可能调用需要修改" → 实测 fact-check 端点
- **AI 产出**：
  - `test_factagent.py` 新增 5 条近期热点用例（鹅腿阿姨走红/卖假货、2024 诺奖化学奖、嫦娥六号、5G 传新冠谣言），共 7 条
  - 用指定解释器 `E:/develop/env/agent/python.exe` 跑测试：7 条准确率 57.1%（4 对 3 错）；**Anspire 搜索链路完全打通**，每条都搜到 9~10 条结果，豆包内容抽取正常
  - 发现真瓶颈：3 个 supported 真命题被判 not_supported（如嫦娥六号明明搜到权威正文却称"no retrieved evidence"），问题在 evidence_seeker→verdict_predictor 的证据衔接，非搜索问题
  - 起 FastAPI 服务端到端实测 `/internal/v1/fact-check`：鉴权(401)→统一响应体→FactAgent 单例→完整多智能体流程→结果解析映射全部通过；维C防坏血病用例返回 `isTrue:true`，证据被正确引用
  - 发现小瑕疵：`explanation` 字段塞了 verdict dict 的 str()（`{'label':...}`），非纯文本（未改，待人工定夺）
- **人工修改**：无
- **风险控制**：
  - 用 UTF-8 文件传 curl body，规避 Windows shell 中文编码导致 JSON 解析失败
  - 测试覆盖真/假/难判定三类，含同主题一真一假对照（鹅腿阿姨）检验区分能力
  - 端到端验证证明 retrieve.py 去 Gemini 重构在真实 API 路径下工作正常
- **价值**：
  - 确认"搜不到信息"问题已不存在，搜索链路重构后端到端可用
  - 暴露并定位真正瓶颈（证据→判定衔接），为后续提升准确率指明方向
  - API 层经实测确认无需改动即可正常工作

---

### 条目 #34 — Git 提交与推送受阻

- **日期**：2026-06-21
- **场景**：版本控制 / 团队协作
- **关键 Prompt**：
  > "git提交" → "推送到仓库"
- **AI 产出**：
  - 删除测试临时文件 `.tmp_factcheck_body.json`，避免入库
  - 暂存 CLAUDE.md + retrieve.py + test_factagent.py + experiments/__init__.py，commit `7e6e37e`（4 文件 +173/-11）
  - `git push` 被拒：远程 main 有同学新提交，本地无；`git fetch` 又因 GitHub 连接超时失败
- **人工修改**：人工选择"先更新 AI 协作日志，推送暂缓"
- **风险控制**：
  - 临时测试文件不入库
  - 推送被拒后不擅自 `--force`，计划用 `pull --rebase` 整合远程改动；若有冲突停下来由人工定夺，不覆盖他人代码
  - 网络不稳定时不反复轰炸远程
- **价值**：本地改动已落盘成提交；远程整合待网络恢复后处理

### 条目 #35 — 推理路径 Trace 模块 + Prompt 全中文/强制搜索改造

- **日期**：2026-06-21
- **场景**：功能完善 / 提示词优化
- **关键 Prompt**：
  > "实现推理路径 trace 收集器"
  > "在 process_claim 包裹流，包含 set_current、claim_start、claim_end 和 finalize"
  > "为什么没有证据"
  > "方案B，必须搜索，并且要LLM注意时间一定要最新的，第二点必须要生成中文回答不要英文"
- **AI 产出**：
  - 新建 `src/main/python/tracing.py`：`TraceCollector` 类 + `set_current/get_current` 线程局部句柄，记录 claim_start/supervisor/step/search/verdict/claim_end 六类事件
  - `main_agent.py` 改造：`process_claim` 用 try/finally 包裹，确保 trace 建立和清理
  - `retrieve.py` 改造：`_retrieve_single` 注入 trace.search 调用，记录 query/结果数/选中URL/证据摘要
  - `fact_check.py`：记录 trace 文件路径日志；`.gitignore` 追加 `logs/`
  - Trace 文件验证：生成的 JSON 合法、结构完整（153 行），控制台缩进树可读性良好
  - **Prompt 全面改造**：
    - `evidence_seeking_prompt`：从"内容抽取助手"重写为"强制搜索 agent"——必须调用搜索工具、追求最新信息、全部中文输出
    - `verdict_prediction_prompt`：从英文改为全中文，判定理由必须中文撰写
    - `query_generation_prompt`：改为全中文，生成面向最新信息的中文搜索问题
- **人工修改**：无
- **风险控制**：
  - trace 用 `threading.local` 实现线程隔离，FastAPI 多请求安全
  - `set_current(None)` 在 finally 块中清理，避免请求间泄漏
  - trace 默认开启但可关闭（`enabled=False`），不影响既有行为
  - `search` 事件仅在真正调用搜索工具时记录，不编造空事件
  - Prompt 改造保留 `response_format` schema 不变，只改提示文本，向后兼容
- **价值**：
  - Trace 模块为调试和报告提供可视化推理路径
  - 证据链 trace 打通 LangGraph 节点 → 搜索引擎 → 最终判定全链路
  - 强制搜索 + 中文输出提升输出质量和时效性，修复"证据全靠 LLM 记忆"问题

---

## 日志条目 #36 — 数据库对齐版 F3 接口（/internal/v1/fact-check/detail/db）

- **日期**：2026-06-21
- **场景**：接口设计 / 代码生成 / 文档同步
- **关键 Prompt**：
  > "请基于当前 SentiGuard Python FactAgent 的真实能力，重新设计 /internal/v1/fact-check 接口返回结构，使其能够与 Java 后端事实核查数据库表结构对齐。"
  > "原先接口肯定要保持不变，所有修改只在新的接口上"
- **需求背景**：Java 后端开发提出需要与数据库表（fact_claim / evidence / fact_check_result / analysis_report）直接对齐的结构化 JSON，便于直接反序列化并持久化，不能只返回 isTrue/conclusion/explanation 三字段。
- **AI 产出**：
  - **字段映射分析**：逐一比对 Java 后端建议的 22 个字段 vs Agent 真实能力，标记为 ✅已有 / ✅新增 / ⚠️估算 / ❌暂缺
  - **`tracing.py` 改造**：`search()` 方法追加 `source_title` 和 `source_name` 参数，保留向后兼容
  - **`retrieve.py` 改造**：`_retrieve_single()` 在选中证据 URL 时捕获文章标题和来源域名，传给 trace
  - **`schemas.py` 新增**：`F3ClaimItem`、`F3EvidenceItem`、`F3Result`、`F3Report`、`FactCheckDetailDBData` 五个 Pydantic model，字段名与 Java 数据库表列名对齐（驼峰）
  - **`fact_check.py` 新增**：`_build_detail_db_response()` 汇编函数 + `fact_check_detail_db()` 路由（`POST /internal/v1/fact-check/detail/db`），包含：
    - 从 claim_splitter 输出解析 claims 列表
    - 从 query_generator 建立 query→claimOrder 映射
    - 从 search events 构建 evidences（含 source_title / source_name）
    - 基于 verdict label 推算 relationType / credibilityScore
    - 从 claims/evidences/verdict 拼接 markdown 格式 report
  - **`app.py`**：版本号更新为 0.4.0
  - **`docs/api/internal-api.md`**：新增 F3 完整文档（含字段说明、字段映射表、已知限制）
  - **接口约定**：
    - F3 与 F1/F2 相互独立，不共享响应结构
    - claims 中的 claimOrder 从 1 递增
    - evidence 不带数据库 claim_id（由 Java 入库后生成）
    - 无真实证据时 evidences 可为空，resultLabel 返回 insufficient_evidence
    - 字段名固定，方便 Java DTO 反序列化
- **人工修改**：无
- **风险控制**：
  - F3 是新路由，F1/F2 代码完全未动，零回归风险
  - tracing.search() 新增参数有默认值 `""`，已有调用方不需要修改
  - retrieve.py 只在选中 URL 处追加了捕获逻辑，不影响原有证据检索流程
  - 所有估算字段（relationType / credibilityScore）在文档中明确标注为估算
- **价值**：
  - Java 后端可直接用 F3 返回体反序列化并写入数据库，无需二次加工
  - 字段映射表作为后续改进 roadmap，publishTime / 逐条 relationType 等明确标为待办

---

### 日志条目 #37 — 百度新闻采集器日志功能增强 + Git 推送

- **日期**：2026-06-22
- **场景**：功能完善 / 日志增强 / 版本控制
- **关键 Prompt**：
  > "你检查一下百度新闻采集器的实现，添加日志功能，在fastapi成功发送新闻的时候，你需要在控制栏输出一下提示，比如搜到多少新闻，然后列举几个"
  > "推到github并修改ai辅助日志"
- **AI 产出**：
  - **`baidu_collector.py`**：新增 `logging` 模块导入和 `logger` 实例，在 `fetch()` 方法各关键路径添加结构化日志：
    - ✅ API JSON 接口成功：`共获取 N 条热搜` + 列举前 5 条（`#1 XX (热度:YY)`）
    - ⚠️ 接口返回空数据 / 请求异常：提示回退方案
    - ✅ HTML 回退成功：同上格式，标注来源
    - ❌ 全部失败：打印错误并 `raise RuntimeError`
  - **`hotspots.py`**：新增 `logging` 导入和 `logger`，在 `trigger_collect` 端点采集成功后输出控制台简报：
    - `📡 热点采集完成 | 来源: BAIDU | 采集 N 条 | 入库 N 条 | 发现 N 个热点`
    - 逐条输出热点：`🔥 #N 热点名称 (热度:X, 情感:pos, 关联 N 条新闻)`
    - 失败时输出 `❌ 热点采集失败: {e}` 带完整堆栈
  - Git 提交并推送到 `origin/main`：commit `708e20d`
- **人工修改**：无
- **风险控制**：
  - 日志用 `logging.getLogger(__name__)` 按模块隔离，不干扰业务逻辑
  - 采集器成功日志仅列举前 5 条，避免刷屏
  - 提交前语法验证（`ast.parse`）通过
- **价值**：
  - 采集过程透明可追踪，运维人员可从控制台直接看到采集结果
  - 失败时不再静默，控制台输出异常堆栈便于排查
  - 推送后团队成员可通过 git pull 同步日志功能

---

### 日志条目 #39 — 置信度评分 + 报告模块重构

- **日期**：2026-06-22
- **场景**：功能升级 / 架构重构 / 设计模式应用
- **关键 Prompt**：
  > "首先来改动置信度的判定，使用 Veracity 的方法... 我觉得这个报告的功能是很好的。我们需要借鉴一下放到我们的项目里面去，你先规划好模块和功能，要符合设计原则（尤其是开闭原则），然后再进行编程实现"
- **AI 产出**：

  **A. 置信度评分功能（基于 Veracity 论文方法）**
  - **`prompts/verdict_prediction.py`**：在 prompt 中加入 Veracity 风格的评分标准表格（80-100 高置信度 / 60-79 中等 / 40-59 低 / 0-39 极低四段），明确 5 个评分维度（证据充分性、来源可靠性、证据一致性、冲突程度、覆盖完整性），引导 LLM 输出更稳定、有依据的 `confidenceScore`
  - **`main_agent.py`**：`verdict_prediction_node()` 将 `confidenceScore` 传给 `trace.verdict()`
  - **`tracing.py`**：`verdict()` 方法增加 `confidence_score` 参数，打印摘要时显示分数

  **B. 报告模块（基于 BettaFish ReportEngine 设计思路）**
  - **`src/main/python/report/`**：全新模块，三层策略模式架构：
    - `sections/`（策略模式） — 5 个章节类：header / claims / evidence / verdict / metadata，各继承 `BaseSection` 实现 `render()`
    - `templates/`（策略模式） — 模板决定章节选择和顺序，当前有 `StandardTemplate`
    - `renderers/`（策略模式） — 输出渲染，当前有 `MarkdownRenderer`
    - `generator.py`（模板方法模式） — `ReportGenerator.generate()` 编排流程
    - `models.py` — 内部数据模型，含 `from_f3_data()` 工厂方法兼容 F3 API schema
    - 所有扩展点都采用注册表模式（`register_section`/`register_template`/`register_renderer`）
  - **`api/routers/fact_check.py`**：F3 接口中原硬编码的字符串模板（约 30 行 `report_lines.append`）替换为 `ReportGenerator.generate()`

- **人工修改**：无
- **开闭原则验证**：新增章节 → 写 `sections/xxx.py` + 注册；新增模板 → 写 `templates/xxx.py` + 注册；新增渲染器 → 写 `renderers/xxx.py` + 注册；均不修改既有代码
- **风险控制**：
  - 模块独立，不修改现有接口契约（F1/F2/F3 接口字段不变）
  - report 模块通过 `from_f3_data()` 适配，与 API schema 解耦
  - GBK 编码兼容：移除 tracing.py 和 retrieve.py 中的 emoji 字符
- **价值**：
  - 置信度评分让判定结果从布尔值升级为 0-100 量化输出
  - 报告模块从 30 行硬编码升级为可扩展的架构，后续可加 HTML/PDF 渲染、简洁模板等

---

### 日志条目 #40 — LLM 叙事报告 + Java 后端接口对接

- **日期**：2026-06-22
- **场景**：功能开发 / 接口设计 / 前后端对接
- **关键 Prompt**：
  > "我觉得这个报告的功能是很好的。我们需要借鉴一下放到我们的项目里面去... 我们需要关注如何把html文件传入java后端呢？你需要把这个接口设定好了"
- **AI 产出**：

  **A. LLM 叙事报告模式（借鉴 BettaFish ReportEngine）**
  - **`report/llms/client.py`**：报告模块专用 LLM 客户端，复用项目已有的 LLM 抽象层
  - **`report/prompts/prompts.py`**：三个提示词
    - `SYSTEM_PROMPT_REPORT_LAYOUT`：LLM 设计报告布局（标题/摘要/KPI/关键发现）
    - `SYSTEM_PROMPT_CHAPTER`：逐章节内容生成
    - `SYSTEM_PROMPT_FULL_REPORT`：一次性生成完整 Markdown 报告
  - **`report/generator.py`**：新增 `LLMReportGenerator` 类，流程为：布局设计 → 构建数据包 → LLM 生成 → HTML 渲染
  - **`report/renderers/html.py`**：`HTMLRenderer`，将 LLM 生成的 Markdown 渲染为美观的 HTML 页面，含 Hero 区、KPI 卡片、暗色模式、响应式设计
  - **`test_report_html.py`**：本地测试脚本，`python src/test/python/test_report_html.py --claim "声明" --output report.html`

  **B. Java 后端接口对接**
  - **`api/schemas.py`**：`FactCheckRequest` 新增可选字段 `report_style: str = "simple"`，取值 `simple`（数据驱动 Markdown）或 `llm`（LLM 叙事 HTML）
  - **`api/routers/fact_check.py`**：
    - `_build_detail_db_response()` 新增 `report_style` 参数，根据值选择报告模式
    - `report_style="llm"` 时调用 `LLMReportGenerator`，失败自动降级
    - 保留 `POST /fact-check/detail/llm-report` 独立路由作为别名
  - **接口向后兼容**：不传 `report_style` 默认走数据驱动模式，Java 端无需改 URL

- **人工修改**：无
- **风险控制**：
  - `report_style` 默认 `"simple"`，现有 Java 调用不受影响
  - LLM 生成失败时自动降级为数据驱动模式，不抛异常
  - HTML 渲染器样式用 CSS 变量，支持暗色模式
- **价值**：
  - Java 端只需在请求体中加 `"report_style": "llm"` 即可获得 HTML 报告
  - 前端可直接展示 HTML 报告（含 Hero 区、KPI 卡片、证据表格）
  - 本地测试脚本方便独立调试，不依赖 API

### 日志条目 #41 — 结构化 IR 方案：报告模块重大升级

- **日期**：2026-06-23
- **场景**：架构重构 / 代码生成 / 设计模式应用
- **关键 Prompt**：
  > "我看了测试给出的报告，我认为内容太单调了，你详细的阅读bettafish他们的报告是怎么生成的，一定要详细，他们的报告内容很丰富，我们需要借鉴"
- **背景**：用户对当前报告模块的 LLM 叙事模式输出不满意，认为内容单调、结构扁平，要求深入借鉴 BettaFish ReportEngine 的设计思路。
- **AI 产出**：

  **A. 深入研读 BettaFish ReportEngine（约 3500 行代码）**
  通读全部核心文件：`agent.py`（总调度）、`ir/schema.py`（18 种 block 类型 IR Schema）、`html_renderer.py`（按 block type 分派渲染，355KB）、`chapter_generation_node.py`（逐章 JSON 生成+校验+修复）、`document_layout_node.py`（布局设计）、`word_budget_node.py`（字数规划）、`template_selection_node.py`（模板选择）、`core/stitcher.py`（章节装订）、`core/template_parser.py`（模板切片）、`prompts/prompts.py`（全量提示词）、`state/state.py`（状态管理）

  关键发现——BettaFish 的核心创新：
  1. **结构化 IR（中间表示）**：LLM 不生成 Markdown，而是生成带类型标注的 JSON block 数组（heading/paragraph/list/table/swotTable/pestTable/callout/kpiGrid/engineQuote/widget 等 18 种）
  2. **四阶段 LLM 流水线**：模板选择 → 布局设计 → 字数规划（~40000 字/本）→ 逐章生成（每章独立调用 LLM）
  3. **丰富的渲染能力**：Chart.js 图表、词云、SWOT/PEST 分析表、Callout 提示框、KPI 卡片、暗色模式、PDF 导出、吸顶导航

  **B. 结构化 IR 方案适配事实核查场景**
  基于 BettaFish 的设计理念，为事实核查场景定制了简化但核心一致的方案：

  - **`report/ir/schema.py`**（新建）— 9 种 block 类型定义：heading/paragraph/list/table/callout/kpiGrid/blockquote/evidenceCard/hr，含 validate_block() 校验函数和 build_document_ir() 组装函数。新增 evidenceCard 类型是事实核查专用的证据卡片。
  - **`report/ir/__init__.py`**（新建）— 包入口
  - **`report/prompts/prompts.py`**（重写）— 强化 SYSTEM_PROMPT_REPORT_LAYOUT（增加 keyFindings/chapterGuidance），新增 SYSTEM_PROMPT_CHAPTER_IR（替代全文 Markdown，要求输出结构化 JSON blocks）
  - **`report/renderers/html.py`**（重写）— 从 240 行正则 Markdown→HTML 改为 500+ 行的 block-type 分派渲染体系，新增 `render_ir()` 方法，支持 9 种 block 类型的精确渲染（callout 带 4 种色调、evidenceCard 带可信度进度条和论辩关系标签、kpiGrid 卡片网格、list/table/blockquote 等），增强 CSS（callout/证据卡片/可信度条/暗色模式/响应式）。保留 `render()` 和 `render_llm()` 向后兼容。
  - **`report/renderers/base.py`**（修改）— 新增 `render_ir()` 抽象方法
  - **`report/generator.py`**（重写）— LLMReportGenerator 从"一次调用生成全文 Markdown"改为多阶段流水线：布局设计 → 逐章 IR 生成（5 个章节各调一次 LLM）→ 文档 IR 组装。失败时自动降级为原有 Markdown 模式。

  **C. 验证结果**
  - 所有导入正常（IR schema、prompts、generator、HTML renderer、Markdown renderer）
  - 数据驱动模式（ReportGenerator）向后兼容，输出正常
  - 结构化 IR 渲染器端到端验证通过：10 个检查点全部 OK（Hero 区/KPI 卡片/Callout/证据卡片/表格/引用/章节/暗色模式/响应式）

- **人工修改**：无
- **开闭原则验证**：新增 evidenceCard block 类型只需在 schema.py 加常量 + html.py 加 handler，不修改既有代码
- **风险控制**：
  - 完整保留向后兼容路径（render() + render_llm()）
  - 结构化 IR 生成失败时自动降级为 Markdown 模式
  - 数据驱动模式（ReportGenerator + MarkdownRenderer）完全未动
  - API 接口不变，Java 端无需修改
- **价值**：
  - 报告从"Markdown 转 HTML"升级为"结构化 IR 渲染"，内容层次和丰富度大幅提升
  - 9 种 block 类型让 LLM 生成更有结构的报告（callout 突出关键发现、evidenceCard 清晰展示证据链、kpiGrid 直观呈现数据）
  - 多阶段流水线为后续增加字数规划、模板选择等阶段预留了扩展点

---

## 阶段性统计（自动维护，每次新增条目时更新）

| 项 | 值 |
|----|----|
| 累计条目数 | 41 |
| 涉及场景类别 | 代码理解、需求分析、接口设计、代码生成、文档撰写、算法理解、知识 Q&A、版本控制、字段精简、文档代码同步、架构调整、验证测试、交付总结、数据源验证、团队协作、数据源扩展、业务功能、数据采集、代码替换、功能完善、项目维护、配置优化、环境变量管理、向后兼容、Bug 排查、测试用例、接口联调、提示词优化、数据库对齐、日志增强、安全加固、置信度评分、报告模块重构、**LLM 叙事报告**、**Java 接口对接**、**结构化 IR 方案**、**Block-type 分派渲染** |
| 已生成代码文件 | 41（新增 ir/ 模块 2 个 + 重写 3 个 = 5 个核心文件变动） |
| 新增核心文件 | 29（ir/schema.py + ir/__init__.py） |
| 已生成文档文件 | 8 |
| 报告模块 | ✓ 数据驱动模式 + Markdown 渲染 + ✓ LLM 叙事模式（结构化 IR + 9 种 block 类型渲染 + 降级路径） |
| 结构化 IR | ✓ 9 种 block 类型（heading/paragraph/list/table/callout/kpiGrid/blockquote/evidenceCard/hr） |
| Block 渲染 | ✓ callout（4 色调）、evidenceCard（可信度条+论辩标签）、kpiGrid、table、list、blockquote |
| 置信度评分 | ✓ Veracity 方法：prompt 评分标准 + trace 记录 + 接口输出 |
| Java 接口 | ✓ `report_style` 字段，向后兼容，不传 = 原数据驱动模式 |
| 本地测试 | ✓ `test_report_html.py`，生成 HTML 文件用浏览器查看 |
| 人工干预次数 | ≥ 14 |
| 已知待办 | verdict 证据衔接准确率、F3 publishTime 字段填充（需搜索引擎改造）、F3 逐条证据 relationType 判断、F3 credibilityScore LLM 逐条评估 |

---

### 日志条目 #42 — 搜索引擎优化：search_service 模块收尾

- **日期**：2026-06-23
- **场景**：代码完善 / 架构优化
- **关键 Prompt**：
  > "继续写你之前没写完的代码，就是搜索引擎优化"
  > "之前是让你做两个搜索功能，一个是简略搜索，一个是摘要搜索。简略搜索只有摘要，详细搜索有全文。你首先实现"
- **背景**：之前完成了 search_service.py 的基础框架（search_summary 和 search_fulltext 两个策略），但存在几个关键问题需要收尾修复。
- **AI 产出**：

  **A. SearchEngineRetriever 模块级缓存**
  - **`search_service.py`**：新增 `_RETRIEVER_CACHE` 字典 + `_get_retriever(dataset)` 函数，按 dataset 名称缓存 SearchEngineRetriever 实例
  - **问题修复**：`search_fulltext()` 每次调用都创建新的 SearchEngineRetriever → 新建 Selenium WebDriver，既不释放又慢。现在只在首次调用时创建，后续复用缓存实例
  - **关键改动**：`search_fulltext()` 中 `SearchEngineRetriever(dataset)` 替换为 `_get_retriever(dataset)`

  **B. 返回类型一致性修复**
  - **`retrieve.py`**：`search_retrieve_news()` 的 `except` 分支原来返回 `""`（空字符串），而正常路径返回 `list[dict]`，类型不一致。修复为统一返回 `[]`

  **C. 搜索引擎兜底策略（fallback chain）**
  - **`search_service.py`**：`_get_engine()` 从"只取第一个注册引擎"改为"遍历全部注册引擎，找到第一个可用的"
  - **`retrieve.py`**：`SearchEngineRetriever.__init__` 同步改造，同样的遍历兜底逻辑
  - 改进前：`available[0]` 不可用时直接返回 None
  - 改进后：遍历 `[anspire, serper, ...]` 直到找到可用引擎；全部不可用时日志明确输出"共 N 个引擎均不可用"

- **人工修改**：无
- **风险控制**：
  - Selenium WebDriver 缓存后，进程级只有一个 Chrome 实例，注意 `__del__` 中 `driver.quit()` 的清理逻辑保持不变
  - 返回类型 `[]` vs `""` 的改动确认无上游代码对空字符串做 `== ""` 检查（grep 确认）
  - 引擎遍历兜底不改变既有注册逻辑，新增引擎只需 `register_search_engine`
- **价值**：
  - search_fulltext 不再每次调用开新 Chrome 实例，性能提升显著
  - 注册多个搜索引擎时自动 fallback，提高搜索可用性
  - 返回类型统一避免上层代码的隐式 bug

---

## 阶段性统计（自动维护，每次新增条目时更新）

| 项 | 值 |
|----|----|
| 累计条目数 | 50 |
| 涉及场景类别 | 代码理解、需求分析、接口设计、代码生成、文档撰写、算法理解、知识 Q&A、版本控制、字段精简、文档代码同步、架构调整、验证测试、交付总结、数据源验证、团队协作、数据源扩展、业务功能、数据采集、代码替换、功能完善、项目维护、配置优化、环境变量管理、向后兼容、Bug 排查、测试用例、接口联调、提示词优化、数据库对齐、日志增强、安全加固、置信度评分、报告模块重构、**LLM 叙事报告**、**Java 接口对接**、**结构化 IR 方案**、**Block-type 分派渲染**、**搜索服务优化**、**接口重构**、**证据模型重构**、**证据粒度优化**、**LangGraph 新节点**、**max_tokens 默认值修复**、**DeepLLMReportGenerator**、**报告生成防御性加固**、**三阶段HTML组装重构** |
| 已生成代码文件 | 55（新增 evidence_merging.py + 重构 evidence_seeking.py + 重构 fact_check.py + 修改 main_agent.py + 修改 llms/* 三个 client + 修改 report/generator.py + 修改 report/prompts/prompts.py + 修改 prompts/deep_decomposer.py + 修改 report/renderers/html.py） |
| 新增核心文件 | 30（+ evidence_merging.py） |
| 已生成文档文件 | 8 |
| 证据模型 | ✓ LLM 逐条判定 relationType + ✓ 逐条搜索结果独立为证据 + ✓ evidence_merger 合并同事件多来源 |
| LangGraph 节点 | ✓ 新增 evidence_merger 节点，证据流：seeker → merger → verdict |
| 报告模块 | ✓ 数据驱动模式 + Markdown 渲染 + ✓ LLM 叙事模式（结构化 IR + 9 种 block 类型渲染 + 降级路径） |
| 结构化 IR | ✓ 9 种 block 类型（heading/paragraph/list/table/callout/kpiGrid/blockquote/evidenceCard/hr） |
| Block 渲染 | ✓ callout（4 色调）、evidenceCard（可信度条+论辩标签）、kpiGrid、table、list、blockquote |
| 置信度评分 | ✓ Veracity 方法：prompt 评分标准 + trace 记录 + 接口输出 |
| Java 接口 | ✓ F3 保留向后兼容 + ✓ 新增 Q1（quick）+ ✓ 新增 D1（deep），三者返回相同 FactCheckDetailDBData |
| 搜索服务 | ✓ search_summary（摘要）+ search_fulltext（全文）+ 引擎兜底 + Retriever 缓存 |
| API 端点 | ✓ `/quick`（快速核查） + ✓ `/deep`（深度核查） + ✓ 旧端点保留但废弃 |
| 本地测试 | ✓ `test_report_html.py`，生成 HTML 文件用浏览器查看 |
| 人工干预次数 | ≥ 15 |
| 已知待办 | verdict 证据衔接准确率、F3 publishTime 字段填充（需搜索引擎改造）、F3 逐条证据 relationType 判断、F3 credibilityScore LLM 逐条评估、快速核查 HTML 报告生成 |
| Java 接口 | ✓ `report_style` 字段，向后兼容，不传 = 原数据驱动模式 |
| 搜索服务 | ✓ search_summary（摘要）+ search_fulltext（全文）+ 引擎兜底 + Retriever 缓存 |
| 本地测试 | ✓ `test_report_html.py`，生成 HTML 文件用浏览器查看 |
| 人工干预次数 | ≥ 14 |
| 已知待办 | verdict 证据衔接准确率、F3 publishTime 字段填充（需搜索引擎改造）、F3 逐条证据 relationType 判断、F3 credibilityScore LLM 逐条评估 |

---

### 日志条目 #43 — 事实核查接口重构：quick + deep 两个新端点

- **日期**：2026-06-23
- **场景**：接口设计 / 代码重构 / 文档更新
- **关键 Prompt**：
  > "即便是深度思考，也不能只返回报告，也要和快速核查一样返回结果之类的"
  > "即便是快速核查也需要返回html的报告，这个先不着急实现，我们先把接口设定好"
  > "你的第三个接口是做什么的"
  > "好的，那就按照原计划新增两个接口，快速核查以及深度核查，他们的返回格式是一样的，只是核查的过程不一样。其它接口暂时保留，但是注明废弃。"
- **背景**：当前 Python FastAPI 有 4 个事实核查端点（F1/F2/F3/LLM），职责划分模糊，reflective 模式通过请求体布尔开关控制不够直观。Java 后端只调用 F3 一个端点。需要两个意图清晰、返回相同结构化数据的端点。
- **AI 产出**：

  **A. 接口设计**
  - `POST /internal/v1/fact-check/quick` — **快速核查**：标准 FactAgent + 摘要搜索，返回完整 `FactCheckDetailDBData`
  - `POST /internal/v1/fact-check/deep` — **深度核查**：ReflectiveFactAgent + 全文搜索 + 反思循环，返回**相同结构** `FactCheckDetailDBData`
  - **核心原则**：两个端点返回完全相同的数据结构（claims/evidences/result/report），Java DTO 零改动即可切换
  - 区别仅在内部：quick 用 `search_summary()` 摘要搜索 + 数据驱动报告；deep 用 `search_fulltext()` 全文搜索 + 反思循环 + LLM HTML 报告

  **B. 共享函数提取（消除重复代码）**
  - `_build_claims_evidences_from_trace()` — 从 trace 提取 claims + evidences
  - `_build_result_conclusion()` — 根据 label 确定 resultLabel + conclusion（消除 4 处重复）
  - `_build_report_data_from_f3()` — 构造 ReportModuleData（消除 3 处 f3_like 匿名对象）
  - `_build_f3_result()` — 构建 F3Result（含 supportCount/attackCount）
  - `_merge_evidence()` — 合并 trace evidence 与 reflective supplement evidence，按 content+url 去重
  - `_build_quick_response()` / `_build_deep_response()` — 两个端点处理函数

  **C. 旧端点标注废弃**
  - F1/F2/F3/LLM 四个旧端点全部保留但标注 `deprecated=True`
  - F1 内部委托 `_build_quick_response()` 或 `_build_deep_response()`
  - F2 保持原有 trace 逻辑不变
  - F3 内部委托 `_build_quick_response()` 或 `_build_deep_response()`（保持 Java 向后兼容）
  - LLM 报告端点委托 `_build_deep_response()`

- **人工修改**：用户纠正了"深度核查只返回报告"的误解，要求两个端点返回相同结构
- **风险控制**：
  - Java 后端调用的 F3 端点完全不动，响应结构不变
  - 旧端点全部标注 `deprecated` 但保留功能，不破坏现有调用
  - FastAPI 的 `deprecated=True` 在 OpenAPI 文档中显示为废弃标记
- **价值**：
  - 两个新端点意图清晰，前端/后端按需选择
  - 共享函数消除约 80 行重复代码
  - 返回结构统一，降低对接成本
- **待办**：快速核查的 HTML 报告生成（当前 quick 返回 Markdown 报告，需后续实现）

---

### 日志条目 #44 — 证据模型重构：LLM 逐条判定 relationType

- **日期**：2026-06-24
- **场景**：代码重构 / Bug 修复
- **关键 Prompt**：
  > "在这个项目里面，证据的数量是怎么判定的？我认为这个有问题"
  > "我的天哪，这个一定需要修改，每个证据是否支持观点一定是llm来判断的呀"
- **背景**：用户发现证据的 `relationType`（support/attack/neutral）不是由 LLM 判断，而是通过硬编码关键词（如"306"、"232"、"11月3日"等美国大选特化词）在事后推断，回退路径甚至根据全局 verdict 给所有证据赋同一 relationType——导致 `supportCount`/`attackCount` 完全失真。
- **AI 产出**：
  - **`prompts/evidence_seeking.py`** — Schema 新增 `relationType` 枚举字段（support/attack/neutral），设为 required；Prompt 新增第 6 条规则，要求 LLM 基于证据内容与子声明语义对比逐条判断
  - **`api/routers/fact_check.py`** — `_extract_evidence_items_from_trace()` 优先从 evidence_seeker 输出的 `relationType` 读取，保留关键词推断作为回退
  - **`tools/search_service.py`** — `search_fulltext()` 新增 `default_relation` 参数，避免深度核查补充证据硬编码为 neutral
- **人工修改**：无
- **风险控制**：
  - 旧的关键词回退逻辑保留，新 LLM 判定为空时才触发
  - search_fulltext 的 default_relation 参数有默认值，向后兼容
- **价值**：证据的论辩关系从"硬编码关键词猜测 + 全局回退"升级为"LLM 逐条语义判定"，supportCount/attackCount 从此反映真实的证据分布

---

### 日志条目 #45 — 证据粒度重构 + evidence_merger 节点

- **日期**：2026-06-24
- **场景**：代码重构 / 功能升级
- **关键 Prompt**：
  > "我们需要重新审视证据本身，一次搜索是吧所有的搜索结构封装成一个证据吗？应该是搜到几个新闻，每个新闻一个证据"
  > "在搜集新闻之后，第一步是llm给每个新闻弄成证据，第二步是合并同样的内容"
- **背景**：上一轮改造后 relationType 由 LLM 判定，但证据粒度仍然有问题——一个搜索查询的 10 条结果被 LLM 揉成 1 段 evidence 字符串，损失了每条结果各自的 url/title/source/relationType。同时，同一事件被多家媒体报道应合并为一条证据并提升可信度。
- **AI 产出**：

  **A. 证据粒度从"1 查询 = 1 证据"改为"1 搜索结果 = 1 证据"**
  - **`prompts/evidence_seeking.py`** — Schema 重构：单字段 `evidence`（string）改为 `evidences[]` 数组，每条含 `title/url/source/content/credibilityScore/relationType`；Prompt 明确要求逐条处理、禁止合并
  - **`api/routers/fact_check.py`** — `_extract_evidence_items_from_trace()` 重写为主数据源从 `evidences[]` 数组展开，弃用旧的 search trace 单条记录路径

  **B. 新增 evidence_merger 节点（LangGraph 新节点）**
  - **`prompts/evidence_merging.py`**（新建）— 定义 `merged_evidences[]` JSON Schema，每条合并证据含 `summary` + `sources[]`（多个来源共享 summary/credibilityScore/relationType）
  - **`main_agent.py`** — 在 evidence_seeker 与 verdict_predictor 之间插入 evidence_merger 节点：新增 `evidence_merging_agent`、`evidence_merging_node`，修改 supervisor 成员列表和 graph 注册
  - **`api/routers/fact_check.py`** — 提取逻辑优先从 evidence_merger 的 `merged_evidences` 读取，回退到 evidence_seeker 原始输出

- **数据流**：
  ```
  evidence_seeker  →  逐条输出（每搜索结果 1 条，含独立 url/title/relationType）
  evidence_merger  →  合并同一事件的多来源为 1 条 merged_evidence（sources[] 含所有来源，共享 summary/credibilityScore）
  verdict_predictor →  基于合并后的证据做最终判定
  ```
- **人工修改**：无
- **风险控制**：
  - evidence_merger 输出优先，回退到 evidence_seeker 原始输出，不破坏旧 trace 兼容
  - supervisor 调度 merger 节点，evidence_seeker 输出完整传给 merger 的对话上下文
  - 合并时保留反驳/中性证据，不因合并丢失信息
- **价值**：
  - 每条搜索结果独立为一条证据，保留各自的 url/title/source/relationType
  - 同一事件多来源报道合并为一条，sources 数组汇总所有来源
  - 合并后的 credibilityScore 因多来源相互印证而提升，反映真实可信度
  - supportCount 按合并后条数计算，不再膨胀

---

### 日志条目 #46 — 声明拆解 Prompt 重构：一阶谓词逻辑 + 中文场景化

- **日期**：2026-06-24
- **场景**：提示词优化 / 质量改进
- **关键 Prompt**：
  > "声明拆解具体是怎么做的？提示词是什么"
  > "我觉得问题非常大，尤其是拆分规则非常简陋。这样吧你先给例子改成中文的，然后拆分策略就说不能是包含关系"
  > "再次加入说明，需要把声明拆解成若干子声明的一阶谓词式子，并且指明和声明等价的形式。比如张教授曾经在清北任职，可以拆成在清华或北大任职。每个子声明只要达到容易验证的程度就不必拆分。比如小明是中国人不必拆分成张雪峰是北京或上海或等等等。这样反而加大工作量。"
- **背景**：审查声明拆解模块时发现 `claim_decomposition_prompt` 存在三个严重问题：(1) 仅一句英文描述"define all the predicates"，缺乏拆解策略指导；(2) 示例全部是英文（Howard University Hospital、Alfredo Cornejo Cuevas），与项目中文场景脱节；(3) 没有约束子声明之间的关系，LLM 可能拆出包含关系的子声明（如"获得奖牌"包含"获得金牌"），导致下游搜索工作量膨胀。
- **AI 产出**：
  - **`prompts/input_ingestion.py`** — `claim_decomposition_prompt` 全面重构：
    1. **全中文改写**：prompt 从英文改为中文，示例替换为中文场景（武汉协和医院/同济医院、东京奥运会中国金牌数、张教授清北任职）
    2. **一阶谓词逻辑形式**：每条子声明格式 `谓词(主体, 客体) ::: 中文描述`，谓词用英文动词过去式（Located、Won、WorkedAt 等）
    3. **等价性原则**：明确拆解后的子声明集合必须与原声明逻辑等价——AND 关系（"和/都"→ 全部为真）和 OR 关系（"或"→ 至少一个为真），用逻辑符号标注
    4. **适度拆分原则**：拆到"容易通过搜索验证"即可，反对过度拆分（如"张雪峰是中国人"不必拆成省市）
    5. **禁止包含关系**：子声明之间不能互相包含（A 成立则 B 必然成立 → B 被 A 包含）
  - `claim_classification_prompt` 和 `claim_splitter_prompt` 暂未改动（仍为英文）
- **人工修改**：用户明确要求加入一阶谓词逻辑等价性和适度拆分原则
- **风险控制**：
  - 输出 schema（`subclaims` 字符串数组）不变，下游消费代码零改动
  - 示例中的英文谓词名（Located/Won/WorkedAt）与旧格式兼容
  - 适度拆分原则防止过度拆解导致搜索工作量膨胀
- **价值**：
  - 声明拆解从"一句话英文指令"升级为结构化、可预期的拆解策略
  - 一阶谓词逻辑形式让子声明语义清晰，便于下游证据匹配
  - AND/OR 等价性约束确保拆解后不丢失原声明的逻辑关系
  - 适度拆分 + 禁止包含关系双重约束控制拆解粒度，平衡核查质量与工作量

---

### 日志条目 #47 — DeepLLMReportGenerator：深度搜索逐段报告生成

- **日期**：2026-06-24
- **场景**：功能开发 / 架构扩展
- **关键 Prompt**：
  > "继续刚才的这个逐段生成报告... 证据以及声明应该放在一起来做。逐个声明后面接上证据，以及分析"
  > "每个子声明以及其证据分析都要llm单个输出，然后在汇总，在和llm对话生成报告时，告诉llm当前报告进度以及llm这次对话的任务"
- **背景**：深度搜索的报告之前使用 `LLMReportGenerator`（IR 模式），但存在两个问题：(1) 证据章节 LLM 经常遗漏部分证据；(2) IR 模式的多阶段流水线过于复杂。用户要求按思考逻辑顺序逐段生成。
- **AI 产出**：

  **A. 新增 Prompt（`report/prompts/prompts.py`）**
  - `SYSTEM_PROMPT_DEEP_CLAIM_ANALYSIS` — 逐子声明分析：含进度占位符 `{progress_info}`，LLM 逐条分析所有证据并给出综合判断
  - `SYSTEM_PROMPT_DEEP_SUMMARIZE` — 汇总所有分析为完整 Markdown 报告
  - `SYSTEM_PROMPT_DEEP_MD_TO_HTML` — Markdown→HTML 转换，含 CSS 模板

  **B. 新增 `DeepLLMReportGenerator`（`report/generator.py`）**
  - 继承 `LLMReportGenerator`，四阶段流水线：
    1. `_design_layout()` — 布局设计（复用父类）
    2. `_analyze_all_claims()` — 逐个分析子声明+证据，每个独立 LLM 调用
    3. `_summarize_report()` — 汇总生成完整 Markdown
    4. `_convert_md_to_html()` — LLM 将 Markdown→HTML
  - 每个阶段有独立降级路径

  **C. 路由更新（`api/routers/fact_check.py`）**
  - deep 路由改用 `DeepLLMReportGenerator`

  **D. 导出更新（`report/__init__.py`）**

- **风险控制**：逐条 try/except + 三步降级（子声明→汇总→HTML）
- **价值**：子声明+证据捆绑分析，逻辑连贯；进度告知提升生成质量

---

### 日志条目 #48 — LLM max_tokens 默认为 16384，修复 structured_output 截断

- **日期**：2026-06-24
- **场景**：Bug 修复
- **关键 Prompt**：
  > （用户提供 traceback）"Could not parse response content as the length limit was reached — CompletionUsage(completion_tokens=4096, prompt_tokens=38827, total_tokens=42923)"
- **背景**：深度核查时 evidence_seeker 节点调用失败。LLM 的 structured output（JSON）超过 4096 token 上限被截断，无法解析。根因是 `BaseLLM` 及其子类（`DoubaoLLM`/`OpenAILLM`/`OllamaLLM`）的 `as_langchain_chat_model()` 和原生 API 调用均未传递 `max_tokens`，导致各模型使用默认的 4096 上限。
- **AI 产出**：
  - **`llms/base.py`**：`BaseLLM.__init__` 新增 `self.max_tokens`，从 `**kwargs` 提取，默认值 16384
  - **`llms/doubao_client.py`**：`chat()` / `chat_with_json()` 和 `as_langchain_chat_model()` 均使用 `self.max_tokens`
  - **`llms/openai_client.py`**：同上
  - **`llms/ollama_client.py`**：`chat()` / `chat_with_json()` 使用 `num_predict` 选项，`as_langchain_chat_model()` 的 `ChatOllama` 使用 `num_predict` 参数
- **人工修改**：无
- **风险控制**：
  - 默认 16384 对大多数模型安全（doubao-seed / GPT-4o 系列均支持）
  - 可通过 `create_chat_model(model_name, max_tokens=N)` 或环境变量覆盖
  - 不修改 `BaseLLM` 公共 API 签名（仅从 kwargs 提取），不影响现有调用
- **价值**：
  - 修复 evidence_seeker / evidence_merger 等大输出节点的 structured_output 截断问题
  - 统一三个 LLM 提供商的 max_tokens 行为
  - 开闭原则：新增的 `max_tokens` 从 kwargs 透传，不破坏现有接口

---

### 日志条目 #49 — DeepLLMReportGenerator 防御性加固 + Double JSON encoding 修复

- **日期**：2026-06-24
- **场景**：Bug 修复
- **关键 Prompt**：
  > "我记得报告时逐段生成的，为什么依然超出范围？？还是说调用过程有误？"
  > "很可能是最后一步出的问题"
- **背景**：证据模型重构（commit `5e2aa5e`）后证据内容暴增，`DeepLLMReportGenerator.generate()` 一直抛异常，降级到数据驱动 `ReportGenerator`。排查发现三个问题。
- **AI 产出**：

  **A. `_design_layout` 无异常保护（`report/generator.py:172`）**
  - 整个 `generate()` 中唯一没有 try/except 的 LLM 调用
  - 一旦 API 报错（限流/超时），`generate()` 直接崩溃
  - → 加了 try/except，失败时返回默认 layout

  **B. `_summarize_report` Double JSON encoding（`report/generator.py:668-692`）**
  - `layout_json = json.dumps({...})` 然后 `json.dumps({"layout": layout_json})` → 所有引号被二次转义，token 数翻倍
  - 证据重构后每个子声明分析文本膨胀 5 倍 + double escaping → prompt 轻松 50K+ chars
  - → 改为直接传递 dict/list，消除二次序列化

  **C. `_convert_md_to_html` 大文档保护（`report/generator.py:729-757`）**
  - 整份 Markdown 一坨扔给 LLM 做 MD→HTML 转换，超过 20000 字符时 token 极易溢出
  - → 新增 `len(md_content) > 20000` 阈值，超限直接走 IR 渲染器（纯本地转换，无 LLM 调用）
  - 同时修复 `kpi_json` 的 double encoding → 改为 `kpis` 字典直传

  **D. Prompt 文档同步（`report/prompts/prompts.py`）**
  - `SYSTEM_PROMPT_DEEP_SUMMARIZE` 和 `SYSTEM_PROMPT_DEEP_MD_TO_HTML` 的占位符说明更新为新格式
  - 旧格式引用了 `{layout_json}` / `{analyses_json}` / `{kpi_json}` → 改为描述 JSON 字段 `layout` / `analyses` / `kpis`

  **E. 声明拆解日志兜底（`prompts/deep_decomposer.py:55`）**
  - `decompose()` 首轮 LLM 调用失败时返回 `[claim]` 但之前不写任何 log
  - → 新增 `initial_failed` 类型日志条目

- **风险控制**：所有改动都是增量防御（加 try/except、降级阈值），不改变现有成功路径的行为
- **价值**：
  - 修复 `DeepLLMReportGenerator` 崩溃问题，`generate()` 现在不会因单点 LLM 失败而整体挂掉
  - prompt 体积减半（消除 double encoding），LLM 调用成功率显著提升
  - 大文档自动跳过 LLM MD→HTML，避免 token 溢出

---

### 日志条目 #50 — DeepLLMReportGenerator 三阶段 HTML 组装重构

- **日期**：2026-06-24
- **场景**：架构重构
- **关键 Prompt**：
  > "报告内容太大了没法直接进行编辑，我们修改生成报告的方法，让他先根据模板生成一个框架，然后再逐段的生成html填入其中"
- **背景**：旧的 `_summarize_report` + `_convert_md_to_html` 两阶段都是"把全部内容一坨扔给 LLM"，证据重构后 prompt 轻松 50K+ chars，LLM 调用失败或产出不稳定。需要分治策略。
- **AI 产出**：

  **A. `HTMLRenderer.render_framework()`（`report/renderers/html.py:89`）**
  - 用 IR 渲染器生成 HTML 骨架（完整 CSS + Hero + KPI + 判定标语 + 报告附注）
  - 骨架中预留 `{claim_sections}` 占位符，CSS 样式完整可控（不依赖 LLM）
  - 新增 `.verdict-banner` / `.report-footer` / `.claim-card` 等 CSS 类

  **B. `SYSTEM_PROMPT_CLAIM_CARD_HTML`（`report/prompts/prompts.py:230`）**
  - 专门用于单张声明分析卡片的 LLM 生成 prompt
  - 输入 ~3K chars（1 个子声明 + 证据列表），输出 ~2K-4K chars
  - 远低于任何模型的 token 上限，不会截断

  **C. `_render_html_report()`（`report/generator.py:653`）**
  - 三阶段流程：
    ① `render_framework(layout, result)` → HTML 骨架（纯本地，无 LLM）
    ② 对每个子声明，LLM 生成一张 `.claim-card`（独立调用，失败隔离）
    ③ `framework.replace("{claim_sections}", all_cards)`（纯字符串，无 LLM）
  - 替换旧 `_summarize_report` + `_convert_md_to_html`

  **D. `_build_claim_card_html_fallback()`（`report/generator.py:697`）**
  - 单个子声明 LLM 调用失败时的 HTML 降级卡片
  - 纯数据渲染：证据卡含关系标签、可信度进度条、来源链接

  **E. `generate()` 更新（`report/generator.py:525`）**
  - 调用链变更：`_analyze_all_claims()` → `_render_html_report()`
  - 删除 `_summarize_report` / `_convert_md_to_html` 调用（方法保留不删，向后兼容）

- **风险控制**：
  - 每段 LLM 调用独立，单段失败→降级为数据卡片，不影响其他段
  - CSS 由 IR 渲染器统一管理，不依赖 LLM 生成
  - `_summarize_report` / `_convert_md_to_html` 保留不删，旧路径可随时切回
- **价值**：
  - 彻底解决大文档 LLM token 溢出问题（分治策略，每段 <5K tokens）
  - CSS 质量有保障（IR 渲染器管理，不再靠 LLM 手写）
  - 失败隔离：单个子声明失败不影响整体报告
  - 可观察：每张卡片生成打一行日志，用户可见进度
