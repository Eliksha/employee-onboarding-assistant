import { useCallback, useEffect, useState } from 'react';
import { LayoutDashboard, Bot, ClipboardCheck, CalendarDays, Laptop, Headset, Sparkles, Menu, X, Send, RefreshCw, ArrowRight, UserRound, ShieldCheck, LogOut, LoaderCircle, ThumbsUp, ThumbsDown, LifeBuoy } from 'lucide-react';
import { authApi, employeeApi, feedbackApi, setCsrfToken, setUnauthorizedHandler } from './api';
import { SESSION_EXPIRED_NOTICE, SIGNED_OUT_NOTICE } from './auth';
import LoginPage from './LoginPage';
import { CHAT_MAX_LENGTH, answerActions, escalationPayload, formatSources } from './format';
import './App.css';

const NAV = [
  ['Dashboard', LayoutDashboard], ['AI Assistant', Bot], ['My Checklist', ClipboardCheck],
  ['Leave & Payroll', CalendarDays], ['My Assets', Laptop], ['Support Center', Headset],
];
// Records loaded for the table pages: [record key, employeeApi method].
const PAGE_TASKS = {
  'Leave & Payroll': [['leave', 'leave'], ['payroll', 'payroll']],
  'My Assets': [['assets', 'assets']],
};
const unwrap = (data) => data?.items ?? data?.data ?? data?.results ?? data;
const asList = (data) => Array.isArray(unwrap(data)) ? unwrap(data) : [];
const display = (value) => value === null || value === undefined || value === '' ? '—' : typeof value === 'boolean' ? (value ? 'Yes' : 'No') : String(value);
const pretty = (key) => key.replaceAll('_', ' ').replace(/\b\w/g, (x) => x.toUpperCase());

function DataTable({ data, empty = 'No records available.' }) {
  const records = asList(data);
  if (!records.length) return <p className="muted">{empty}</p>;
  const keys = [...new Set(records.flatMap((record) => Object.keys(record ?? {})))].filter((key) => !['employee_id'].includes(key));
  return <div className="table-scroll"><table><thead><tr>{keys.map((key) => <th key={key}>{pretty(key)}</th>)}</tr></thead><tbody>{records.map((record, index) => <tr key={record.id ?? index}>{keys.map((key) => <td key={key}>{display(record[key])}</td>)}</tr>)}</tbody></table></div>;
}

// Rate or escalate one answer through the existing /feedback and /escalate endpoints.
function AnswerActions({ message }) {
  const [local, setLocal] = useState({});
  const [pending, setPending] = useState('');
  const [note, setNote] = useState('');
  const { rating, escalated } = answerActions(message, local);
  if (message.id == null) return null;
  const rate = async (value) => {
    setPending(value); setNote('');
    try { await feedbackApi.rate(message.id, value); setLocal((s) => ({ ...s, rating: value })); setNote('Thanks for the feedback.'); }
    catch (err) { setNote(err.response?.data?.detail ?? 'Could not save feedback.'); }
    finally { setPending(''); }
  };
  const escalate = async () => {
    setPending('escalate'); setNote('');
    try { const r = await feedbackApi.escalate(escalationPayload(message)); setLocal((s) => ({ ...s, escalated: true })); setNote(`Escalated to HR/IT (reference #${r.data?.id}).`); }
    catch (err) { setNote(err.response?.data?.detail ?? 'Could not escalate this answer.'); }
    finally { setPending(''); }
  };
  return <div className="answer-actions" aria-label="Answer feedback">
    <button type="button" className={rating === 'up' ? 'selected' : ''} aria-pressed={rating === 'up'} aria-label="Helpful" title="Helpful" disabled={!!pending} onClick={() => rate('up')}><ThumbsUp size={14}/></button>
    <button type="button" className={rating === 'down' ? 'selected' : ''} aria-pressed={rating === 'down'} aria-label="Not helpful" title="Not helpful" disabled={!!pending} onClick={() => rate('down')}><ThumbsDown size={14}/></button>
    <button type="button" className="escalate" disabled={!!pending || escalated} onClick={escalate}><LifeBuoy size={14}/>{escalated ? 'Escalated to HR/IT' : 'Escalate to HR/IT'}</button>
    {note && <span className="answer-note" role="status">{note}</span>}
  </div>;
}

function Chat({ employeeId }) {
  const [history, setHistory] = useState([]);
  const [question, setQuestion] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  // State is only updated in promise callbacks, never synchronously inside the effect.
  const load = useCallback(() => employeeApi.history(employeeId)
    .then((response) => { setHistory(asList(response.data).reverse()); setError(''); })
    .catch((err) => { setHistory([]); setError(err.response?.data?.detail ?? 'Could not load chat history. Check the FastAPI server.'); }),
  [employeeId]);
  useEffect(() => { load(); }, [load]);
  const send = async (event) => {
    event.preventDefault();
    const text = question.trim();
    if (!text || busy) return;
    setBusy(true); setError(''); setQuestion('');
    try { await employeeApi.chat(employeeId, text); await load(); }
    catch (err) { setQuestion(text); setError(err.response?.data?.detail ?? 'Chat request failed.'); }
    finally { setBusy(false); }
  };
  return <section className="panel chat-panel"><div className="panel-heading"><div><h2>Ask OnboardAI</h2><p>Answers from your handbook and employee records.</p></div><button className="subtle-button" onClick={load}><RefreshCw size={16}/> Refresh</button></div>
    <div className="chat-messages">{!history.length && <div className="empty-state"><Bot size={38}/><h3>How can I help you today?</h3><p>Try “What is my leave balance?” or “What is the leave policy?”</p></div>}
    {history.map((message, index) => <div className="exchange" key={message.id ?? index}><div className="bubble question">{message.question}</div><div className="bubble answer"><div className="answer-label"><Sparkles size={15}/> OnboardAI</div><p>{message.answer}</p>{formatSources(message.sources) && <small>Sources: {formatSources(message.sources)}</small>}<AnswerActions message={message}/></div></div>)}</div>
    {error && <p className="error" role="alert">{String(error)}</p>}
    <form className="chat-form" onSubmit={send}><input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask a question about onboarding..." aria-label="Chat question" maxLength={CHAT_MAX_LENGTH}/><button disabled={busy || !question.trim()} type="submit"><Send size={18}/>{busy ? 'Sending...' : 'Send'}</button></form>
    <p className="disclaimer">Demo only · Synthetic employee data · Responses may require HR verification.</p>
  </section>;
}


function Checklist({ employeeId }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState({});
  // Fetch only; state changes happen in promise callbacks (safe to call from an effect).
  const fetchItems = useCallback(() => employeeApi.checklist(employeeId)
    .then((response) => setItems(asList(response.data)))
    .catch((err) => {
      setItems([]);
      setError(err.response?.data?.detail ?? 'Could not load checklist.');
    })
    .finally(() => setLoading(false)), [employeeId]);
  // Initial load: `loading` starts true and the component remounts per employee (key={employeeId}).
  useEffect(() => { fetchItems(); }, [fetchItems]);
  // Refresh button: event handler, so resetting loading/error synchronously is fine.
  const load = () => {
    setLoading(true);
    setError('');
    return fetchItems();
  };

  const isDone = (item) => Boolean(item.done ?? item.is_done ?? item.completed ?? (item.status === 'completed' || item.status === 'done'));
  const getId = (item) => item.id ?? item.item_id;
  const toggle = async (item) => {
    const id = getId(item);
    if (id === undefined || id === null || saving[id]) return;
    const next = !isDone(item);
    setSaving((previous) => ({ ...previous, [id]: true }));
    setError('');
    try {
      await employeeApi.updateChecklist(employeeId, id, next);
      const response = await employeeApi.checklist(employeeId);
      setItems(asList(response.data));
    } catch (err) {
      setError(err.response?.data?.detail ?? 'Unable to save checklist change. Please try again.');
    } finally {
      setSaving((previous) => ({ ...previous, [id]: false }));
    }
  };
  const completed = items.filter(isDone).length;
  return <section className="panel checklist-panel">
    <div className="panel-heading"><div><h2>Onboarding Tasks</h2><p>{loading ? 'Loading checklist...' : `${completed} of ${items.length} tasks completed`}</p></div><button className="subtle-button" onClick={load} disabled={loading || Object.values(saving).some(Boolean)}><RefreshCw size={16}/> Refresh</button></div>
    {error && <p className="error" role="alert">{String(error)}</p>}
    {loading ? <p className="muted">Loading records...</p> : items.length === 0 ? <p className="muted">No checklist items available for this employee.</p> :
      <div className="checklist-items">{items.map((item, index) => {
        const id = getId(item);
        const done = isDone(item);
        const title = item.title ?? item.task_name ?? item.task ?? item.name ?? item.description ?? `Task ${index + 1}`;
        const description = item.description && item.description !== title ? item.description : null;
        return <label className={`checklist-item ${done ? 'is-done' : ''}`} key={id ?? index}>
          <input type="checkbox" checked={done} disabled={id == null || Boolean(saving[id])} onChange={() => toggle(item)} aria-label={`Mark ${title} ${done ? 'incomplete' : 'complete'}`}/>
          <span className="checklist-item-content"><strong>{String(title)}</strong>{description && <small>{String(description)}</small>}</span>
          <span className="checklist-status">{saving[id] ? 'Saving...' : done ? 'Completed' : 'Pending'}</span>
        </label>;
      })}</div>}
    <p className="disclaimer">Changes are saved to this demo employee's checklist.</p>
  </section>;
}


function SupportCenter({ employeeId }) {
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [form, setForm] = useState({ category: 'HR', subject: '', description: '' });

  // Fetch only; state changes happen in promise callbacks (safe to call from an effect).
  const fetchTickets = useCallback(() => employeeApi.tickets(employeeId)
    .then((response) => setTickets(asList(response.data)))
    .catch((err) => {
      setTickets([]);
      setError(err.response?.data?.detail ?? 'Could not load support tickets.');
    })
    .finally(() => setLoading(false)), [employeeId]);

  // Initial load: `loading` starts true and the component remounts per employee (key={employeeId}).
  useEffect(() => { fetchTickets(); }, [fetchTickets]);

  // Refresh button: event handler, so resetting loading/error synchronously is fine.
  const load = () => {
    setLoading(true);
    setError('');
    return fetchTickets();
  };

  const submit = async (event) => {
    event.preventDefault();
    if (submitting) return;
    const payload = {
      category: form.category.trim(),
      subject: form.subject.trim(),
      description: form.description.trim(),
    };
    if (payload.category.length < 2 || payload.subject.length < 3 || payload.description.length < 5) {
      setError('Enter a category, a subject of at least 3 characters, and a description of at least 5 characters.');
      setSuccess('');
      return;
    }
    setSubmitting(true);
    setError('');
    setSuccess('');
    try {
      const response = await employeeApi.createTicket(employeeId, payload);
      const ticketId = response.data?.id ?? response.data?.ticket_id;
      setForm({ category: 'HR', subject: '', description: '' });
      setSuccess(`Support ticket${ticketId != null ? ` #${ticketId}` : ''} submitted successfully.`);
      try {
        const refreshed = await employeeApi.tickets(employeeId);
        setTickets(asList(refreshed.data));
      } catch {
        setError('Ticket submitted, but the list could not refresh. Use Refresh to try again.');
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Could not submit ticket. Please check your entries and try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return <>
    <section className="panel support-panel">
      <div className="panel-heading"><div><h2>Create a Support Ticket</h2><p>Send an HR or IT request for {employeeId}.</p></div><span className="pill">{employeeId}</span></div>
      <form className="support-form" onSubmit={submit}>
        <label>Category
          <select value={form.category} disabled={submitting} onChange={(event) => setForm((current) => ({ ...current, category: event.target.value }))} required>
            <option value="HR">HR</option>
            <option value="IT">IT</option>
            <option value="Payroll">Payroll</option>
            <option value="Onboarding">Onboarding</option>
            <option value="Other">Other</option>
          </select>
        </label>
        <label>Subject
          <input value={form.subject} disabled={submitting} onChange={(event) => setForm((current) => ({ ...current, subject: event.target.value }))} minLength={3} maxLength={150} placeholder="Briefly describe your issue" required />
        </label>
        <label>Description
          <textarea value={form.description} disabled={submitting} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} minLength={5} maxLength={2000} rows={5} placeholder="Provide details so the support team can help" required />
        </label>
        {error && <p className="error" role="alert">{String(error)}</p>}
        {success && <p className="support-success" role="status">{success}</p>}
        <button className="support-submit" type="submit" disabled={submitting || !form.subject.trim() || !form.description.trim()}><Send size={16}/>{submitting ? 'Submitting...' : 'Submit Ticket'}</button>
      </form>
      <p className="disclaimer">Demo only · Avoid entering real personal or confidential information.</p>
    </section>
    <section className="panel">
      <div className="panel-heading"><div><h2>My Support Tickets</h2><p>Requests associated with {employeeId}.</p></div><button className="subtle-button" type="button" onClick={load} disabled={loading || submitting}><RefreshCw size={16}/> Refresh</button></div>
      {loading ? <p className="muted">Loading tickets...</p> : <DataTable data={tickets} empty="No support tickets submitted for this employee yet." />}
    </section>
  </>;
}

function SignOutButton({ onSignOut, signingOut }) {
  return <button type="button" className="subtle-button logout-button" onClick={onSignOut} disabled={signingOut}><LogOut size={16}/>{signingOut ? 'Signing out...' : 'Sign out'}</button>;
}

// The employee is always the signed-in user's own employee (identity comes from the server session).
function Workspace({ user, onSignOut, signingOut }) {
  const employeeId = user.employee_id;
  const [page, setPage] = useState('Dashboard');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  // Results are stored with the request they belong to; stale/empty states are derived during render
  // instead of being reset synchronously inside effects.
  const [profileResult, setProfileResult] = useState({ employeeId: null, data: null, error: '' });
  const [recordsResult, setRecordsResult] = useState({ requestKey: null, records: {} });
  const navigate = (next) => { setPage(next); setSidebarOpen(false); };
  useEffect(() => {
    let live = true;
    employeeApi.profile(employeeId)
      .then(({ data }) => { if (live) setProfileResult({ employeeId, data: unwrap(data), error: '' }); })
      .catch(() => { if (live) setProfileResult({ employeeId, data: null, error: 'Profile unavailable. Start the FastAPI backend.' }); });
    return () => { live = false; };
  }, [employeeId]);
  const profileCurrent = profileResult.employeeId === employeeId;
  const profile = profileCurrent ? profileResult.data : null;
  const profileError = profileCurrent ? profileResult.error : '';

  const pageTasks = PAGE_TASKS[page];
  const requestKey = pageTasks ? `${employeeId}|${page}` : null;
  useEffect(() => {
    if (!pageTasks) return undefined;
    let live = true;
    Promise.all(pageTasks.map(async ([key, method]) => { try { const result = await employeeApi[method](employeeId); return [key, { data: result.data }]; } catch (error) { return [key, { error: error.response?.data?.detail ?? 'Unable to load records.' }]; } }))
      .then((entries) => { if (live) setRecordsResult({ requestKey, records: Object.fromEntries(entries) }); });
    return () => { live = false; };
  }, [employeeId, pageTasks, requestKey]);
  const loading = requestKey !== null && recordsResult.requestKey !== requestKey;
  const records = loading ? {} : recordsResult.records;
  const name = profile?.full_name ?? profile?.name ?? user.name ?? employeeId;
  const panels = page === 'Leave & Payroll' ? [['leave', 'Leave Balances'], ['payroll', 'Payroll Calendar']] : page === 'My Checklist' ? [] : page === 'My Assets' ? [['assets', 'Assigned Assets']] : page === 'Support Center' ? [] : [];
  return <div className="app-shell">
    {sidebarOpen && <button className="overlay" aria-label="Close menu" onClick={() => setSidebarOpen(false)}/>}
    <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}><div className="brand"><div className="brand-icon"><Sparkles size={23}/></div><div><strong>OnboardAI</strong><small>NEW JOINER PLATFORM</small></div><button className="mobile-close" onClick={() => setSidebarOpen(false)} aria-label="Close menu"><X size={20}/></button></div><div className="nav-caption">WORKSPACE</div><nav>{NAV.map(([label, Icon]) => <button key={label} className={`nav-item ${page === label ? 'active' : ''}`} onClick={() => navigate(label)}><Icon size={19}/>{label}</button>)}</nav><div className="sidebar-footer"><ShieldCheck size={16}/> Synthetic-data demonstration</div></aside>
    <div className="main-area"><header className="topbar"><div className="breadcrumb"><button className="menu-button" aria-label="Open menu" onClick={() => setSidebarOpen(true)}><Menu size={22}/></button><span>Workspace</span><span>/</span><strong>{page}</strong></div><div className="topbar-right"><span className="environment">LOCAL DEMO</span><div className="avatar" title={user.email}>{name[0]}</div><SignOutButton onSignOut={onSignOut} signingOut={signingOut}/></div></header>
    <main className="content"><div className="page-header"><div><div className="eyebrow">✦ YOUR ONBOARDING WORKSPACE</div><h1>{page === 'Dashboard' ? `Welcome, ${name.split(' ')[0]}!` : page}</h1><p>{page === 'Dashboard' ? 'Everything you need to get started, all in one place.' : 'Your employee-specific onboarding workspace.'}</p></div><div className="employee-selector identity-card"><span>SIGNED IN AS</span><div><UserRound size={17}/><strong>{name}</strong></div><small>{employeeId} · {user.email}</small></div></div>
    {profileError && <div className="error" role="alert">{profileError}</div>}
    {page === 'Dashboard' && <><section className="hero"><div className="hero-text"><span className="hero-tag"><Sparkles size={14}/> YOUR AI-POWERED ONBOARDING COMPANION</span><h2>A smoother start.<br/>A smarter journey.</h2><p>From first-day questions to HR support, OnboardAI helps you find your way.</p><button onClick={() => navigate('AI Assistant')}>Explore AI Assistant <ArrowRight size={17}/></button></div><div className="hero-art"><Sparkles size={88}/></div></section><h2 className="section-title">Your workspace</h2><p className="section-subtitle">Quick access to your onboarding essentials.</p><div className="action-grid">{NAV.slice(1).map(([label, Icon], index) => <button className="action-card" key={label} onClick={() => navigate(label)}><div className={`action-icon tone-${index}`}><Icon size={24}/></div><h3>{label}</h3><p>{label === 'AI Assistant' ? 'Ask questions about HR policies and your onboarding.' : `Explore your ${label.toLowerCase()} information.`}</p><ArrowRight size={18} className="action-arrow"/></button>)}</div><section className="panel profile-card"><div className="panel-heading"><h2>Employee snapshot</h2><span className="pill">{employeeId}</span></div>{profile ? <div className="detail-grid">{Object.entries(profile).filter(([, value]) => ['string', 'number'].includes(typeof value)).map(([key, value]) => <div key={key}><small>{pretty(key)}</small><strong>{display(value)}</strong></div>)}</div> : <p className="muted">Loading employee profile...</p>}</section></>}
    {page === 'AI Assistant' && <Chat key={employeeId} employeeId={employeeId}/>}
    {panels.map(([key, title]) => <section className="panel" key={key}><div className="panel-heading"><h2>{title}</h2><span className="pill">{employeeId}</span></div>{loading ? <p className="muted">Loading records...</p> : records[key]?.error ? <p className="error">{String(records[key].error)}</p> : <DataTable data={records[key]?.data} empty="No records available for this employee."/>}</section>)}
    {page === 'My Checklist' && <Checklist key={employeeId} employeeId={employeeId}/>}
    {page === 'Support Center' && <SupportCenter key={employeeId} employeeId={employeeId}/>}
    <footer className="footer"><span>OnboardAI · RAG-Powered New Joiner Support Platform</span><span>Azure target architecture · Local development demo</span></footer></main></div>
  </div>;
}

// Administrator accounts have no employee workspace; admin actions are API-only (for example POST /ingest).
function AdminHome({ user, onSignOut, signingOut }) {
  return <div className="admin-shell">
    <header className="topbar"><div className="brand"><div className="brand-icon"><Sparkles size={23}/></div><div><strong>OnboardAI</strong><small>ADMINISTRATOR</small></div></div><div className="topbar-right"><span className="environment">LOCAL DEMO</span><SignOutButton onSignOut={onSignOut} signingOut={signingOut}/></div></header>
    <main className="content"><section className="panel"><div className="panel-heading"><div><h2>Administrator account</h2><p>Signed in as {user.email}</p></div><span className="pill">ADMIN</span></div>
      <p className="muted">This account is not linked to an employee, so there is no personal onboarding workspace. Administrative actions, such as rebuilding the knowledge-base index (POST /ingest), are available through the API with this session.</p></section></main>
  </div>;
}

function App() {
  const [auth, setAuth] = useState({ status: 'checking', user: null, notice: '' });
  const [signingOut, setSigningOut] = useState(false);

  useEffect(() => {
    let live = true;
    // Any 401 from a data request means the server-side session is gone: return to the login page.
    setUnauthorizedHandler(() => {
      setCsrfToken(null);
      setAuth((current) => current.status === 'authenticated' ? { status: 'anonymous', user: null, notice: SESSION_EXPIRED_NOTICE } : current);
    });
    // Restore an existing session after a page refresh (the cookie is HttpOnly; only the server can read it).
    authApi.me()
      .then(({ data }) => { if (live) { setCsrfToken(data.csrf_token); setAuth({ status: 'authenticated', user: data.user, notice: '' }); } })
      .catch(() => { if (live) setAuth({ status: 'anonymous', user: null, notice: '' }); });
    return () => { live = false; setUnauthorizedHandler(null); };
  }, []);

  const signedIn = (data) => {
    setCsrfToken(data.csrf_token);
    setAuth({ status: 'authenticated', user: data.user, notice: '' });
  };
  const signOut = () => {
    setSigningOut(true);
    authApi.logout().catch(() => {}).finally(() => {
      setCsrfToken(null);
      setSigningOut(false);
      setAuth({ status: 'anonymous', user: null, notice: SIGNED_OUT_NOTICE });
    });
  };

  if (auth.status === 'checking') return <div className="auth-loading" role="status"><LoaderCircle size={22} className="spin"/> Checking your session...</div>;
  if (auth.status !== 'authenticated') return <LoginPage onSignedIn={signedIn} notice={auth.notice}/>;
  if (!auth.user.employee_id) return <AdminHome user={auth.user} onSignOut={signOut} signingOut={signingOut}/>;
  return <Workspace key={auth.user.email} user={auth.user} onSignOut={signOut} signingOut={signingOut}/>;
}
export default App;
