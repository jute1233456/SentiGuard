# SentiGuard 内部接口文档

> 本文档描述 **Spring Boot 后端 ↔ Python FastAPI 智能体服务** 之间的接口规范。
> 所有接口仅在内网暴露，前缀 `/internal/v1`。

---

## 0. 通用约定

### 0.1 通信方式
- 协议：HTTP/1.1
- 数据格式：JSON（`Content-Type: application/json; charset=utf-8`）
- 调用方：Spring Boot
- 提供方：FastAPI（Python 多智能体服务）

### 0.2 通用请求头

| Header | 必填 | 说明 |
|--------|------|------|
| `Content-Type` | 是 | 固定 `application/json` |
| `X-Internal-Token` | 是 | 服务间共享密钥，用于鉴权，防止内网被绕 |
| `X-Trace-Id` | 否 | 链路追踪 ID（UUID），FastAPI 透传到日志 |

### 0.3 统一响应体

成功：
```json
{
  "code": 0,
  "message": "ok",
  "data": { }
}
```

失败：
```json
{
  "code": 50001,
  "message": "topic modeling failed",
  "data": null
}
```

### 0.4 通用错误码

| code  | HTTP | 含义 |
|-------|------|------|
| 0     | 200  | 成功 |
| 40001 | 400  | 参数校验失败 |
| 40101 | 401  | `X-Internal-Token` 无效 |
| 50001 | 500  | 内部错误 |
| 50301 | 503  | 上游依赖（LLM / 数据库 / 检索）不可用 |

---

## 1. 接口清单

| 编号 | 方法 | 路径 | 用途 | 状态 |
|------|------|------|------|------|
| H1   | GET  | `/internal/v1/hotspots`    | 获取热点列表（按热度排序） | 已定义 |
| F1   | POST | `/internal/v1/fact-check`  | 事实核查（简易版，只返回结论与解释） | 已定义 |
| F2   | POST | `/internal/v1/fact-check/detail` | 事实核查（详细版，含推理过程与证据链） | 已定义 |

---

## H1. 获取热点列表

### 基本信息
- **方法**：`GET`
- **路径**：`/internal/v1/hotspots`
- **用途**：返回按热度倒序排好的热点数组，供 Spring Boot 后端调用展示
- **幂等性**：是（同样参数返回同样的当前快照）

### 请求

#### 请求头
```
X-Internal-Token: <服务间共享密钥>
X-Trace-Id: <uuid>            （可选）
```

#### 查询参数（Query String）

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `limit` | int | 否 | 20 | 返回热点数量上限，取值范围 1~100 |
| `from`  | string (ISO8601) | 否 | 当前时间 - 24h | 时间窗口起点，UTC |
| `to`    | string (ISO8601) | 否 | 当前时间 | 时间窗口终点，UTC |
| `topK`  | int | 否 | 5 | 每个热点返回前 K 个关键词，取值范围 1~20 |

#### 请求示例

```http
GET /internal/v1/hotspots?limit=10&topK=5 HTTP/1.1
Host: fastapi.internal:8000
X-Internal-Token: shared-secret-xxx
X-Trace-Id: 7c6d3e1a-2b9f-4a5c-9d11-e7f0a1b2c3d4
```

### 响应

#### HTTP 状态码
- `200 OK`：成功
- `400 Bad Request`：参数错误
- `401 Unauthorized`：token 无效
- `500 / 503`：服务异常

#### 响应体

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "generatedAt": "2026-06-16T10:00:00Z",
    "windowFrom":  "2026-06-15T10:00:00Z",
    "windowTo":    "2026-06-16T10:00:00Z",
    "hotspots": [
      {
        "rank": 1,
        "name": "某某事件",
        "heat": 87.4,
        "keywords": [
          { "word": "事件", "weight": 0.42 },
          { "word": "官方", "weight": 0.31 },
          { "word": "通报", "weight": 0.27 },
          { "word": "调查", "weight": 0.21 },
          { "word": "回应", "weight": 0.18 }
        ],
        "sentiment": {
          "label": "neg",
          "score": -0.62,
          "distribution": { "pos": 0.15, "neg": 0.70, "neu": 0.15 }
        }
      },
      {
        "rank": 2,
        "name": "另一个热点",
        "heat": 72.1,
        "keywords": [
          { "word": "政策", "weight": 0.38 },
          { "word": "改革", "weight": 0.29 },
          { "word": "试点", "weight": 0.22 }
        ],
        "sentiment": {
          "label": "neu",
          "score": 0.05,
          "distribution": { "pos": 0.30, "neg": 0.25, "neu": 0.45 }
        }
      }
    ]
  }
}
```

### 字段说明

#### data 顶层

| 字段 | 类型 | 说明 |
|------|------|------|
| `generatedAt` | string (ISO8601) | 本次结果生成的时间戳，UTC |
| `windowFrom`  | string (ISO8601) | 实际使用的时间窗口起点（与请求参数 `from` 一致或采用默认值） |
| `windowTo`    | string (ISO8601) | 实际使用的时间窗口终点 |
| `hotspots`    | array  | 热点数组，**已按 `heat` 倒序排好**；长度 ≤ `limit` |

#### hotspots[] 单个热点

| 字段 | 类型 | 说明 |
|------|------|------|
| `rank` | int | 排名，从 1 开始 |
| `name` | string | 热点名称，由 BERTopic 代表性关键词或 LLM 概括生成 |
| `heat` | float | 热度值，范围 0~100，越大越热 |
| `keywords` | array | 主题关键词数组，**已按 weight 倒序排好**，长度 ≤ `topK` |
| `sentiment` | object | 整体情感分析结果 |

#### keywords[] 单个关键词

| 字段 | 类型 | 说明 |
|------|------|------|
| `word`   | string | 关键词文本 |
| `weight` | float  | 关键词权重，来自 BERTopic c-TF-IDF 分数，范围 0~1 |

#### sentiment 情感对象

| 字段 | 类型 | 说明 |
|------|------|------|
| `label` | string enum | 整体情感标签：`pos` / `neg` / `neu` |
| `score` | float | 情感强度，范围 -1.0 ~ +1.0（-1 极负面，+1 极正面） |
| `distribution` | object | 三类情感占比，`pos + neg + neu = 1.0` |
| `distribution.pos` | float | 正面比例，范围 0~1 |
| `distribution.neg` | float | 负面比例，范围 0~1 |
| `distribution.neu` | float | 中性比例，范围 0~1 |

### 错误码（本接口）

| code  | HTTP | 含义 |
|-------|------|------|
| 0     | 200  | 成功 |
| 40001 | 400  | 参数非法（如 `limit` 超 100、时间格式错误、`from` 晚于 `to`） |
| 40101 | 401  | `X-Internal-Token` 无效 |
| 50001 | 500  | BERTopic 拟合失败 / 情感分析失败等内部错误 |
| 50301 | 503  | 数据库或下游服务不可用 |

#### 错误响应示例

```json
{
  "code": 40001,
  "message": "limit must be between 1 and 100",
  "data": null
}
```

### Java 端调用示例

```java
// Spring Boot 端使用 RestTemplate 调用示例
String url = "http://fastapi.internal:8000/internal/v1/hotspots?limit=10&topK=5";

HttpHeaders headers = new HttpHeaders();
headers.set("X-Internal-Token", internalToken);
headers.set("X-Trace-Id", UUID.randomUUID().toString());

ResponseEntity<HotspotResponse> resp = restTemplate.exchange(
    url, HttpMethod.GET, new HttpEntity<>(headers), HotspotResponse.class);

List<Hotspot> hotspots = resp.getBody().getData().getHotspots();
```

#### 对应 DTO

```java
public class HotspotResponse {
    private int code;
    private String message;
    private HotspotData data;
}

public class HotspotData {
    private String generatedAt;
    private String windowFrom;
    private String windowTo;
    private List<Hotspot> hotspots;
}

public class Hotspot {
    private int rank;
    private String name;
    private double heat;
    private List<Keyword> keywords;
    private Sentiment sentiment;
}

public class Keyword {
    private String word;
    private double weight;
}

public class Sentiment {
    private String label;            // pos | neg | neu
    private double score;            // -1.0 ~ +1.0
    private Distribution distribution;
}

public class Distribution {
    private double pos;
    private double neg;
    private double neu;
}
```

### 设计说明

1. **GET 而非 POST**
   该接口为只读查询，不改变 FastAPI 端状态，符合 GET 语义；同时方便缓存与浏览器/调试工具直接访问。

2. **关键词为何采用 `[{word, weight}]` 结构**
   - 带权重便于前端实现词云、热力条等可视化
   - 不需要权重时可忽略，仍可作为字符串数组使用
   - 多一个 float 字段成本极低

3. **`heat` 取值口径**
   当前定义为 0~100 的归一化数值。具体计算口径（新闻条数、时间衰减、来源权重等）由算法侧确定，本接口约束输出范围。

4. **`name` 生成策略**
   - 一期：取前 1~2 个关键词拼接
   - 二期：调用 LLM 基于关键词 + 代表性标题生成更可读的短语

5. **时间窗口**
   FastAPI 端基于 `from` / `to` 参数对 GDELT 新闻数据切片，再做 BERTopic 主题建模。请求未指定时使用默认值并在响应中通过 `windowFrom` / `windowTo` 回显，便于 Java 端核对。

---

## F1. 事实核查（简易版）

### 基本信息
- **方法**：`POST`
- **路径**：`/internal/v1/fact-check`
- **用途**：Java 后端提交一段需要核实的内容，FastAPI 通过多智能体流程完成核查后，**一次性返回结论与解释**
- **同步/异步**：同步
- **幂等性**：否（每次调用都会触发一次完整的智能体推理）

> **简易版说明**：本版本仅返回三个字段 —— `isTrue`（真假，布尔）、`conclusion`（结论）、`explanation`（解释），
> 不包含证据列表、子声明拆解、元信息等扩展内容。后续如需详细信息，可在保持向后兼容的前提下扩展响应体。

### 请求

#### 请求头
```
Content-Type: application/json
X-Internal-Token: <服务间共享密钥>
X-Trace-Id: <uuid>            （可选）
```

#### 请求体

```json
{
  "claim": "2024年巴黎奥运会是第33届夏季奥林匹克运动会。"
}
```

#### 字段说明（请求）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `claim` | string | 是 | 待核查的声明，长度 1~2000 字 |

### 响应

#### HTTP 状态码
- `200 OK`：核查完成（无论结论为何）
- `400 Bad Request`：参数错误
- `408 Request Timeout`：核查超时
- `503 Service Unavailable`：下游 LLM 不可用

#### 响应体

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "isTrue": true,
    "conclusion": "声明真实：2024 年巴黎奥运会确为第 33 届夏季奥林匹克运动会。",
    "explanation": "国际奥委会官网与新华社等权威媒体均明确指出 2024 巴黎奥运会为第 33 届夏季奥林匹克运动会。综合多方信息相互印证，未发现反驳证据，因此判定该声明为真实。"
  }
}
```

#### 字段说明（响应）

##### data 顶层

| 字段 | 类型 | 说明 |
|------|------|------|
| `isTrue` | boolean | 真假判定结果。`true` 表示声明为真，`false` 表示声明为假 |
| `conclusion` | string | 结论，一句话总结判定结果，可直接展示给前端用户 |
| `explanation` | string | 自然语言解释，说明判定依据，可直接展示给前端用户 |

> **关于不确定情况**
> 当前简易版只用一个布尔表达真假，对于"部分真实""证据不足"等情况，
> 服务端会归并为最接近的布尔值（趋向真则 `true`，趋向假则 `false`），
> 并在 `conclusion` / `explanation` 中通过文字描述补充细节。
> 后续若需要更精细的标签，可扩展为 `label` 枚举字段。

### 错误码（本接口）

| code  | HTTP | 含义 |
|-------|------|------|
| 0     | 200  | 成功（包括"证据不足但归并为布尔结果"的情况） |
| 40001 | 400  | 参数非法（如 claim 为空 / 超长） |
| 40101 | 401  | `X-Internal-Token` 无效 |
| 42201 | 422  | claim 内容不合法（如检测到提示词注入） |
| 40801 | 408  | 核查超时（默认上限 120s） |
| 50001 | 500  | 智能体内部错误 |
| 50301 | 503  | 下游 LLM 服务不可用 |

#### 错误响应示例

```json
{
  "code": 40001,
  "message": "claim must not be empty",
  "data": null
}
```

### Java 端调用示例

```java
// 请求体
Map<String, Object> body = Map.of(
    "claim", "2024年巴黎奥运会是第33届夏季奥林匹克运动会。"
);

HttpHeaders headers = new HttpHeaders();
headers.setContentType(MediaType.APPLICATION_JSON);
headers.set("X-Internal-Token", internalToken);
headers.set("X-Trace-Id", UUID.randomUUID().toString());

ResponseEntity<FactCheckResponse> resp = restTemplate.exchange(
    "http://fastapi.internal:8000/internal/v1/fact-check",
    HttpMethod.POST,
    new HttpEntity<>(body, headers),
    FactCheckResponse.class
);

FactCheckData data = resp.getBody().getData();
boolean isTrue = data.isTrue();              // 真假判定
String conclusion = data.getConclusion();    // 一句话结论
String explanation = data.getExplanation();  // 详细解释
```

#### 对应 DTO

```java
public class FactCheckResponse {
    private int code;
    private String message;
    private FactCheckData data;
}

public class FactCheckData {
    private boolean isTrue;       // 真假判定
    private String conclusion;    // 一句话结论
    private String explanation;   // 详细解释
}
```

### 设计说明

1. **简易版的范围**
   仅返回真假（`isTrue`）+ 结论（`conclusion`）+ 解释（`explanation`）三个字段。
   适用于前端只需要展示"判定结果 + 一段说明"的场景，开发与对接成本最低。

2. **布尔字段的取舍**
   实际核查可能产生"部分真实""证据不足"等中间态，本版本统一归并为最接近的布尔值，
   细节通过文字描述放在 `conclusion` 与 `explanation` 中表达。
   后续若需要枚举级标签，可在 `data` 中追加 `label` 字段，保持向后兼容。

3. **同步模式的代价**
   FactAgent 一次完整核查耗时通常 10~120s。Java 端 HTTP 客户端的 read timeout 必须设置 ≥ 150s，否则会过早断开连接。

4. **超时处理**
   FastAPI 端内置 120s 软超时，超时即返回 `408`，避免请求长时间挂起。

5. **未来扩展**
   后续若需要返回置信度 / 证据 / 子声明 / 元信息，可在 `data` 下追加字段（`confidence`、`evidence`、`subclaims`、`meta` 等），保持向后兼容；
   也可单独提供 `POST /internal/v1/fact-check/async` 异步版本用于超长任务。

---

## F2. 事实核查（详细版，含推理过程与证据链）

### 基本信息
- **方法**：`POST`
- **路径**：`/internal/v1/fact-check/detail`
- **用途**：在 F1 的 `isTrue` + `conclusion` + `explanation` 基础上，额外返回完整的推理路径（trace）和展平证据列表
- **同步/异步**：同步
- **幂等性**：否

### 请求

#### 请求头
```
Content-Type: application/json
X-Internal-Token: <服务间共享密钥>
X-Trace-Id: <uuid>            （可选）
```

#### 请求体

```json
{
  "claim": "2024年巴黎奥运会是第33届夏季奥林匹克运动会。"
}
```

#### 字段说明（请求）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `claim` | string | 是 | 待核查的声明，长度 1~2000 字 |

### 响应

#### HTTP 状态码
- `200 OK`：核查完成
- `400 Bad Request`：参数错误
- `401 Unauthorized`：token 无效
- `408 Request Timeout`：核查超时
- `503 Service Unavailable`：下游 LLM 不可用

#### 响应体

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "isTrue": true,
    "conclusion": "声明真实：多个权威来源相互印证。",
    "explanation": "国际奥委会官网与新华社等权威媒体均明确指出...",
    "trace": {
      "runId": "20260621_214615_a1ec",
      "claim": "2024年巴黎奥运会是第33届夏季奥林匹克运动会。",
      "route": [
        { "graph": "main", "next": "input_ingestor" },
        { "graph": "ingestion", "next": "claim_splitter" },
        { "graph": "ingestion", "next": "claim_classification" },
        { "graph": "ingestion", "next": "FINISH" },
        { "graph": "main", "next": "query_generator" },
        { "graph": "main", "next": "evidence_seeker" },
        { "graph": "main", "next": "verdict_predictor" },
        { "graph": "main", "next": "FINISH" }
      ],
      "steps": [
        {
          "node": "claim_splitter",
          "output": { "subclaims": ["2024年巴黎奥运会是第33届夏季奥林匹克运动会"] }
        },
        {
          "node": "query_generator",
          "output": {
            "subclaim_with_questions": [
              {
                "subclaim": "2024年巴黎奥运会是第33届夏季奥林匹克运动会",
                "questions": ["2024年巴黎奥运会是第几届？", ...]
              }
            ]
          }
        },
        {
          "node": "evidence_seeker",
          "output": {
            "subclaims_with_query_evidence": [
              {
                "subclaim": "...",
                "queries_with_evidence": [
                  { "query": "...", "evidence": "..." }
                ]
              }
            ]
          }
        },
        {
          "node": "verdict_predictor",
          "output": {
            "result": { "label": "supported", "explanation": "..." }
          }
        }
      ],
      "searches": [
        {
          "subclaim": "",
          "query": "2024年巴黎奥运会 第几届？",
          "chosenUrl": "https://olympics.com/zh/olympic-games/paris-2024",
          "evidenceSnippet": "2024年巴黎奥运会是第33届夏季奥林匹克运动会..."
        }
      ],
      "verdict": {
        "label": "supported",
        "explanation": "国际奥委会官网确认..."
      }
    },
    "evidenceItems": [
      {
        "subclaim": "2024年巴黎奥运会是第33届夏季奥林匹克运动会",
        "query": "2024年巴黎奥运会 第几届？",
        "chosenUrl": "https://olympics.com/zh/olympic-games/paris-2024",
        "evidenceSnippet": "2024年巴黎奥运会是第33届夏季奥林匹克运动会..."
      }
    ]
  }
}
```

#### 字段说明（响应）

##### data 顶层

| 字段 | 类型 | 说明 |
|------|------|------|
| `isTrue` | boolean | 真假判定 |
| `conclusion` | string | 一句话结论 |
| `explanation` | string | 详细解释 |
| `trace` | object | 完整推理路径（见下） |
| `evidenceItems` | array | 展平证据列表，每条含子声明上下文 |

##### trace 对象

| 字段 | 类型 | 说明 |
|------|------|------|
| `runId` | string | 本次 trace 运行唯一 ID |
| `claim` | string | 原始声明文本 |
| `route` | array | Supervisor 路由序列：`{graph, next}` |
| `steps` | array | 各智能体节点的结构化输出：`{node, output}` |
| `searches` | array | 搜索引擎调用记录，每项同 `EvidenceItem` 结构 |
| `verdict` | object | 最终判定：`{label, explanation}` |

##### evidenceItems[] 单条证据

| 字段 | 类型 | 说明 |
|------|------|------|
| `subclaim` | string | 该证据对应的子声明 |
| `query` | string | 搜索引擎使用的查询语句 |
| `chosenUrl` | string | 选中作为证据来源的 URL |
| `evidenceSnippet` | string | 从该 URL 抽取的与查询相关的摘要 |

### 与 F1 的关系

- F2 是 F1 的超集：`isTrue` / `conclusion` / `explanation` 三字段完全一致
- Java 端可按需选择：
  - 只需结论 → 调 F1（更快，响应体更小）
  - 需要展示推理过程 / 证据来源 → 调 F2
- F1 和 F2 共享同一个 `FactCheckRequest` 请求体

### Java 端调用示例

```java
// 请求体与 F1 完全一致
Map<String, Object> body = Map.of(
    "claim", "2024年巴黎奥运会是第33届夏季奥林匹克运动会。"
);

HttpHeaders headers = new HttpHeaders();
headers.setContentType(MediaType.APPLICATION_JSON);
headers.set("X-Internal-Token", internalToken);

ResponseEntity<FactCheckDetailResponse> resp = restTemplate.exchange(
    "http://fastapi.internal:8000/internal/v1/fact-check/detail",
    HttpMethod.POST,
    new HttpEntity<>(body, headers),
    FactCheckDetailResponse.class
);

FactCheckDetailData data = resp.getBody().getData();
boolean isTrue = data.isTrue();
List<EvidenceItem> evidence = data.getEvidenceItems();
List<TraceStep> steps = data.getTrace().getSteps();
```

#### 对应 DTO

```java
public class FactCheckDetailResponse {
    private int code;
    private String message;
    private FactCheckDetailData data;
}

public class FactCheckDetailData {
    private boolean isTrue;
    private String conclusion;
    private String explanation;
    private FactCheckTrace trace;
    private List<EvidenceItem> evidenceItems;
}

public class FactCheckTrace {
    private String runId;
    private String claim;
    private List<TraceRoute> route;
    private List<TraceStep> steps;
    private List<EvidenceItem> searches;
    private Verdict verdict;
}

public class TraceRoute {
    private String graph;
    private String next;
}

public class TraceStep {
    private String node;
    private Object output;
}

public class EvidenceItem {
    private String subclaim;
    private String query;
    private String chosenUrl;
    private String evidenceSnippet;
}

public class Verdict {
    private String label;
    private String explanation;
}
```

### 设计说明

1. **F2 是 F1 的超集**，两者共享请求体 `FactCheckRequest`，Java 端只改 URL 和 DTO 即可升级
2. **trace.steps 保留原始结构化输出**，不做二次加工，方便前端按需渲染
3. **evidenceItems 是展平视图**，将 search 事件与 evidence_seeker 的 subclaim 映射拼接，便于直接展示"哪条证据支撑哪个子声明"
4. **trace.route** 记录 supervisor 路由序列，可用于可视化智能体调用链路
5. **verdict** 放在 trace 内，与 steps / searches 平级，保持事件完整性

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-06-16 | 0.1.0 | 初稿，定义热点列表接口 H1 |
| 2026-06-16 | 0.2.0 | 新增事实核查接口 F1（简易版，仅返回结论与解释） |
| 2026-06-16 | 0.2.1 | F1 响应体精简为 `isTrue`(布尔) + `conclusion` + `explanation` 三字段 |
| 2026-06-21 | 0.3.0 | 新增 F2 POST `/internal/v1/fact-check/detail`（详细版，含推理过程与证据链） |
