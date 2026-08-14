(() => {
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
      append('assistant', body.reply || body.error?.message || '请求未能完成。');
    } catch {
      append('assistant', '网络连接失败，请稍后重试。');
    }
  });
})();
