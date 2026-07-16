import React from 'react'
import { Link } from 'react-router-dom'
import { api, downloadFile } from '../api.js'
import { Alert, Badge, Score, fmtDate, useAsync } from '../components.jsx'

export default function Tracker() {
  const { data, error, loading } = useAsync(() => api.get('/api/tracker'))

  if (loading) return <p>Loading…</p>
  if (error) return <Alert kind="error">{error}</Alert>

  return (
    <div>
      <div className="row between">
        <div><h1>Recruitment tracker</h1>
          <p className="sub">Stage 9 — the master tracker, updated automatically by every action.</p></div>
        <button className="btn" onClick={() => downloadFile('/api/export/tracker', 'tracker.xlsx')}>
          Export to Excel
        </button>
      </div>
      <div className="card" style={{ overflowX: 'auto' }}>
        <table className="data">
          <thead><tr>
            <th>Job</th><th>Candidate</th><th>Source</th><th>Received</th><th>Screened</th>
            <th>AI score</th><th>AI rec.</th><th>Recruiter</th><th>Status</th>
            <th>Interview</th><th>Offer</th><th>Joining</th><th>Next action</th><th>Owner</th><th>Updated</th>
          </tr></thead>
          <tbody>
            {data.map((row) => (
              <tr key={row.candidate_id}>
                <td className="small">{row.job_id}<br /><span className="muted">{row.job_title}</span></td>
                <td><Link to={`/candidates/${row.id}`}><b>{row.candidate_name || row.candidate_id}</b></Link>
                  <div className="small muted">{row.candidate_id}</div></td>
                <td className="small">{row.resume_source}</td>
                <td className="small">{fmtDate(row.date_received)}</td>
                <td className="small">{fmtDate(row.date_screened)}</td>
                <td>{row.ai_score ?? '—'}</td>
                <td><Badge value={row.ai_recommendation} /></td>
                <td><Badge value={row.recruiter_decision || null} /></td>
                <td><Badge value={row.screening_status} /></td>
                <td className="small">{row.interview_stage || '—'}<br />
                  <span className="muted">{row.interview_date ? fmtDate(row.interview_date) : ''}</span></td>
                <td className="small">{row.offer_status || '—'}</td>
                <td className="small">{row.joining_status || '—'}</td>
                <td className="small">{row.next_action || '—'}</td>
                <td className="small">{row.owner || '—'}</td>
                <td className="small">{fmtDate(row.last_updated)}</td>
              </tr>
            ))}
            {data.length === 0 && <tr><td colSpan={15} className="muted">No candidates yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}
