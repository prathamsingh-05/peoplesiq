import React, { useState } from 'react'
import { api, setToken } from '../api.js'
import { Alert } from '../components.jsx'

export default function Login({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true); setError('')
    try {
      const result = await api.post('/api/auth/login', { username, password })
      setToken(result.access_token)
      onLogin(result.user)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <h1>People IQ</h1>
        <p className="sub">Recruiter Agent — sign in to continue</p>
        <Alert kind="error">{error}</Alert>
        <label className="field">Username
          <input value={username} onChange={(e) => setUsername(e.target.value)}
                 autoComplete="username" required />
        </label>
        <label className="field">Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                 autoComplete="current-password" required />
        </label>
        <button className="btn" disabled={busy} style={{ width: '100%' }}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
        <p className="small muted" style={{ marginTop: 14 }}>
          Internal tool — all actions are audit-logged. Final hiring decisions
          always rest with a human recruiter.
        </p>
      </form>
    </div>
  )
}
