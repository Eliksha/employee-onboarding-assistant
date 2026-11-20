import { useCallback, useEffect, useState } from 'react';
import { LayoutDashboard, Bot, ClipboardCheck, CalendarDays, Laptop, Headset, Sparkles, Menu, X, Send, RefreshCw, ArrowRight, UserRound, ShieldCheck } from 'lucide-react';
import { employeeApi } from './api';
import './App.css';

const EMPLOYEES = ['EMP001', 'EMP002', 'EMP003'];
const NAV = [
  ['Dashboard', LayoutDashboard], ['AI Assistant', Bot], ['My Checklist', ClipboardCheck],
  ['Leave & Payroll', CalendarDays], ['My Assets', Laptop], ['Support Center', Headset],
];
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

function Chat({ employeeId }) {
  const [history, setHistory] = useState([]);
  const [question, setQuestion] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    try { const response = await employeeApi.history(employeeId); setHistory(asList(response.data).reverse()); setError(''); }
    catch (err) { setHistory([]); setError(err.response?.data?.detail ?? 'Could not load chat history. Check the FastAPI server.'); }
  }, [employeeId]);
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
    {history.map((message, index) => <div className="exchange" key={message.id ?? index}><div className="bubble question">{message.question}</div><div className="bubble answer"><div className="answer-label"><Sparkles size={15}/> OnboardAI</div><p>{message.answer}</p>{message.sources && <small>Sources: {typeof message.sources === 'string' ? message.sources : JSON.stringify(message.sources)}</small>}</div></div>)}</div>
    {error && <p className="error" role="alert">{String(error)}</p>}
    <form className="chat-form" onSubmit={send}><input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask a question about onboarding..." aria-label="Chat question" maxLength={2000}/><button disabled={busy || !question.trim()} type="submit"><Send size={18}/>{busy ? 'Sending...' : 'Send'}</button></form>
    <p className="disclaimer">Demo only · Synthetic employee data · Responses may require HR verification.</p>
  </section>;
}


function Checklist({ employeeId }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState({});
  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await employeeApi.checklist(employeeId);
      setItems(asList(response.data));
    } catch (err) {
      setItems([]);
      setError(err.response?.data?.detail ?? 'Could not load checklist.');
    } finally {
      setLoading(false);
    }
  }, [employeeId]);
  useEffect(() => { load(); }, [load]);

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

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await employeeApi.tickets(employeeId);
      setTickets(asList(response.data));
    } catch (err) {
      setTickets([]);
      setError(err.response?.data?.detail ?? 'Could not load support tickets.');
    } finally {
      setLoading(false);
    }
  }, [employeeId]);

  useEffect(() => { load(); }, [load]);

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

function App() {
  const [employeeId, setEmployeeId] = useState('EMP001');
  const [page, setPage] = useState('Dashboard');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [profile, setProfile] = useState(null);
  const [profileError, setProfileError] = useState('');
  const [records, setRecords] = useState({});
  const [loading, setLoading] = useState(false);
  const navigate = (next) => { setPage(next); setSidebarOpen(false); };
  useEffect(() => { let live = true; setProfile(null); setProfileError(''); employeeApi.profile(employeeId).then(({ data }) => { if (live) setProfile(unwrap(data)); }).catch(() => { if (live) setProfileError('Profile unavailable. Start the FastAPI backend.'); }); return () => { live = false; }; }, [employeeId]);
  useEffect(() => {
    if (page === 'Dashboard' || page === 'AI Assistant') return;
    const tasks = page === 'Leave & Payroll' ? [['leave', employeeApi.leave], ['payroll', employeeApi.payroll]] : page === 'My Checklist' ? [] : page === 'My Assets' ? [['assets', employeeApi.assets]] : page === 'Support Center' ? [] : [];
    let live = true; setLoading(true); setRecords({});
    Promise.all(tasks.map(async ([key, fn]) => { try { const result = await fn(employeeId); return [key, { data: result.data }]; } catch (error) { return [key, { error: error.response?.data?.detail ?? 'Unable to load records.' }]; } })).then((entries) => { if (live) { setRecords(Object.fromEntries(entries)); setLoading(false); } });
    return () => { live = false; };
  }, [employeeId, page]);
  const name = profile?.full_name ?? profile?.name ?? employeeId;
  const panels = page === 'Leave & Payroll' ? [['leave', 'Leave Balances'], ['payroll', 'Payroll Calendar']] : page === 'My Checklist' ? [] : page === 'My Assets' ? [['assets', 'Assigned Assets']] : page === 'Support Center' ? [] : [];
  return <div className="app-shell">
    {sidebarOpen && <button className="overlay" aria-label="Close menu" onClick={() => setSidebarOpen(false)}/>}
    <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}><div className="brand"><div className="brand-icon"><Sparkles size={23}/></div><div><strong>OnboardAI</strong><small>NEW JOINER PLATFORM</small></div><button className="mobile-close" onClick={() => setSidebarOpen(false)} aria-label="Close menu"><X size={20}/></button></div><div className="nav-caption">WORKSPACE</div><nav>{NAV.map(([label, Icon]) => <button key={label} className={`nav-item ${page === label ? 'active' : ''}`} onClick={() => navigate(label)}><Icon size={19}/>{label}</button>)}</nav><div className="sidebar-footer"><ShieldCheck size={16}/> Synthetic-data demonstration</div></aside>
    <div className="main-area"><header className="topbar"><div className="breadcrumb"><button className="menu-button" aria-label="Open menu" onClick={() => setSidebarOpen(true)}><Menu size={22}/></button><span>Workspace</span><span>/</span><strong>{page}</strong></div><div className="topbar-right"><span className="environment">LOCAL DEMO</span><div className="avatar">{name[0]}</div></div></header>
    <main className="content"><div className="page-header"><div><div className="eyebrow">✦ YOUR ONBOARDING WORKSPACE</div><h1>{page === 'Dashboard' ? `Welcome, ${name.split(' ')[0]}!` : page}</h1><p>{page === 'Dashboard' ? 'Everything you need to get started, all in one place.' : 'Your employee-specific onboarding workspace.'}</p></div><label className="employee-selector"><span>VIEWING AS · DEMO ONLY</span><div><UserRound size={17}/><select value={employeeId} onChange={(event) => setEmployeeId(event.target.value)}>{EMPLOYEES.map((id) => <option value={id} key={id}>{id}</option>)}</select></div></label></div>
    {profileError && <div className="error" role="alert">{profileError}</div>}
    {page === 'Dashboard' && <><section className="hero"><div className="hero-text"><span className="hero-tag"><Sparkles size={14}/> YOUR AI-POWERED ONBOARDING COMPANION</span><h2>A smoother start.<br/>A smarter journey.</h2><p>From first-day questions to HR support, OnboardAI helps you find your way.</p><button onClick={() => navigate('AI Assistant')}>Explore AI Assistant <ArrowRight size={17}/></button></div><div className="hero-art"><Sparkles size={88}/></div></section><h2 className="section-title">Your workspace</h2><p className="section-subtitle">Quick access to your onboarding essentials.</p><div className="action-grid">{NAV.slice(1).map(([label, Icon], index) => <button className="action-card" key={label} onClick={() => navigate(label)}><div className={`action-icon tone-${index}`}><Icon size={24}/></div><h3>{label}</h3><p>{label === 'AI Assistant' ? 'Ask questions about HR policies and your onboarding.' : `Explore your ${label.toLowerCase()} information.`}</p><ArrowRight size={18} className="action-arrow"/></button>)}</div><section className="panel profile-card"><div className="panel-heading"><h2>Employee snapshot</h2><span className="pill">{employeeId}</span></div>{profile ? <div className="detail-grid">{Object.entries(profile).filter(([key, value]) => ['string', 'number'].includes(typeof value)).map(([key, value]) => <div key={key}><small>{pretty(key)}</small><strong>{display(value)}</strong></div>)}</div> : <p className="muted">Loading employee profile...</p>}</section></>}
    {page === 'AI Assistant' && <Chat key={employeeId} employeeId={employeeId}/>}
    {panels.map(([key, title]) => <section className="panel" key={key}><div className="panel-heading"><h2>{title}</h2><span className="pill">{employeeId}</span></div>{loading ? <p className="muted">Loading records...</p> : records[key]?.error ? <p className="error">{String(records[key].error)}</p> : <DataTable data={records[key]?.data} empty="No records available for this employee."/>}</section>)}
    {page === 'My Checklist' && <Checklist key={employeeId} employeeId={employeeId}/>}
    {page === 'Support Center' && <SupportCenter key={employeeId} employeeId={employeeId}/>}
    <footer className="footer"><span>OnboardAI · RAG-Powered New Joiner Support Platform</span><span>Azure target architecture · Local development demo</span></footer></main></div>
  </div>;
}
export default App;
