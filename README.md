# QA Community · 带 RAG 与 Agent 的问答社区后端

基于 **FastAPI、MySQL 和 Redis** 的问答社区后端，在注册登录、问题发布、回答、采纳与点赞等业务之上，接入社区知识库检索和工具调用 Agent。

用户既可以通过 API 浏览与参与讨论，也可以向 AI 助手提问、检索社区资料、查询回答，并在人工确认后完成点赞。项目重点是将 AI 能力接入真实业务流程，同时保留服务端身份校验、缓存策略和写操作审批。

> 当前提供后端 API 与 Swagger 调试入口，尚未包含前端页面。Agent 点赞审批使用单进程内存状态，适合本地开发与单实例演示。

## 功能概览

| 模块 | 已实现能力 |
| --- | --- |
| 用户认证 | 注册、密码哈希、JWT Access/Refresh Token、刷新令牌轮换及重放检测 |
| 问答业务 | 发布与删除问题、问题详情、分页与热度排序、发布/删除回答、回答采纳 |
| 点赞 | 点赞与取消点赞；用户与回答组合的数据库唯一约束 |
| 缓存 | 问题/回答缓存、浏览量缓存与定时回写、检索结果缓存、受限的公开单轮答案缓存 |
| RAG | 中文向量检索、BM25 关键词召回、RRF 融合、Cross-Encoder 重排、来源信息组织 |
| Agent | 知识库检索、回答查询、天气、时间、网络地区查询与点赞工具 |
| Guardrails | 输入风险检测、输入包裹、工具资料隔离、凭据脱敏、点赞人工审批、轻量输出检查 |

社区 API 支持删除和取消点赞，但这些操作**没有暴露为 Agent 工具**。当前 Agent 唯一的业务写工具是 `like_answer`。

## 整体结构

```mermaid
flowchart TD
    Client[API 客户端 / Swagger] --> API[FastAPI]
    API --> Business[认证与问答业务]
    Business --> MySQL[(MySQL)]
    Business --> Redis[(Redis)]
    API --> Guard[输入风险检测与凭据脱敏]
    Guard --> Agent[LangChain Agent]
    Agent <--> LLM[OpenAI 兼容网关 / LiteLLM]
    Agent --> Read[只读工具]
    Read --> RAG[向量检索 + BM25 + 重排]
    RAG --> Chroma[(Chroma)]
    Agent --> HITL[点赞审批]
    HITL -->|批准| Like[绑定登录用户的点赞工具]
    Like --> MySQL
    Agent --> Output[输出检查]
    Output --> Client
    MySQL --> Sync[知识库增量同步]
    Sync --> Chroma
```

### RAG 检索流程

1. 优先检查归一化查询的精确缓存，命中则复用检索结果。
2. 向量召回最多 50 条候选。当前快路在首条相关性分数大于 `0.7` 时直接使用向量排序，跳过重排。
3. 慢路合并向量与 BM25 候选，通过 RRF 按排名融合并按内容指纹去重，保留最多 40 条进入重排。
4. 使用 Cross-Encoder 重排，最多保留 8 条，并过滤分数不高于 `0.05` 的结果。
5. 供模型使用的上下文默认取前 3 条，附带标题与 `qid`，方便引用来源和继续查询回答。

Embedding 使用 `BAAI/bge-small-zh-v1.5`，重排模型从本地 `models/bge-reranker/` 加载。阈值是当前实现参数，并非跨模型通用标准。

知识库以问题 ID 作为文档 ID，组合问题与优先采纳/高赞回答的内容，通过文本指纹识别新增、修改和删除，避免对未变化内容重复向量化。定时任务默认每 6 小时执行一次，启动后不会立即同步。

### 工具权限与人工审批

| 工具 | 用途 | 执行策略 |
| --- | --- | --- |
| `search_master` | 检索社区离线知识库 | 无需审批 |
| `get_answers` | 查询指定问题的回答 | 无需审批 |
| `get_weather` | 查询天气 | 无需审批 |
| `get_time` | 查询北京时间 | 无需审批 |
| `get_location` | 查询服务端网络出口所在地区 | 无需审批 |
| `like_answer` | 以当前登录用户身份点赞 | 必须批准 |

匿名用户没有点赞工具。登录用户触发点赞后，`HumanInTheLoopMiddleware` 暂停执行并返回待审批操作；批准后通过 `Command(resume=...)` 恢复，拒绝则跳过该写操作。用户 ID 由服务端闭包绑定，模型不能自行指定操作身份。

审批绑定用户与会话，只接受批准/拒绝，不允许客户端修改工具参数。审批记录有效期为 10 分钟，最多保留 128 条；同一记录原子取走，防止重复恢复。如果模型在同一批次同时提出只读工具和点赞，框架会暂停该批次，审批后继续。

### 防护与缓存边界

- 用户消息在模型视图中统一包裹并转义，历史不会重复保存包裹后的文本。正则检测用于识别风险，不作为授权依据。
- 工具返回资料作为不可信数据处理；包含疑似注入或敏感内容时隔离，过长时截断。
- 根据实际登录数据流处理 JWT、Bearer、明确标注的密码/token 及配置密钥；不对公开用户名、问题/回答 ID 做无关脱敏，也不声称覆盖全部 PII。
- 最终回答检查配置密钥、私钥头、堆栈和超长文本；检查通过后才发送。接口使用 SSE，但当前不是逐 token 输出。
- 检索缓存 TTL 为 30 分钟；答案缓存 TTL 为 10 分钟。答案缓存仅用于匿名、无历史、无风险的公开知识问题，且该轮实际只调用 `search_master`。
- 聊天历史 TTL 为 30 分钟，登录用户按用户 ID 与会话 ID 隔离。匿名会话 ID 应妥善保管。

## 技术栈

| 层次 | 主要技术 |
| --- | --- |
| Web 与校验 | FastAPI、Pydantic、Uvicorn |
| 数据与缓存 | SQLAlchemy、MySQL、PyMySQL、Redis |
| 认证 | python-jose、Passlib、bcrypt |
| Agent 编排 | LangChain、LangGraph、HumanInTheLoopMiddleware |
| 检索 | Chroma、Hugging Face Embeddings、sentence-transformers、jieba、rank-bm25 |
| 模型接入 | ChatOpenAI + OpenAI 兼容模型网关 |
| 测试 | pytest、HTTPX、隔离 SQLite |

## 本地运行

### 1. 准备环境与依赖

当前开发环境为 Python 3.12。先克隆仓库，在独立虚拟环境中安装依赖：

```bash
git clone https://github.com/jj-wang005/qa-community.git
cd qa-community
python -m venv .venv
```

Windows PowerShell 激活：`.venv\Scripts\Activate.ps1`；Linux/macOS 激活：`source .venv/bin/activate`。

以下为按源码整理的直接依赖参考；仓库尚未提供完整依赖锁定文件，未验证全新环境的一键安装。AI 编排与密码哈希相关版本采用当前开发环境版本：

```bash
python -m pip install fastapi uvicorn sqlalchemy pymysql redis pydantic-settings "python-jose[cryptography]" passlib "bcrypt==4.0.1" requests pytest httpx tzdata
python -m pip install "langchain==1.3.16" "langgraph==1.2.11" "langchain-core==1.6.0" "langchain-openai==1.6.0" "langchain-chroma==1.1.0" "langchain-huggingface==1.2.2" sentence-transformers rank-bm25 jieba
```

### 2. 配置服务与环境变量

准备 MySQL，并创建数据库，例如：

```sql
CREATE DATABASE qa_db CHARACTER SET utf8mb4;
```

Redis 当前在代码中配置为 `localhost:6379`、默认 DB 0；其他地址或认证方式需要修改 `app/core/redis_client.py`。同时准备支持工具调用的 OpenAI 兼容网关；现有开发配置使用 LiteLLM，由网关管理模型路由。

在项目根目录新建 `.env`，按自己的环境填写：

```dotenv
DATABASE_URL=mysql+pymysql://YOUR_USER:YOUR_PASSWORD@127.0.0.1:3306/qa_db?charset=utf8mb4
SECRET_KEY=REPLACE_WITH_A_RANDOM_SECRET
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7

LLM_GATEWAY_BASE_URL=http://127.0.0.1:4000
LLM_GATEWAY_MODEL=mimo-chat
LLM_GATEWAY_API_KEY=YOUR_GATEWAY_KEY
LITELLM_MASTER_KEY=YOUR_LITELLM_MASTER_KEY
DEEPSEEK_API_KEY=YOUR_DEEPSEEK_KEY
XIAOMI_MIMO_API_KEY=YOUR_MIMO_KEY

KB_REBUILD_INTERVAL_HOURS=6
```

以上均为占位值。当前配置类要求这些字段存在；Agent 实际调用使用 `LLM_GATEWAY_*`，模型名称应与网关中的可用名称一致。`.env` 与本地 `litellm_config.yaml` 不随仓库提交，克隆后需自行配置。密码包含 URL 特殊字符时，需要对数据库连接串中的密码进行 URL 编码。

### 3. 准备本地模型

应用导入 RAG 模块时即加载模型，且代码设置了 `HF_HUB_OFFLINE=1`。因此首次启动前需要：

- 将 `BAAI/bge-small-zh-v1.5` 下载到当前运行用户的 Hugging Face 缓存。
- 将 `BAAI/bge-reranker-base` 的完整模型文件准备到 `models/bge-reranker/`。

模型文件和 Chroma 数据不包含在 Git 仓库中。仅配置模型 API Key 不能替代本地检索模型。

### 4. 启动并准备知识库

从项目根目录运行：

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

启动时会创建尚不存在的数据库表。浏览器打开 [Swagger API 文档](http://127.0.0.1:8000/docs)，先注册、登录，通过接口添加问题和回答。

初次准备好数据后，在另一个终端执行增量同步：

```bash
python -c "from app.core.build_kb import sync_kb_incremental; print(sync_kb_incremental())"
```

同步会使 Chroma 中的文档与当前数据库对应，包括移除数据库中已删除问题的向量。初次同步后重启应用，使首次查询基于新数据构建 BM25 索引；不要在尚有待审批操作时重启。

当前必须使用单 worker。开发热重载或服务重启都会使内存中的待审批记录失效，用户需要重新发起操作。

## API 使用

除根路径外，业务接口统一使用 `/api/v1` 前缀。登录后在需要身份的请求中携带 `Authorization: Bearer <access_token>`。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | `/api/v1/auth/register` | 注册 |
| POST | `/api/v1/auth/login` | 获取访问与刷新令牌 |
| POST | `/api/v1/auth/refresh` | 刷新令牌 |
| GET / POST | `/api/v1/questions` | 分页查询 / 发布问题 |
| GET / DELETE | `/api/v1/questions/{id}` | 查看 / 删除问题 |
| GET / POST | `/api/v1/questions/{question_id}/answers` | 查询 / 发布回答 |
| POST | `/api/v1/answers/{answer_id}/accept` | 采纳回答 |
| DELETE | `/api/v1/answers/{answer_id}` | 删除回答 |
| POST / DELETE | `/api/v1/like/{answer_id}` | 点赞 / 取消点赞 |
| POST | `/api/v1/ai/chat` | AI 对话 |
| POST | `/api/v1/ai/approve` | 批准或拒绝 Agent 操作 |

### AI 对话与点赞审批

向 `/api/v1/ai/chat` 发送：

```json
{"question": "社区里关于 JWT 过期有哪些讨论？"}
```

后续对话传入响应返回的 `session_id`，其格式为 UUID。`question` 长度为 1～200 字符。

登录用户请求点赞时，例如 `{"question":"请给 ID 为 7 的回答点赞"}`，服务在实际写入前返回：

```text
event: approval_required
data: {"session_id":"<会话 UUID>","approval_id":"<审批 UUID>","expires_in":600,"actions":[{"name":"like_answer","args":{"answer_id":7},"allowed_decisions":["approve","reject"]}]}
```

检查回答 ID 后，以同一用户身份向 `/api/v1/ai/approve` 提交：

```json
{
  "session_id": "<替换为响应中的会话 UUID>",
  "approval_id": "<替换为响应中的审批 UUID>",
  "decisions": [{"type": "approve"}]
}
```

拒绝时将 `approve` 改为 `reject`。多条操作需按 `actions` 顺序逐一提供决定；恢复后若产生新审批事件，需要使用新的审批 ID。

普通回答使用 SSE `data` 字段，并返回 `[SESSION_ID]:...`。客户端应区分 `approval_required`、`error` 与普通正文，不能将“等待审批”显示为“点赞成功”。审批过期或已处理返回 410，身份/会话不匹配返回 404，决定数量或格式错误返回 422。获批后请求中断时，应先查询点赞状态，避免盲目重复发起。

## 测试

### 离线 Guardrails 与审批回归

在依赖和配置齐备的环境中执行：

```bash
python -m pytest --noconftest -p no:cacheprovider tests/test_guardrails.py tests/test_agent_guardrail.py tests/test_ai_guardrails.py -q
```

这些测试使用真实 Agent 图配合假模型与内存缓存，并用隔离 SQLite 验证真实点赞工具，不调用外部模型、不写开发 MySQL，也不连接开发 Redis。覆盖输入包裹、资料隔离、凭据处理、审批暂停/恢复、拒绝、身份隔离、过期、重复/并发领取及点赞后的缓存失效。

### 业务集成测试

```bash
python -m pytest -q
```

全量测试需要 MySQL、Redis 和本地模型等环境。`tests/conftest.py` 会重建 `qa_db_test` 中的表，并清空 Redis DB 15；请使用独立测试服务，确保这些位置没有需要保留的数据。离线回归通过不代表全量集成测试或真实模型链路均已验证。

## 目录结构

```text
qa-community/
├── README.md
├── .gitignore
├── pytest.ini
├── app/
│   ├── main.py                 # 应用入口、路由注册与后台任务
│   ├── routers/
│   │   ├── auth.py             # 注册、登录与令牌刷新
│   │   ├── questions.py        # 问题发布、查询与删除
│   │   ├── answers.py          # 回答发布、查询、采纳与删除
│   │   ├── like.py             # 社区点赞与取消点赞接口
│   │   └── ai.py               # AI 对话与审批恢复接口
│   ├── schemas/
│   │   ├── user.py             # 用户与认证数据结构
│   │   ├── questions.py        # 问题请求、响应与排序选项
│   │   ├── answers.py          # 回答请求、响应与排序选项
│   │   └── ai.py               # 对话与审批请求校验
│   ├── models/
│   │   ├── user.py             # 用户表
│   │   ├── question.py         # 问题表
│   │   ├── answer.py           # 回答表
│   │   └── like.py             # 点赞表与唯一约束
│   ├── db/
│   │   └── base.py             # ORM 基类、数据库引擎与会话
│   └── core/
│       ├── config.py           # 环境配置
│       ├── deps.py             # 登录身份依赖
│       ├── security.py         # 密码与 JWT
│       ├── exceptions.py       # 统一异常处理
│       ├── paginate.py         # 分页辅助
│       ├── redis_client.py     # Redis 连接
│       ├── rag.py              # 检索、融合、重排与上下文组织
│       ├── build_kb.py         # 知识库构建与增量同步
│       ├── kb_sync.py          # 定时知识库同步
│       ├── tools.py            # Agent 读工具与绑定身份的点赞工具
│       ├── guardrails.py       # 输入、资料与输出防护
│       └── approvals.py        # 待审批记录及一次性领取
└── tests/
    ├── conftest.py             # 业务测试夹具与服务隔离
    ├── test_auth.py            # 认证测试
    ├── test_questions.py       # 问题测试
    ├── test_answers.py         # 回答测试
    ├── test_like.py            # 点赞测试
    ├── test_ai_tools.py        # 工具行为测试
    ├── test_guardrails.py      # 输入风险检测与包裹测试
    ├── test_agent_guardrail.py # 模型边界防护测试
    └── test_ai_guardrails.py   # 对话、缓存与审批闭环测试
```

目录树展开主要源码与测试文件，省略各包的 `__init__.py`。模型、向量库、环境配置、缓存与个人资料不列入源码目录树，也不随仓库发布。

## 当前限制与后续方向

- **审批持久化**：当前仅支持单进程，尚不支持跨进程或重启恢复。
- **知识库新鲜度**：同步后尚未自动重建已加载的 BM25 索引，也未统一失效检索/答案缓存，更新结果可能延迟可见；缓存版本管理仍待完善。
- **多轮检索**：聊天保留历史，但尚未增加独立的多轮查询改写步骤。
- **输出体验**：当前完整检查后发送，尚未实现安全的逐 token 流式输出。
- **复现与展示**：待补充依赖锁定、前端审批交互和可公开复现的评测材料。

当前保留精确查询缓存，未启用语义相似答案复用。混合检索和重排是已实现的检索路径，但其效果需要结合具体数据集评测，不在此声明未经公开复现的性能或召回提升。
