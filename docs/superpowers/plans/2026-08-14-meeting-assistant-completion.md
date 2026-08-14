# 智能会议助手补全实施计划

> **执行要求：** 使用 `superpowers:executing-plans` 在当前隔离快照中逐项实施。每项行为变更必须先看到对应测试失败，再写最小实现。当前目录没有 `.git`，且用户未授权提交，因此所有“提交”检查点改为测试检查点，不执行 commit 或 push。

**目标：** 补齐空闲查询、模拟 HTTP API 调用、多会议选择、无日期改期、明确忙碌提示和可安装 wheel，并把约定文档统一为简体中文。

**架构：** 保留固定 LangGraph 工作流和端口适配器。运行时通过 `httpx.AsyncClient` 与 `ASGITransport` 调用模拟 FastAPI；会话状态显式保存会议候选项，解释器生成结构化空闲查询或选择命令。

**技术栈：** Python 3.12、FastAPI、Pydantic v2、LangGraph、httpx、SQLite、pytest、Ruff、setuptools。

## 全局约束

- 不新增删除、批量修改、周期会议、真实 OAuth、RAG 或多 Agent。
- 模型不能获得数据库、身份、任意 HTTP 或写入权限。
- 所有创建和更新继续经过预览与明确确认。
- 文档中文化不翻译代码标识符、环境变量、命令、HTTP 路径和 JSON 字段。
- 不提交、不推送、不创建或合并 Pull Request。

---

### 任务 1：结构化空闲查询

**文件：**
- 修改：`app/agent/interpreter.py`
- 修改：`app/agent/demo_interpreter.py`
- 修改：`app/agent/service.py`
- 修改：`app/domain/availability.py`
- 测试：`tests/unit/test_demo_interpreter.py`
- 测试：`tests/integration/test_agent_workflow.py`
- 测试：`tests/e2e/test_user_journeys.py`

**接口：**
- 新增 `AvailabilityQuery(attendee_ids, window_start, window_end, duration_minutes)`。
- `MeetingCommand.operation` 新增 `availability` 和 `select`。
- `MeetingCommand.availability` 保存空闲查询参数。

- [ ] **步骤 1：写解释器失败测试**

```python
command = await DemoInterpreter().interpret("查询 bob 明天下午3点是否空闲", context())
assert command.operation == "availability"
assert command.availability.attendee_ids == ("bob",)
assert command.availability.window_start == datetime(2026, 8, 15, 15, tzinfo=SHANGHAI)
assert command.availability.window_end == datetime(2026, 8, 15, 16, tzinfo=SHANGHAI)
```

- [ ] **步骤 2：运行定向测试并确认因缺少 availability 意图而失败**

运行：`.venv\Scripts\python.exe -m pytest tests/unit/test_demo_interpreter.py -q`

- [ ] **步骤 3：实现最小结构化查询与解析**

优先识别“空闲”“有空”“忙不忙”，提取 `alice|bob|carol`、今天/明天、上午/下午和整点。明确整点时使用一小时窗口；只有上午/下午时分别使用 09:00—12:00、13:00—18:00。

- [ ] **步骤 4：写服务失败测试**

```python
reply = await service.handle(chat(), "查询 carol 明天上午10点是否空闲")
assert reply.status == "done"
assert "carol" in reply.reply
assert "忙碌" in reply.reply
```

- [ ] **步骤 5：运行失败测试，确认当前 query 分支错误返回会议列表**

运行：`.venv\Scripts\python.exe -m pytest tests/integration/test_agent_workflow.py -q`

- [ ] **步骤 6：实现空闲查询节点**

调用 `CalendarPort.freebusy`；精确时间窗口回复“均空闲”或列出忙碌参会人，宽时间窗口调用 `find_common_free_slots` 返回共同空闲区间。缺少必要字段时返回 `needs_clarification`。

- [ ] **步骤 7：运行任务 1 测试至通过**

运行：`.venv\Scripts\python.exe -m pytest tests/unit/test_demo_interpreter.py tests/integration/test_agent_workflow.py tests/e2e/test_user_journeys.py -q`

---

### 任务 2：多会议选择与无日期改期

**文件：**
- 修改：`app/domain/models.py`
- 修改：`app/agent/state.py`
- 修改：`app/agent/demo_interpreter.py`
- 修改：`app/agent/llm_interpreter.py`
- 修改：`app/agent/service.py`
- 测试：`tests/unit/test_demo_interpreter.py`
- 测试：`tests/unit/test_state.py`
- 测试：`tests/integration/test_agent_workflow.py`
- 测试：`tests/e2e/test_user_journeys.py`

**接口：**
- 新增 `MeetingCandidate(id, title, start_at, end_at)`。
- `ConversationState.meeting_candidates` 保存当前用户可见的候选会议。
- `select` 命令只允许选择候选列表中的会议，并继续 `state.draft` 中未完成的更新。

- [ ] **步骤 1：写无日期改期失败测试**

```python
await service.handle(chat(), "查询我的会议")
preview = await service.handle(chat(request_id="r2"), "把时间改到下午3点")
assert preview.meeting_draft.start_at == datetime(2026, 8, 15, 15, tzinfo=SHANGHAI)
```

- [ ] **步骤 2：运行测试并确认当前结果错误为 2026-08-14 15:00**

运行：`.venv\Scripts\python.exe -m pytest tests/e2e/test_user_journeys.py -q`

- [ ] **步骤 3：实现选中会议日期基准**

查询结果写入 `meeting_candidates`；解释器在消息没有“今天/明天”时，从 `selected_meeting_id` 对应候选项读取原日期。LLM 提示加入选中会议和候选摘要。

- [ ] **步骤 4：写多会议选择失败测试**

```python
await service.handle(chat(), "查询我的会议")
clarify = await service.handle(chat(request_id="r2"), "把会议改到明天下午4点")
preview = await service.handle(chat(request_id="r3"), "第一个")
assert clarify.status == "needs_clarification"
assert preview.status == "needs_confirmation"
```

- [ ] **步骤 5：运行测试并确认“第一个”被误判为创建意图**

运行：`.venv\Scripts\python.exe -m pytest tests/integration/test_agent_workflow.py -q`

- [ ] **步骤 6：实现候选列表和 select 流程**

查询回复使用 `1. 主题（日期 时间）` 格式。解释器按序号、完整 ID 或唯一主题匹配候选；服务端再次验证候选可见性，将 `select` 转换为携带原更新草稿的 `update` 命令。

- [ ] **步骤 7：运行任务 2 测试至通过**

运行：`.venv\Scripts\python.exe -m pytest tests/unit/test_demo_interpreter.py tests/unit/test_state.py tests/integration/test_agent_workflow.py tests/e2e/test_user_journeys.py -q`

---

### 任务 3：主运行时调用模拟 HTTP API

**文件：**
- 修改：`app/runtime.py`
- 修改：`app/main.py`
- 复用：`app/integrations/calendar_client.py`
- 复用：`app/integrations/room_client.py`
- 复用：`app/api/mock_integrations.py`
- 测试：`tests/integration/test_runtime.py`
- 测试：`tests/integration/test_mock_integrations.py`

**接口：**
- `Runtime.integration_client: httpx.AsyncClient | None`。
- `Runtime.aclose() -> None` 关闭运行时拥有的 client。
- `build_runtime` 默认创建包含模拟路由的 FastAPI 应用和 ASGI transport。

- [ ] **步骤 1：写运行时失败测试**

```python
runtime = build_runtime(tmp_path / "runtime.db")
assert isinstance(runtime.assistant._tools.calendar, CalendarClient)
assert isinstance(runtime.assistant._tools.rooms, RoomClient)
await runtime.aclose()
```

- [ ] **步骤 2：运行测试并确认当前注入的是 InProcessCalendar/InProcessRooms**

运行：`.venv\Scripts\python.exe -m pytest tests/integration/test_runtime.py -q`

- [ ] **步骤 3：接入真实 HTTP client**

创建仅包含模拟路由的 FastAPI 应用，通过 `httpx.ASGITransport` 和固定 `base_url` 构建 client，然后注入现有 `CalendarClient`、`RoomClient`。主应用 lifespan 调用 `Runtime.aclose()`。

- [ ] **步骤 4：运行运行时和模拟 API 测试至通过**

运行：`.venv\Scripts\python.exe -m pytest tests/integration/test_runtime.py tests/integration/test_mock_integrations.py tests/integration/test_chat_api.py -q`

---

### 任务 4：明确忙碌错误

**文件：**
- 修改：`app/domain/errors.py`
- 修改：`app/agent/tools.py`
- 修改：`app/agent/service.py`
- 测试：`tests/integration/test_agent_workflow.py`
- 测试：`tests/e2e/test_user_journeys.py`

**接口：**
- 新增 `AttendeeBusyError(attendee_ids)`，只保存忙碌参会人 ID。

- [ ] **步骤 1：修改已有忙碌场景断言并运行失败测试**

```python
assert rejected.status == "rejected"
assert "carol" in rejected.reply
assert "忙碌" in rejected.reply
assert "暂时不可用" not in rejected.reply
```

运行：`.venv\Scripts\python.exe -m pytest tests/e2e/test_user_journeys.py -q`

- [ ] **步骤 2：实现专用错误和服务层映射**

`MeetingTools._ensure_available` 收集忙碌参会人并抛出 `AttendeeBusyError`；`MeetingAssistant.handle` 在通用 `DomainError` 之前捕获，清除待确认动作并返回明确业务提示。

- [ ] **步骤 3：运行任务 4 测试至通过**

运行：`.venv\Scripts\python.exe -m pytest tests/integration/test_agent_workflow.py tests/e2e/test_user_journeys.py -q`

---

### 任务 5：可安装 wheel

**文件：**
- 修改：`pyproject.toml`
- 验证：`app/repositories/schema.sql`

- [ ] **步骤 1：记录当前构建失败证据**

运行：`.venv\Scripts\python.exe -m build`

预期当前失败：缺少 `build` 模块；此前 wheel 隔离安装已复现缺少 `app/repositories/schema.sql`。

- [ ] **步骤 2：修改打包配置**

将 `build>=1.2` 加入 `dev`，并在 package data 中加入 `repositories/schema.sql`：

```toml
[tool.setuptools.package-data]
app = ["static/*", "repositories/schema.sql"]
```

- [ ] **步骤 3：更新虚拟环境并构建 wheel**

运行：`.venv\Scripts\python.exe -m pip install -e ".[dev]"`

运行：`.venv\Scripts\python.exe -m build`

- [ ] **步骤 4：隔离安装并初始化数据库**

将 wheel 安装到 `dist/verify-install`，从仓库外目录导入该安装副本并初始化 `MeetingRepository`；命令必须退出码为 0，且实际加载路径位于 `dist/verify-install`。

---

### 任务 6：文档全部中文化

**文件：**
- 修改：`README.md`
- 修改：`DESIGN.md`
- 修改：`.env.example`
- 修改：`docs/superpowers/plans/2026-08-14-meeting-assistant.md`
- 保持中文：`docs/superpowers/specs/2026-08-14-meeting-assistant-completion-design.md`
- 保持中文：`docs/superpowers/plans/2026-08-14-meeting-assistant-completion.md`

- [ ] **步骤 1：翻译并更新 README**

保留所有可复制命令，中文说明默认 demo 模式、LLM 选型、重置、空闲查询、多会议选择、模拟 API、Docker 和验证步骤。

- [ ] **步骤 2：更新设计文档**

使 `DESIGN.md` 与真实 HTTP API 调用、候选状态、空闲查询、错误分类和 wheel 打包保持一致，并继续控制在简短设计文档范围。

- [ ] **步骤 3：翻译历史实施计划和环境示例注释**

所有自然语言段落、标题和注释使用简体中文；路径、命令、类型名和字段名保持原样。

- [ ] **步骤 4：人工扫描残留英文说明**

搜索英文标题和句子，逐项确认剩余英文只属于约定保留项。

---

### 任务 7：完整验收

- [ ] **步骤 1：运行完整测试和覆盖率门禁**

运行：`.venv\Scripts\python.exe -m pytest --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=80`

- [ ] **步骤 2：运行静态检查和格式检查**

运行：`.venv\Scripts\python.exe -m ruff check --no-cache .`

运行：`.venv\Scripts\python.exe -m ruff format --check --no-cache .`

- [ ] **步骤 3：运行编译、依赖和构建检查**

运行：`.venv\Scripts\python.exe -m compileall -q app tests`

运行：`.venv\Scripts\python.exe -m pip check`

运行：`.venv\Scripts\python.exe -m build`

- [ ] **步骤 4：重新执行题目原话**

验证“查询 bob 明天下午3点是否空闲”“把时间改到下午3点”“第一个”和忙碌参会人场景的实际 API 响应。
