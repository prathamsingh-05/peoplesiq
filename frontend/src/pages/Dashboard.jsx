import React from 'react'
import { Link } from 'react-router-dom'
import { api, downloadFile } from '../api.js'
import { Alert, useAsync } from '../components.jsx'

const TILES = [
  ['total_resumes_received', 'Resumes received'],
  ['total_resumes_screened', 'Resumes screened'],
  ['unreadable_or_duplicates', 'Unreadable / duplicates'],
  ['ai_recommended', 'AI recommended'],
  ['recruiter_shortlisted', 'Recruiter shortlisted'],
  ['rejected', 'Rejected'],
  ['awaiting_review', 'Awaiting review'],
  ['interviews_scheduled', 'Interviews scheduled'],
  ['offers_made', 'Offers made'],
  ['offers_accepted', 'Offers accepted'],
  ['expected_joiners', 'Expected joiners'],
  ['joined', 'Joined'],
]

export default function Dashboard() {
  const { data, error, loading } = useAsync(() => api.get('/api/dashboard'))
  const health = useAsync(() => api.get('/api/health'))

  if (loading) return <p>Loading…</p>
  if (error) return <Alert kind="error">{error}</Alert>

  return (
    <div>
      <h1>Dashboard</h1>
      <p className="sub">Live view of the recruitment funnel across all jobs.</p>

      {health.data && health.data.ai_engine !== 'claude' && (
        <Alert kind="info">
          The AI engine is running in <b>deterministic fallback mode</b> (no
          ANTHROPIC_API_KEY configured). Screening still works, but evidence
          analysis is keyword-based and every result routes to recruiter review.
        </Alert>
      )}
      {health.data && health.data.email_mode === 'draft-only' && (
        <Alert kind="info">
          Email is in <b>draft-only mode</b> — nothing is ever sent until SMTP is
          configured and enabled. All drafts stay in the outbox.
        </Alert>
      )}

      <div className="grid cols-4">
        {TILES.map(([key, label]) => (
          <div className="card tile" key={key}>
            <div className="num">{data[key] ?? 0}</div>
            <div className="lbl">{label}</div>
          </div>
        ))}
      </div>

      <div className="grid cols-2" style={{ marginTop: 4 }}>
        <div className="card tile">
          <div className="num">
            {data.ai_recruiter_agreement_rate === null ? '—' : `${data.ai_recruiter_agreement_rate}%`}
          </div>
          <div className="lbl">
            AI ↔ recruiter decision agreement ({data.decided_count} decided)
          </div>
        </div>
        <div className="card tile">
          <div className="num">{data.flagged_for_fairness_review}</div>
          <div className="lbl">
            Profiles flagged for fairness review — <Link to="/governance">review queue</Link>
          </div>
        </div>
      </div>

      <div className="card row between">
        <div>
          <h3>Master recruitment tracker</h3>
          <span className="muted small">All candidates, all jobs, every tracker field — as Excel.</span>
        </div>
        <button className="btn" onClick={() => downloadFile('/api/export/tracker', 'tracker.xlsx')}>
          Export tracker (.xlsx)
        </button>
      </div>
    </div>
  )
}
