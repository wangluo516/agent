# 会议确认预览展示实施计划

> **供智能体执行者使用：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，按复选框逐项执行本计划。

**目标：** 网页收到会议草稿时，在助手回复中展示中文会议明细，并保留手动输入“确认”或“取消”的交互方式。

**架构：** 在现有 `app/static/app.js` 中增加无 DOM 依赖的纯格式化函数，先把 API 响应转换为安全纯文本，再交给既有 `append` 函数通过 `textContent` 渲染。使用 Node 内置测试运行器直接加载并验证格式化函数，不新增 npm 依赖，不修改后端 API。

**技术栈：** 原生 JavaScript、Node.js 内置 `node:test`、FastAPI 静态文件、Pytest、Ruff。

## 全局约束

- 不增加确认或取消按钮。
- 不修改后端 API 和确认前禁止写入的安全约束。
- 只展示 `meeting_draft` 中实际存在的字段。
- 时间统一按 `Asia/Shanghai` 格式化为 `MM月DD日 HH:mm`；解析失败时保留原值。
- 所有内容继续通过 `textContent` 写入 DOM，不拼接 HTML。
- 不引入 npm 依赖。
- 当前目录不含 `.git`，不执行提交或推送。

---

### 任务 1：用失败测试定义会议草稿展示文本

**文件：**

- 新建：`tests/frontend/test_app.js`
- 测试：`tests/frontend/test_app.js`

**接口：**

- 使用：CommonJS `require("../../app/static/app.js")`
- 期望导出：`formatAssistantReply(body: object): string`

- [ ] **步骤 1：编写只有时间字段的修改草稿测试**

```javascript
const test = require('node:test');
const assert = require('node:assert/strict');
const { formatAssistantReply } = require('../../app/static/app.js');

test('修改草稿会显示时间并提示手动确认', () => {
  const text = formatAssistantReply({
    reply: '请确认以下会议变更。',
    needs_confirmation: true,
    meeting_draft: {
      start_at: '2026-08-15T15:00:00+08:00',
      end_at: '2026-08-15T16:00:00+08:00',
    },
  });

  assert.equal(
    text,
    '请确认以下会议变更。\n\n开始时间：08月15日 15:00\n结束时间：08月15日 16:00\n\n请手动输入“确认”或“取消”。',
  );
});
```

- [ ] **步骤 2：编写完整创建草稿测试**

```javascript
test('创建草稿会显示所有存在的会议字段', () => {
  const text = formatAssistantReply({
    reply: '请确认以下会议安排。',
    needs_confirmation: true,
    meeting_draft: {
      title: '设计评审',
      start_at: '2026-08-15T15:00:00+08:00',
      end_at: '2026-08-15T16:00:00+08:00',
      attendee_ids: ['bob', 'carol'],
      room_id: 'room-orchid',
      required_features: ['whiteboard'],
    },
  });

  assert.match(text, /会议主题：设计评审/);
  assert.match(text, /参会人：bob、carol/);
  assert.match(text, /会议室：room-orchid/);
  assert.match(text, /所需设施：whiteboard/);
});
```

- [ ] **步骤 3：运行测试并确认按预期失败**

运行：

```powershell
node --test tests/frontend/test_app.js
```

预期：测试失败，原因是 `formatAssistantReply` 尚未导出或不存在。

### 任务 2：实现安全的前端草稿格式化

**文件：**

- 修改：`app/static/app.js`
- 测试：`tests/frontend/test_app.js`

**接口：**

- 生成：`formatMeetingDate(value: string): string`
- 生成：`formatMeetingDraft(draft: object | null): string`
- 生成并导出：`formatAssistantReply(body: object): string`

- [ ] **步骤 1：实现上海时区时间格式化**

使用 `Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })` 和 `formatToParts`，组装为 `MM月DD日 HH:mm`；无效日期直接返回原字符串。

- [ ] **步骤 2：实现草稿字段格式化**

按主题、开始时间、结束时间、参会人、会议室、所需设施的顺序生成行。字符串为空、数组为空或字段不存在时跳过，不输出 `undefined`。

- [ ] **步骤 3：实现完整助手回复格式化**

```javascript
const formatAssistantReply = (body) => {
  const sections = [body?.reply].filter(Boolean);
  const details = formatMeetingDraft(body?.meeting_draft);
  if (details) sections.push(details);
  if (details && body?.needs_confirmation) {
    sections.push('请手动输入“确认”或“取消”。');
  }
  return sections.join('\n\n');
};
```

Node 环境通过 `module.exports` 导出函数；没有 `document` 时提前返回。浏览器提交响应时改为调用 `formatAssistantReply(body)`，错误响应继续回退到 `body.error.message`。

- [ ] **步骤 4：运行 Node 测试并确认通过**

运行：

```powershell
node --test tests/frontend/test_app.js
```

预期：2 项测试全部通过。

### 任务 3：回归与页面验收

**文件：**

- 验证：`app/static/app.js`
- 验证：`tests/frontend/test_app.js`

**接口：**

- 使用：运行中的 `GET /` 和 `POST /api/chat`
- 产出：页面可见的会议确认明细

- [ ] **步骤 1：运行全量 Python 测试**

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q
```

预期：全部通过且没有新增失败。

- [ ] **步骤 2：运行静态检查和格式检查**

```powershell
.\.venv\Scripts\python.exe -m ruff check --no-cache .
.\.venv\Scripts\python.exe -m ruff format --check --no-cache .
```

预期：两项检查退出码均为 0。

- [ ] **步骤 3：通过浏览器验收真实场景**

刷新 `http://127.0.0.1:8000/`，依次输入：

```text
查询我的会议
把我的会议改到下午3点
```

预期：助手气泡显示开始时间 `08月15日 15:00`、结束时间 `08月15日 16:00` 和手动确认提示；页面不增加确认或取消按钮，数据库未执行修改。

- [ ] **步骤 4：记录交付状态**

汇报修改文件、Node/Pytest/Ruff 结果、真实页面验收结果，并明确当前没有 Git 提交或推送。
