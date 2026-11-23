import { test } from 'node:test';
import assert from 'node:assert/strict';
import { CHAT_MAX_LENGTH, answerActions, escalationPayload, formatSources } from './format.js';

test('cited sources are rendered as file › section', () => {
  assert.equal(
    formatSources([{ file: 'handbook.md', section: '2. Leave Policy > 2.1 Casual Leave', score: 0.735 }]),
    'handbook.md › 2. Leave Policy > 2.1 Casual Leave',
  );
  assert.equal(
    formatSources([{ file: 'handbook.md', section: '3. Payroll' }, { file: 'faqs.md', section: 'FAQ: When is salary credited?' }]),
    'handbook.md › 3. Payroll; faqs.md › FAQ: When is salary credited?',
  );
});

test('empty or missing sources render nothing (no "Sources: []")', () => {
  for (const value of [[], '[]', '', null, undefined, {}]) assert.equal(formatSources(value), '');
});

test('JSON-string sources from history are parsed; plain strings pass through', () => {
  assert.equal(formatSources('[{"file":"faqs.md","section":"FAQ: X"}]'), 'faqs.md › FAQ: X');
  assert.equal(formatSources('handbook.md'), 'handbook.md');
});

test('chat input limit matches backend ChatRequest max_length', () => {
  assert.equal(CHAT_MAX_LENGTH, 500);
});

test('Phase 2 hybrid answers: records and handbook sources render as separate labels', () => {
  assert.equal(
    formatSources([
      { file: 'Your records', section: 'Leave balances', score: 1.0 },
      { file: 'handbook.md', section: '2. Leave Policy > 2.1 Casual Leave', score: 0.81 },
    ]),
    'Your records › Leave balances; handbook.md › 2. Leave Policy > 2.1 Casual Leave',
  );
  assert.equal(
    formatSources('[{"file":"Company records","section":"Payroll calendar","score":1.0}]'),
    'Company records › Payroll calendar',
  );
});

test('M4 page-aware citations: optional page is shown when present', () => {
  assert.equal(
    formatSources([
      { file: 'handbook.pdf', section: '7. Expenses and Travel', score: 0.7, page: 3 },
      { file: 'faqs.md', section: 'FAQ: How do I claim expenses?', score: 0.6 },
    ]),
    'handbook.pdf › 7. Expenses and Travel (p. 3); faqs.md › FAQ: How do I claim expenses?',
  );
  assert.equal(formatSources([{ file: 'handbook.pdf', section: '3. Payroll', page: null }]), 'handbook.pdf › 3. Payroll');
});

test('M5 answer actions: stored history state, overridden by this session', () => {
  assert.deepEqual(answerActions({ feedback: 'down', escalated: true }), { rating: 'down', escalated: true });
  assert.deepEqual(answerActions({ feedback: null, escalated: false }, { rating: 'up' }), { rating: 'up', escalated: false });
  assert.deepEqual(answerActions({}, { escalated: true }), { rating: null, escalated: true });
  assert.deepEqual(answerActions(undefined), { rating: null, escalated: false });
});

test('M5 escalation payload links the answer and respects the question limit', () => {
  assert.deepEqual(escalationPayload({ id: 7, question: 'What is the leave policy?' }),
    { question: 'What is the leave policy?', message_id: 7 });
  assert.equal(escalationPayload({ id: 8, question: 'x'.repeat(600) }).question.length, CHAT_MAX_LENGTH);
});
