# 智能会议助手初始实施计划

> **面向执行者：** 按任务逐项实施，并使用复选框记录进度。行为变更遵循测试驱动开发：先确认测试按预期失败，再编写生产代码。

**目标：** 构建一个本地可运行、测试优先的智能会议助手，通过受控 LangGraph 工作流和模拟日历、会议室 API 创建、查询和修改会议。

**架构：** FastAPI 提供聊天及模拟集成端点。类型化 LangGraph 工作流使用可注入的自然语言解释器、不可变会话状态、确定性策略检查、会议仓库工具和写入前明确确认。

**技术栈：** Python 3.12、FastAPI、LangGraph、LangChain Core/OpenAI 适配器、Pydantic v2、SQLite、httpx、pytest、pytest-cov、Ruff。

## 全局约束

- 默认时区固定为 `Asia/Shanghai`，测试使用可注入的固定时钟；
- 核心语句和分支覆盖率至少为 80%；
- 生产代码只在对应测试按预期失败后编写；
- 状态和领域更新返回新值，不修改已有模型或集合；
- 模型只解释语言，身份、授权、确认和写入由确定性代码控制；
- 不提供删除、批量修改、任意 SQL 或任意 HTTP 工具；
- 创建和更新必须经过预览及明确确认，被拒绝请求不得产生写入；
- `demo` 模式无需 API key，真实模型通过环境变量启用。

---

### 任务 1：项目基础、领域模型、仓库和策略

**文件：**
- 创建：`pyproject.toml`、`.gitignore`、`.env.example`；
- 创建：`app/config.py`、`app/domain/models.py`、`app/domain/errors.py`、`app/domain/policies.py`；
- 创建：`app/repositories/meetings.py`、`app/repositories/schema.sql`、`app/repositories/seed.py`；
- 测试：`tests/unit/test_models.py`、`tests/unit/test_policies.py`、`tests/integration/test_repository.py`。

**产出接口：**
- 不可变 Pydantic 模型 `MeetingDraft`、`MeetingPatch`、`Meeting`、`Actor`、`PendingAction`、`ConversationState`；
- `MeetingRepository.list_for_actor/find_visible/create/update`，使用参数化 SQLite 和乐观版本检查；
- 纯策略函数 `validate_draft`、`authorize_query`、`authorize_update`、`classify_unsafe_request` 和确认哈希。

- [ ] 编写模型、策略和仓库失败测试；
- [ ] 确认失败原因是缺少生产模块或行为；
- [ ] 实现最小领域模型、schema、仓库和策略；
- [ ] 运行定向测试并在全绿状态下整理代码。

### 任务 2：空闲时间、会议室推荐、模拟 API 和类型化客户端

**文件：**
- 创建：`app/domain/availability.py`、`app/domain/room_ranking.py`；
- 创建：`app/integrations/models.py`、`app/integrations/calendar_client.py`、`app/integrations/room_client.py`；
- 创建：`app/api/mock_integrations.py`、`app/api/dependencies.py`；
- 测试：`tests/unit/test_availability.py`、`tests/unit/test_room_ranking.py`、`tests/integration/test_mock_integrations.py`。

**产出接口：**
- `find_common_free_slots(busy_by_user, window_start, window_end, duration_minutes)`；
- 确定性的 `rank_rooms(rooms, topic, attendee_count, required_features)`；
- `POST /mock/calendar/freebusy` 和 `POST /mock/rooms/search`；
- 校验完整响应并转换受控集成错误的 HTTP client。

- [ ] 编写时间区间、会议室排序、端点契约和异常响应测试；
- [ ] 确认测试因缺少目标行为而失败；
- [ ] 实现算法、固定数据、端点和类型化 client；
- [ ] 运行定向测试并保持行为不变地整理代码。

### 任务 3：意图解释器和受控 LangGraph 工作流

**文件：**
- 创建：`app/agent/interpreter.py`、`app/agent/demo_interpreter.py`、`app/agent/llm_interpreter.py`；
- 创建：`app/agent/state.py`、`app/agent/service.py`、`app/agent/graph.py`、`app/agent/tools.py`；
- 测试：`tests/unit/test_demo_interpreter.py`、`tests/unit/test_state.py`、`tests/integration/test_agent_workflow.py`。

**产出接口：**
- 结构化 `MeetingCommand` 和部分 `MeetingPatch`；
- `MeetingAssistant.handle(ChatContext, message) -> AssistantReply`；
- 状态 `collecting|needs_clarification|needs_confirmation|done|rejected`；
- 有界节点：安全预检、解释、状态归并与目标解析、校验、集成查询、预览、确认和执行。

- [ ] 编写不完整创建、多轮补充、查询、修改、确认、状态隔离和危险请求测试；
- [ ] 确认测试因缺少工作流行为而失败；
- [ ] 实现解释器、不可变 reducer、工具和固定图；
- [ ] 运行工作流测试并控制节点复杂度。

### 任务 4：FastAPI 聊天接口和最小浏览器界面

**文件：**
- 创建：`app/api/chat.py`、`app/main.py`、`app/runtime.py`；
- 创建：`app/static/index.html`、`app/static/app.js`、`app/static/styles.css`；
- 测试：`tests/integration/test_chat_api.py`、`tests/e2e/test_user_journeys.py`。

**产出接口：**
- `POST /api/chat` 接收 `conversation_id`、`message` 和 `X-Demo-Actor`；
- 返回 `reply`、`status`、可选 `meeting_draft`、`needs_confirmation` 和 `request_id`；
- `GET /health` 与 `/` 单页聊天界面；
- 端到端用户旅程证明创建、查询、更新和危险请求零写入。

- [ ] 先编写路由和完整旅程失败测试；
- [ ] 实现运行时装配、路由、异常信封和无依赖界面；
- [ ] 运行集成及端到端测试并整理代码。

### 任务 5：可复现交付、文档和完整验证

**文件：**
- 创建：`README.md`、`Dockerfile`；
- 修改：`DESIGN.md`、`.env.example`、`pyproject.toml`；
- 测试：全部既有测试。

**产出：** 一条命令完成本地启动、确定性种子与重置说明、可选真实模型配置、测试覆盖率命令和演示脚本。

- [ ] 在干净虚拟环境安装项目并运行 Ruff 与完整分支覆盖率测试；
- [ ] 验证 `/health`、首页和全部演示对话；
- [ ] 执行依赖、安全和意外密钥检查；
- [ ] 检查 `DESIGN.md` 的篇幅、范围一致性和占位符；
- [ ] 记录准确验证证据和剩余限制。
