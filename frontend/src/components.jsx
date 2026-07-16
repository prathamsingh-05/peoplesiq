import React, { useEffect, useState } from 'react'

const BADGES = {
  shortlist: 'ok', recruiter_review: 'warn', do_not_shortlist: 'bad',
  met: 'ok', partially_met: 'warn', not_met: 'bad',
  confirmed: 'ok', partial: 'info', no_evidence: 'muted',
  contradictory: 'bad', needs_verification: 'warn',
  high: 'ok', medium: 'warn', low: 'muted',
  draft: 'muted', approved: 'info', sent: 'ok', failed: 'bad', cancelled: 'muted',
  active: 'ok', paused: 'warn', stopped: 'bad', completed: 'info',
  pending_approval: 'warn',
  received: 'muted', screened: 'info', awaiting_review: 'warn',
  shortlisted: 'ok', rejected: 'bad', on_hold: 'warn', duplicate: 'muted',
  unreadable: 'bad', screening_call_done: 'info', submitted_to_hm: 'info',
  interview_scheduled: 'info', interview_complete: 'info', offer_made: 'info',
  offer_accepted: 'ok', offer_declined: 'bad', offer_withdrawn: 'bad',
  joined: 'ok', handover_complete: 'ok', withdrawn: 'muted', unreachable: 'warn',
  processed: 'ok', error: 'bad',
  pending_review: 'warn', complete: 'ok',
}

export function Badge({ value }) {
  if (value === null || value === undefined || value === '') return <span className="muted">—</span>
  const cls = BADGES[value] || 'info'
  return <span className={`badge ${cls}`}>{String(value).replaceAll('_', ' ')}</span>
}

export function Score({ value }) {
  if (value === null || value === undefined) return <span className="muted">—</span>
  const cls = value >= 70 ? 'hi' : value >= 45 ? 'mid' : 'lo'
  return <span className={`score-ring ${cls}`}>{Math.round(value)}</span>
}

export function Alert({ kind = 'info', children, onClose }) {
  if (!children) return null
  return (
    <div className={`alert ${kind}`}>
      {children}
      {onClose && <button className="btn sm secondary" style={{ marginLeft: 10 }} onClick={onClose}>✕</button>}
    </div>
  )
}

export function useAsync(fn, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const reload = React.useCallback(() => {
    setState((s) => ({ ...s, loading: true }))
    fn().then(
      (data) => setState({ data, error: null, loading: false }),
      (error) => setState({ data: null, error: error.message, loading: false }),
    )
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { reload() }, [reload])
  return { ...state, reload }
}

export function fmtDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

export function fmtDay(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
  })
}
