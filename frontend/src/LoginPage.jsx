import { useState } from 'react';
import { Eye, EyeOff, LoaderCircle, LockKeyhole, Mail, ShieldCheck, Sparkles } from 'lucide-react';
import { authApi } from './api';
import { loginErrorMessage } from './auth';

export default function LoginPage({ onSignedIn, notice }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async (event) => {
    event.preventDefault();
    if (busy) return;
    if (!email.trim() || !password) {
      setError('Enter your email address and password.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const { data } = await authApi.login(email.trim(), password);
      setPassword('');
      onSignedIn(data);
    } catch (err) {
      setPassword('');
      setError(loginErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return <main className="login-shell">
    <section className="login-brand-panel" aria-hidden="true">
      <div className="brand login-brand"><div className="brand-icon"><Sparkles size={23}/></div><div><strong>OnboardAI</strong><small>NEW JOINER PLATFORM</small></div></div>
      <h2>A smoother start.<br/>A smarter journey.</h2>
      <p>Policy answers with sources, your onboarding checklist, leave, assets and support - in one place.</p>
    </section>
    <section className="login-card" aria-labelledby="login-title">
      <div className="eyebrow">✦ SECURE SIGN-IN</div>
      <h1 id="login-title">Welcome back</h1>
      <p className="login-subtitle">Sign in with your work email to open your onboarding workspace.</p>
      {notice && <p className="login-notice" role="status">{notice}</p>}
      <form className="login-form" onSubmit={submit} noValidate>
        <label htmlFor="login-email">Email address</label>
        <div className="login-input"><Mail size={17}/><input id="login-email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@example.com" maxLength={254} disabled={busy} required/></div>
        <label htmlFor="login-password">Password</label>
        <div className="login-input"><LockKeyhole size={17}/><input id="login-password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Your password" maxLength={1024} disabled={busy} required/>
          <button type="button" className="password-toggle" onClick={() => setShowPassword((v) => !v)} aria-label={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword}>{showPassword ? <EyeOff size={17}/> : <Eye size={17}/>}</button>
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        <button type="submit" className="login-submit" disabled={busy}>{busy ? <><LoaderCircle size={17} className="spin"/> Signing in...</> : 'Sign In'}</button>
      </form>
      <p className="disclaimer login-footnote"><ShieldCheck size={14}/> Demo with synthetic employee data. Accounts are provisioned by an administrator.</p>
    </section>
  </main>;
}
