import React, { useContext, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import { Alert, Badge, fmtDate, useAsync } from '../components.jsx'
import { UserContext } from '../App.jsx'

export default function Governance() {
  const user = useContext(UserContext)
  const [tab, setTab] = useState('audit')
  return (
    <div>
      <h1>Governance</h1>
      <p className="sub">Audit trail, fairness review queue and user administration —
        the accountability layer required by §12–15 of the brief.</p>
      <div className="tabs">
        <button className={tab === 'audit' ? 'active' : ''} onClick={() => setTab('audit')}>Audit log</button>
        <button className={tab === 'fairness' ? 'active' : ''} onClick={() => setTab('fairness')}>Fairness review</button>
        {user.role === 'admin' &&
          <button className={tab === 'users' ? 'active' : ''} onClick={() => setTab('users')}>Users</button>}
      </div>
      {tab === 'audit' && <AuditTab />}
      {tab === 'fairness' && <FairnessTab />}
      {tab === 'users' && user.role === 'admin' && <UsersTab />}
    </div>
  )
}

function AuditTab() {
  const [action, setAction] = useState('')
  const logs = useAsync(() => api.get(`/api/admin/audit-logs?limit=300${action ? `&action=${action}` : ''}`), [action])
  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 10 }}>
        {['', 'auth', 'scorecard', 'screening', 'decision', 'email', 'sequence', 'interview'].map((a) => (
          <button key={a} className={`btn sm ${action === a ? '' : 'secondary'}`}
                  onClick={() => setAction(a)}>{a || 'all'}</button>
        ))}
      </div>
      {logs.loading ? <p>Loading…</p> : (
        <table className="data">
          <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Entity</th><th>Details</th></tr></thead>
          <tbody>
            {logs.data.map((row) => (
              <tr key={row.id}>
                <td className="small">{fmtDate(row.created_at)}</td>
                <td>{row.username}</td>
                <td><Badge value={row.action.split('.')[0]} /> <span className="small">{row.action}</span></td>
                <td className="small">{row.entity_type} #{row.entity_id}</td>
                <td className="small muted">{JSON.stringify(row.details)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function FairnessTab() {
  const queue = useAsync(() => api.get('/api/admin/fairness-review-queue'))
  const [error, setError] = useState('')
  const complete = (id) => api.post(`/api/admin/fairness-review/${id}/complete`)
    .then(() => queue.reload()).catch((e) => setError(e.message))
  return (
    <div className="card">
      <p className="small muted">A random sample of AI "do not shortlist" recommendations is
        automatically flagged here for mandatory human review — the periodic check that keeps
        the AI honest (§15).</p>
      <Alert kind="error" onClose={() => setError('')}>{error}</Alert>
      {queue.loading ? <p>Loading…</p> : (
        <table className="data">
          <thead><tr><th>Candidate</th><th>Job</th><th>AI recommendation</th>
            <th>Recruiter decision</th><th></th></tr></thead>
          <tbody>
            {queue.data.map((row) => (
              <tr key={row.id}>
                <td><Link to={`/candidates/${row.id}`}><b>{row.full_name || row.candidate_code}</b></Link></td>
                <td>{row.job_title}</td>
                <td><Badge value={row.ai_recommendation} /></td>
                <td><Badge value={row.recruiter_decision || null} /></td>
                <td><button className="btn sm" onClick={() => complete(row.id)}>Mark reviewed</button></td>
              </tr>
            ))}
            {queue.data.length === 0 &&
              <tr><td colSpan={5} className="muted">Queue is empty — nothing awaiting review.</td></tr>}
          </tbody>
        </table>
      )}
    </div>
  )
}

function UsersTab() {
  const users = useAsync(() => api.get('/api/auth/users'))
  const [form, setForm] = useState({ username: '', email: '', full_name: '', password: '', role: 'recruiter' })
  const [error, setError] = useState('')
  const act = (fn) => fn().then(() => users.reload()).catch((e) => setError(e.message))
  return (
    <div>
      <div className="card">
        <h2>Create user</h2>
        <Alert kind="error" onClose={() => setError('')}>{error}</Alert>
        <div className="grid cols-3">
          <label className="field">Username<input value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })} /></label>
          <label className="field">Full name<input value={form.full_name}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></label>
          <label className="field">Email<input type="email" value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
          <label className="field">Password (min 10 chars)<input type="password" value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
          <label className="field">Role
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              <option value="recruiter">Recruiter</option>
              <option value="hiring_manager">Hiring manager (read-only)</option>
              <option value="admin">Admin</option>
            </select></label>
        </div>
        <button className="btn" onClick={() => act(() => api.post('/api/auth/users', form))}>Create user</button>
      </div>
      <div className="card">
        {users.loading ? <p>Loading…</p> : (
          <table className="data">
            <thead><tr><th>Username</th><th>Name</th><th>Email</th><th>Role</th>
              <th>Active</th><th>Last login</th><th></th></tr></thead>
            <tbody>
              {users.data.map((u) => (
                <tr key={u.id}>
                  <td>{u.username}</td><td>{u.full_name}</td><td>{u.email}</td>
                  <td><Badge value={u.role} /></td>
                  <td>{u.is_active ? '✓' : '—'}</td>
                  <td className="small">{u.last_login ? fmtDate(u.last_login) : 'never'}</td>
                  <td><button className="btn sm secondary" onClick={() => act(() =>
                    api.post(`/api/auth/users/${u.id}/toggle-active`))}>
                    {u.is_active ? 'Disable' : 'Enable'}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
