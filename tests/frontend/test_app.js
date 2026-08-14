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

test('确认保存后显示最终会议明细且不再提示确认', () => {
  const text = formatAssistantReply({
    reply: '会议已保存。',
    needs_confirmation: false,
    meeting_draft: {
      title: '开发会议',
      start_at: '2026-08-15T16:30:00+08:00',
      end_at: '2026-08-15T17:30:00+08:00',
      attendee_ids: ['jack', 'bob', 'alice', 'adam'],
      room_id: 'room-orchid',
      required_features: ['display'],
    },
  });

  assert.match(text, /^会议已保存。/);
  assert.match(text, /会议主题：开发会议/);
  assert.match(text, /参会人：jack、bob、alice、adam/);
  assert.match(text, /会议室：room-orchid/);
  assert.doesNotMatch(text, /请手动输入/);
});
