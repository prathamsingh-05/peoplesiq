import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import { Alert, Badge, fmtDate, useAsync } from '../components.jsx'

export default function Outbox() {
  const [filter, setFilter] = useState('')
  const emails = useAsync(
    () => api.get(`/api/emails/outbox${filter ? `?status=${filter}` : ''}`), [filter])
  const config = useAsync(() => api.get('/api/emails/config'))
  const [error, setError] = useState('')
  const act = (fn) => fn().then(() => emails.reload()).catch((e) => setError(e.message))

  return (
    <div>
      <h1>Email outbox</h1>
      <p className="sub">Every candidate communication across all jobs — drafts, approvals,
        scheduled keep-warm sends and delivery status.</p>
      {config.data && (
        <Alert kind={config.data.sending_enabled ? 'success' : 'info'}>
          Mode: <b>{config.data.mode}</b>{!config.data.sending_enabled &&
            ' — approved emails queue safely; nothing leaves the system until SMTP is configured and enabled.'}
        </Alert>
      )}
      <Alert kind="error" onClose={() => setError('')}>{error}</Alert>
      <div className="row" style={{ marginBottom: 10 }}>
        {['', 'draft', 'approved', 'sent', 'failed', 'cancelled'].map((s) => (
          <button key={s} className={`btn sm ${filter === s ? '' : 'secondary'}`}
                  onClick={() => setFilter(s)}>{s || 'all'}</button>
        ))}
      </div>
      <div className="card">
        {emails.loading ? <p>Loading…</p> : (
          <table className="data">
            <thead><tr><th>Candidate</th><th>Template</th><th>Subject</th><th>To</th>
              <th>Status</th><th>Scheduled</th><th>Sent</th><th></th></tr></thead>
            <tbody>
              {emails.data.map((m) => (
                <tr key={m.id}>
                  <td><Link to={`/candidates/${m.candidate_id}`}>#{m.candidate_id}</Link></td>
                  <td><Badge value={m.template_key} /></td>
                  <td className="small">{m.subject}</td>
                  <td className="small">{m.to_address || '—'}</td>
                  <td><Badge value={m.status} /></td>
                  <td className="small">{m.scheduled_for ? fmtDate(m.scheduled_for) : '—'}</td>
                  <td className="small">{m.sent_at ? fmtDate(m.sent_at) : '—'}</td>
                  <td>
                    {m.status === 'draft' &&
                      <button className="btn sm" onClick={() => act(() =>
                        api.post(`/api/emails/${m.id}/approve`))}>Approve</button>}
                  </td>
                </tr>
              ))}
              {emails.data.length === 0 && <tr><td colSpan={8} className="muted">No emails.</td></tr>}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
