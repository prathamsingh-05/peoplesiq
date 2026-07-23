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
  strong: 'ok', adequate: 'info', weak: 'bad', insufficient_data: 'muted',
}

export function Badge({ value }) {
  if (value === null || value === undefined || value === '') return <span className="muted">—</span>
  const cls = BADGES[value] || 'info'
  return <span className={`badge ${cls}`}>{String(value).replaceAll('_', ' ')}</span>
}

const GUIDANCE_LABEL = { good: 'Strong match', review: 'Review closer', poor: 'Not a fit' }
const GUIDANCE_CLASS = { good: 'ok', review: 'warn', poor: 'bad' }

// Plain-language stand-in for a recruiter with no background in how the
// scoring works — a scannable label instead of "recommendation: recruiter_review".
export function GuidanceChip({ guidance }) {
  if (!guidance) return <span className="muted">—</span>
  return (
    <span className={`badge ${GUIDANCE_CLASS[guidance.tone] || 'info'}`} title={guidance.reason_in_plain_english}>
      {GUIDANCE_LABEL[guidance.tone] || guidance.headline}
    </span>
  )
}

// Animated circular score ring — counts up from 0 on every mount/value change
// so a freshly loaded leaderboard or a just-completed rescreen visibly
// "arrives" rather than popping in as static text.
export function Score({ value }) {
  const target = value === null || value === undefined ? null : Math.round(value)
  const [display, setDisplay] = useState(0)

  useEffect(() => {
    if (target === null) return undefined
    let raf
    const start = performance.now()
    const duration = 600
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - t, 3)
      setDisplay(Math.round(target * eased))
      if (t < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target])

  if (target === null) return <span className="muted">—</span>
  const cls = target >= 70 ? 'hi' : target >= 45 ? 'mid' : 'lo'
  return (
    <span className={`score-ring ${cls}`} style={{ '--pct': target }}>
      <span className="score-ring-fill" />
      <span className="score-ring-num">{display}</span>
    </span>
  )
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

export function Spinner({ label = 'Loading…', inline = false }) {
  return (
    <div className={inline ? 'spinner-wrap inline' : 'spinner-wrap'}>
      <span className="spinner" aria-hidden="true" />
      {label && <span className="small muted">{label}</span>}
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
