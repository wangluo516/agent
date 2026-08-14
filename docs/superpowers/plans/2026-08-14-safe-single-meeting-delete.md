# 安全删除单个会议 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 增加仅限组织者、仅限单个目标、必须二次确认且带版本校验的会议删除能力，并保持批量、越权和注入请求不可执行。

**Architecture:** LLM 和 Demo 解释器只输出结构化 `delete` 意图；LangGraph 工作流负责候选解析、权限、预览和确认；SQLite 仓库仅提供按组织者、会议 ID 和版本删除单条记录的方法。删除确认哈希绑定完整删除快照，执行成功后返回被删除会议详情并清理会话上下文。

**Tech Stack:** Python 3.12、Pydantic v2、LangGraph、FastAPI、SQLite、pytest、Ruff、Node test runner。

## Global Constraints

- 一次只能删除一个明确会议，不能增加批量删除 API。
- 只有会议组织者可以删除，参会者不可删除。
- 删除必须经过预览和后续独立消息“确认”。
- “所有人、所有、全部、批量、清空”、SQL、任意 HTTP 和提示词注入继续被确定性代码拒绝。
- LLM 不得决定身份、授权、确认结果或数据库操作。
- 删除使用物理删除；不增加软删除字段、恢复站或管理员能力。
- 删除成功后必须返回被删除会议完整详情。
- 当前目录没有本地 `.git`；未获得新的提交或推送授权，本计划执行期间不得提交或推送。

---

### Task 1: 收窄预检规则并增加删除授权策略

**Files:**
- Modify: `app/domain/policies.py`
- Modify: `tests/unit/test_policies.py`

**Interfaces:**
- Produces: `authorize_delete(actor: Actor, meeting: Meeting) -> bool`
- Produces: `classify_unsafe_request(message: str) -> str | None`，允许安全的单会议删除文本，拒绝批量和 SQL 删除文本。

- [ ] **Step 1: 写安全单删和危险删除的失败测试**

```python
def test_single_meeting_delete_is_not_rejected_by_precheck() -> None:
    assert classify_unsafe_request("把第二个会议删除") is None


@pytest.mark.parametrize(
    "message",
    ["删除所有人的会议", "删除我的全部会议", "批量删除会议", "清空会议", "DELETE FROM meetings"],
)
def test_bulk_clear_and_sql_delete_are_rejected(message: str) -> None:
    assert classify_unsafe_request(message) is not None


def test_only_organizer_can_delete(meeting: Meeting) -> None:
    assert authorize_delete(Actor(id=meeting.organizer_id, display_name="Owner"), meeting)
    with pytest.raises(AuthorizationError):
        authorize_delete(Actor(id=meeting.attendee_ids[0], display_name="Attendee"), meeting)
```

- [ ] **Step 2: 运行测试并确认因通用删除规则和缺少授权函数而失败**

Run: `pytest tests/unit/test_policies.py -q`

Expected: 单会议删除仍返回 `deletion is not supported`，并且 `authorize_delete` 尚不存在。

- [ ] **Step 3: 实现最小确定性策略**

```python
_UNSAFE_PATTERNS = (
    (
        re.compile(r"删除.*(?:所有人|所有|全部|批量)|(?:所有人|所有|全部|批量).*删除"),
        "bulk deletion is not supported",
    ),
    (re.compile(r"清空"), "bulk deletion is not supported"),
    (re.compile(r"\bdelete\s+from\b", re.IGNORECASE), "database commands are not supported"),
    (re.compile(r"\bdrop\b|\btruncate\b", re.IGNORECASE), "database commands are not supported"),
    (
        re.compile(
            r"\b(select\s+.+\s+from|insert\s+into|update\s+\S+\s+set|create\s+(table|database|user|index)|alter\s+(table|database|user)|union\s+select)\b",
            re.IGNORECASE,
        ),
        "SQL commands are not supported",
    ),
    (
        re.compile(r"\b(get|post|put|patch|delete)\s+https?://", re.IGNORECASE),
        "arbitrary HTTP requests are not supported",
    ),
)


def authorize_delete(actor: Actor, meeting: Meeting) -> bool:
    if actor.id != meeting.organizer_id:
        raise AuthorizationError("only the organizer may delete a meeting")
    return True
```

- [ ] **Step 4: 运行策略测试并确认通过**

Run: `pytest tests/unit/test_policies.py -q`

- [ ] **Step 5: 检查本任务差异，不提交或推送**

Run: `git diff -- app/domain/policies.py tests/unit/test_policies.py`（若本地仍无 `.git`，改用逐文件审阅）。

---

### Task 2: 扩展结构化删除意图和候选选择状态

**Files:**
- Modify: `app/agent/interpreter.py`
- Modify: `app/domain/models.py`
- Modify: `app/agent/demo_interpreter.py`
- Modify: `app/agent/llm_interpreter.py`
- Modify: `app/agent/state.py`
- Modify: `tests/unit/test_demo_interpreter.py`
- Modify: `tests/unit/test_llm_interpreter.py`
- Modify: `tests/unit/test_state.py`

**Interfaces:**
- Produces: `Operation` 包含 `delete`。
- Produces: `ConversationState.selection_action: Literal["update", "delete"] | None`。
- Produces: `PendingAction.action: Literal["create", "update", "delete"]`。
- Consumes: `MeetingCommand(operation="delete", meeting_id=<candidate-or-none>)`。

- [ ] **Step 1: 写解释器和状态模型失败测试**

```python
@pytest.mark.asyncio
async def test_delete_second_candidate_returns_delete_command() -> None:
    context = context_with_two_candidates(status="done")
    command = await DemoInterpreter().interpret("把第二个会议删除", context)
    assert command.operation == "delete"
    assert command.meeting_id == context.state.meeting_candidates[1].id


def test_pending_action_accepts_delete() -> None:
    pending = PendingAction(action="delete", meeting_id="meeting-2", confirmation_hash="hash")
    assert pending.action == "delete"
```

LLM 捕获测试还要断言提示词明确包含“delete 的 meeting_id 只能来自候选会议，权限由服务端判断”。

- [ ] **Step 2: 运行定向测试并确认因 schema 不支持 delete 而失败**

Run: `pytest tests/unit/test_demo_interpreter.py tests/unit/test_llm_interpreter.py tests/unit/test_state.py -q`

- [ ] **Step 3: 实现删除命令和只读候选解析**

```python
Operation = Literal[
    "create",
    "query",
    "update",
    "delete",
    "availability",
    "select",
    "confirm",
    "cancel",
    "unsafe",
    "unknown",
]


class PendingAction(ImmutableModel):
    action: Literal["create", "update", "delete"]
    confirmation_hash: str = Field(min_length=1)
    meeting_id: str | None = None


class ConversationState(ImmutableModel):
    selection_action: Literal["update", "delete"] | None = None
```

Demo 解释器在空闲、查询判断之前识别自然语言删除，序号、候选 ID 或唯一候选主题命中时填入候选 ID；没有候选时只返回 `operation="delete"`。LLM 提示词明确删除只是一种意图，且 `meeting_id` 必须来自会话候选列表。

- [ ] **Step 4: 运行定向测试并确认通过**

Run: `pytest tests/unit/test_demo_interpreter.py tests/unit/test_llm_interpreter.py tests/unit/test_state.py -q`

- [ ] **Step 5: 检查新增字段在状态清理与 model_copy 中不会残留**

Run: `rg -n "selection_action|pending_action|delete" app/agent app/domain tests/unit`

---

### Task 3: 增加单记录版本化仓库删除

**Files:**
- Modify: `app/repositories/meetings.py`
- Modify: `app/agent/tools.py`
- Modify: `tests/integration/test_repository.py`

**Interfaces:**
- Produces: `MeetingRepository.delete(organizer_id: str, meeting_id: str, expected_version: int) -> Meeting`
- Produces: `RepositoryPort.delete(organizer_id: str, meeting_id: str, expected_version: int) -> Meeting`
- Produces: `MeetingTools.prepare_delete(actor: Actor, meeting: Meeting) -> Meeting`
- Consumes: Task 1 的 `authorize_delete`。

- [ ] **Step 1: 写仓库原子删除失败测试**

```python
def test_delete_returns_deleted_meeting_and_removes_only_target(repository, draft) -> None:
    target = repository.create("alice", draft, "target")
    other = repository.create("alice", draft.model_copy(update={"title": "Other"}), "other")
    deleted = repository.delete("alice", target.id, expected_version=target.version)
    assert deleted.id == target.id
    assert repository.find_visible(Actor(id="alice", display_name="Alice"), target.id) is None
    assert repository.find_visible(Actor(id="alice", display_name="Alice"), other.id) is not None


@pytest.mark.parametrize("organizer_id,version", [("bob", 1), ("alice", 999)])
def test_delete_rejects_wrong_owner_or_stale_version(
    repository, draft, organizer_id, version
) -> None:
    target = repository.create("alice", draft, "target")
    with pytest.raises(ConflictError):
        repository.delete(organizer_id, target.id, expected_version=version)
```

- [ ] **Step 2: 运行仓库测试并确认因缺少 delete 方法而失败**

Run: `pytest tests/integration/test_repository.py -q`

- [ ] **Step 3: 实现单事务查询加条件删除**

```python
def delete(self, organizer_id: str, meeting_id: str, expected_version: int) -> Meeting:
    with closing(self._connect()) as connection, connection:
        row = connection.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
        if row is None or row["organizer_id"] != organizer_id or row["version"] != expected_version:
            raise ConflictError("meeting was changed or is unavailable")
        meeting = self._to_meeting(row)
        result = connection.execute(
            "DELETE FROM meetings WHERE id = ? AND organizer_id = ? AND version = ?",
            (meeting_id, organizer_id, expected_version),
        )
        if result.rowcount != 1:
            raise ConflictError("meeting was changed or is unavailable")
    return meeting
```

`MeetingTools.prepare_delete` 只调用 `authorize_delete` 并返回会议，不调用日历或会议室 API。

- [ ] **Step 4: 运行仓库与工具相关测试并确认通过**

Run: `pytest tests/integration/test_repository.py tests/integration/test_agent_workflow.py -q`

---

### Task 4: 接入目标解析、预览、确认和执行工作流

**Files:**
- Modify: `app/agent/service.py`
- Modify: `app/agent/state.py`
- Modify: `tests/integration/test_agent_workflow.py`
- Modify: `tests/e2e/test_user_journeys.py`

**Interfaces:**
- Produces: `DeleteSnapshot(meeting: Meeting, expected_version: int)`。
- Produces: `_delete_snapshots: dict[tuple[str, str], DeleteSnapshot]`。
- Consumes: Task 2 的 `selection_action`、Task 3 的 `repository.delete`。

测试文件使用现有 `chat()` 与 `assistant()`，并增加以下固定数据帮助函数：

```python
def seed_owned_meeting(repository) -> Meeting:
    return repository.create(
        "alice",
        MeetingDraft(
            title="设计评审",
            start_at=datetime(2026, 8, 15, 15, tzinfo=SHANGHAI),
            end_at=datetime(2026, 8, 15, 16, tzinfo=SHANGHAI),
            attendee_ids=("bob",),
        ),
        "delete-target",
    )


def seed_alice_meeting_with_bob(repository) -> Meeting:
    return seed_owned_meeting(repository)
```

- [ ] **Step 1: 写完整删除旅程失败测试**

```python
@pytest.mark.asyncio
async def test_delete_second_meeting_requires_confirmation_and_returns_deleted_details(
    repository,
) -> None:
    first, second = seed_two_owned_meetings(repository)
    service = assistant(repository)
    await service.handle(chat(), "查询我的会议")
    preview = await service.handle(chat(request_id="preview"), "把第二个会议删除")
    assert preview.status == "needs_confirmation"
    assert preview.needs_confirmation is True
    assert preview.meeting_draft.title == second.title
    assert repository.find_visible(chat().actor, second.id) is not None

    confirmed = await service.handle(chat(request_id="confirm"), "确认")
    assert confirmed.status == "done"
    assert confirmed.reply == "会议已删除。"
    assert confirmed.meeting_draft.title == second.title
    assert repository.find_visible(chat().actor, first.id) is not None
    assert repository.find_visible(chat().actor, second.id) is None
```

继续写以下失败测试，每个测试只断言一个安全性质：

```python
@pytest.mark.asyncio
async def test_cancel_delete_keeps_target(repository) -> None:
    target = seed_owned_meeting(repository)
    service = assistant(repository)
    await service.handle(chat(), "删除我的会议")
    cancelled = await service.handle(chat(request_id="cancel"), "取消")
    assert cancelled.status == "done"
    assert repository.find_visible(chat().actor, target.id) is not None


@pytest.mark.asyncio
async def test_attendee_cannot_delete_visible_meeting(repository) -> None:
    target = seed_alice_meeting_with_bob(repository)
    service = assistant(repository)
    rejected = await service.handle(chat(actor_id="bob"), f"删除会议 {target.id}")
    assert rejected.status == "rejected"
    assert repository.find_visible(chat(actor_id="bob").actor, target.id) is not None


@pytest.mark.asyncio
async def test_stale_delete_confirmation_does_not_delete(repository) -> None:
    target = seed_owned_meeting(repository)
    service = assistant(repository)
    await service.handle(chat(), "删除我的会议")
    repository.update("alice", target.id, MeetingPatch(title="已变更"), target.version)
    stale = await service.handle(chat(request_id="stale"), "确认")
    assert stale.status == "rejected"
    assert repository.find_visible(chat().actor, target.id) is not None


@pytest.mark.asyncio
async def test_query_interrupts_delete_confirmation(repository) -> None:
    target = seed_owned_meeting(repository)
    service = assistant(repository)
    await service.handle(chat(), "删除我的会议")
    await service.handle(chat(request_id="query"), "查询我的会议")
    rejected = await service.handle(chat(request_id="confirm"), "确认")
    assert rejected.status == "rejected"
    assert repository.find_visible(chat().actor, target.id) is not None
```

另加具名用例 `test_duplicate_titles_require_selection`、`test_repeated_confirmation_has_no_side_effect` 和 `test_deleted_meeting_no_longer_marks_attendee_busy`，分别断言同名时不预览、第二次确认不影响其他会议，以及确认删除后对应时段恢复为空闲。

- [ ] **Step 2: 运行定向工作流测试并确认失败点覆盖缺失的 delete 分支**

Run: `pytest tests/integration/test_agent_workflow.py tests/e2e/test_user_journeys.py -q`

- [ ] **Step 3: 实现删除目标解析和确认快照**

```python
class DeleteSnapshot(ImmutableModel):
    meeting: Meeting
    expected_version: int = Field(ge=1)
```

解析顺序固定为：命令中的候选 ID → 原始消息中的候选 ID →序号 → 唯一主题 → 当前唯一可见会议。无法唯一定位时写入 `selection_action="delete"` 和候选列表；后续 `select` 根据 `selection_action` 继续为 `delete` 而不是误转成 `update`。

预览阶段用完整 `DeleteSnapshot` 计算确认哈希并保存到会话隔离字典；确认阶段不要求 `state.draft`，而是重新读取删除快照并校验哈希；执行阶段调用版本化仓库删除。

- [ ] **Step 4: 实现状态清理和明确错误响应**

取消、查询打断、执行成功、预检拒绝和确认过期都必须清除删除快照、`selection_action`、`pending_action`、`selected_meeting_id` 和候选列表。参会者删除返回“只有会议组织者可以删除该会议”，不得转成“会议服务暂时不可用”。

- [ ] **Step 5: 运行定向工作流和端到端测试并确认通过**

Run: `pytest tests/integration/test_agent_workflow.py tests/e2e/test_user_journeys.py -q`

---

### Task 5: 更新中文交付文档和安全说明

**Files:**
- Modify: `README.md`
- Modify: `DESIGN.md`

**Interfaces:**
- Documents: “查询—删除单个会议—确认—再次查询”的 demo/真实 LLM 操作。
- Documents: LLM 只做意图解析，权限和单记录约束在确定性代码中执行。

- [ ] **Step 1: 更新能力范围与安全说明**

README 增加以下可直接测试的对话：

```text
查询我的会议
删除第二个会议
确认
查询我的会议
```

同时明确“删除所有人的会议”“清空会议”“批量删除”仍被拒绝。DESIGN 删除“不实现删除”的旧描述，改为“只实现组织者单会议确认删除，不实现批量删除”。

- [ ] **Step 2: 检查文档无自相矛盾或遗留旧描述**

Run: `rg -n "不实现.*删除|删除.*不存在|deletion is not supported|删除所有人的会议|删除第二个" README.md DESIGN.md`

---

### Task 6: 全量验证与工作流审计

**Files:**
- Review: `app/agent/graph.py`
- Review: `app/agent/service.py`
- Review: `app/domain/policies.py`
- Review: `app/repositories/meetings.py`
- Review: `tests/`

**Interfaces:**
- Verifies: 预检 → 解释 → 目标解析 → 权限 → 预览 → 确认 → 版本校验 → 单条删除 → 状态清理。

- [ ] **Step 1: 运行全量自动化验证**

```powershell
pytest --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=80
python -m ruff check --no-cache .
python -m ruff format --check --no-cache .
python -m compileall -q app tests
node --test tests/frontend/test_app.js
```

- [ ] **Step 2: 运行真实服务旅程**

使用唯一会话 ID 依次发送：查询会议、删除第二个、确认、再次查询；验证预览前数据库不变、确认后仅目标消失、响应显示被删除详情。再验证删除所有人的会议被拒绝且数据库不变。

- [ ] **Step 3: 审计未覆盖边界**

逐项检查：无候选、单候选、多候选、同名候选、错误序号、伪造 ID、参会者、组织者、取消、查询打断、重复确认、并发更新、并发删除、服务重启、LLM 非法结构化输出、日历忙闲释放、数据库异常。每项必须有自动测试或在交付说明中明确未覆盖原因和风险。

- [ ] **Step 4: 审查安全性质**

确认仓库没有 `delete_all`、按标题删除或用户可控 SQL；LLM 输出的身份字段不存在；所有写入路径都要求服务端 actor；删除路径不调用日历/会议室外部写操作；日志和响应不包含 API key。

- [ ] **Step 5: 汇报实际证据，不提交或推送**

列出测试数量、覆盖率、静态检查、真实交互结果、已发现并处理的遗漏，以及仍存在的非目标限制。只有用户另行明确授权后才提交或推送。
