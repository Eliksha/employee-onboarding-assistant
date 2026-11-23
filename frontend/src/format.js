// Shared display helpers (kept dependency-free so they can be tested with `node --test`).

// Backend ChatRequest.question has max_length=500 (backend/schemas/models.py).
export const CHAT_MAX_LENGTH = 500;

// Turn chat `sources` ([{file, section, score}] or a JSON string from history) into readable text.
// Returns '' when there is nothing to show, so fallback answers do not render "Sources: []".
export function formatSources(sources) {
  let list = sources;
  if (typeof list === 'string') {
    try { list = JSON.parse(list); } catch { return list.trim(); }
  }
  if (!Array.isArray(list) || list.length === 0) return '';
  return list
    .map((s) => (typeof s === 'string' ? s
      : [s?.file, s?.section].filter(Boolean).join(' › ') + (Number.isInteger(s?.page) ? ` (p. ${s.page})` : '')))
    .filter(Boolean)
    .join('; ');
}

// Feedback / escalation state of one chat answer: local actions (this session) override the stored history.
export function answerActions(message, local = {}) {
  return {
    rating: local.rating ?? message?.feedback ?? null,
    escalated: Boolean(local.escalated ?? message?.escalated),
  };
}

// Body for POST /escalate from a chat answer (question limited to the backend's 500 characters).
export function escalationPayload(message) {
  return { question: String(message?.question ?? '').slice(0, CHAT_MAX_LENGTH), message_id: message?.id };
}
