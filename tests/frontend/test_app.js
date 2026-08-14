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
