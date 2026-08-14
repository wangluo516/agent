(() => {
  const dateTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  });

  const formatMeetingDate = (value) => {
    if (typeof value !== 'string' || !value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    const parts = Object.fromEntries(
      dateTimeFormatter
        .formatToParts(date)
        .filter(({ type }) => type !== 'literal')
        .map(({ type, value: partValue }) => [type, partValue]),
    );
    return `${parts.month}月${parts.day}日 ${parts.hour}:${parts.minute}`;
  };

  const formatMeetingDraft = (draft) => {
    if (!draft || typeof draft !== 'object') return '';
    const lines = [];
    if (draft.title) lines.push(`会议主题：${draft.title}`);
    if (draft.start_at) lines.push(`开始时间：${formatMeetingDate(draft.start_at)}`);
    if (draft.end_at) lines.push(`结束时间：${formatMeetingDate(draft.end_at)}`);
    if (Array.isArray(draft.attendee_ids) && draft.attendee_ids.length) {
      lines.push(`参会人：${draft.attendee_ids.join('、')}`);
    }
    if (draft.room_id) lines.push(`会议室：${draft.room_id}`);
    if (Array.isArray(draft.required_features) && draft.required_features.length) {
      lines.push(`所需设施：${draft.required_features.join('、')}`);
    }
    return lines.join('\n');
  };

  const formatAssistantReply = (body) => {
    const sections = body?.reply ? [body.reply] : [];
    const details = formatMeetingDraft(body?.meeting_draft);
    if (details) sections.push(details);
    if (details && body?.needs_confirmation) {
      sections.push('请手动输入“确认”或“取消”。');
    }
    return sections.join('\n\n');
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { formatAssistantReply, formatMeetingDate, formatMeetingDraft };
  }
  if (typeof document === 'undefined') return;

  const form = document.querySelector('#chat-form');
  const input = document.querySelector('#message');
  const messages = document.querySelector('#messages');
  const conversationId = crypto.randomUUID();

  const append = (role, text) => {
    const message = document.createElement('article');
    message.className = `message ${role}`;
    message.textContent = text;
    messages.append(message);
    message.scrollIntoView({ block: 'end' });
  };

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const message = input.value.trim();
    if (!message) return;
    append('user', message);
    input.value = '';
    input.focus();
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Demo-Actor': 'alice' },
        body: JSON.stringify({ conversation_id: conversationId, message }),
      });
      const body = await response.json();
      append(
        'assistant',
        formatAssistantReply(body) || body.error?.message || '请求未能完成。',
      );
    } catch {
      append('assistant', '网络连接失败，请稍后重试。');
    }
  });
})();
