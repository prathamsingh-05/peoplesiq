import React, { useEffect, useState } from 'react'
import { NavLink, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { api, clearToken, getToken } from './api.js'
import Login from './pages/Login.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Jobs from './pages/Jobs.jsx'
import JobDetail from './pages/JobDetail.jsx'
import CandidateDetail from './pages/CandidateDetail.jsx'
import Tracker from './pages/Tracker.jsx'
import Outbox from './pages/Outbox.jsx'
import ContentLibrary from './pages/ContentLibrary.jsx'
import Governance from './pages/Governance.jsx'

export const UserContext = React.createContext(null)

export default function App() {
  const [user, setUser] = useState(null)
  const [checked, setChecked] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    if (!getToken()) { setChecked(true); return }
    api.get('/api/auth/me')
      .then(setUser)
      .catch(() => clearToken())
      .finally(() => setChecked(true))
  }, [])

  if (!checked) return null
  if (!user) return <Login onLogin={setUser} />

  const logout = () => { clearToken(); setUser(null); navigate('/login') }

  return (
    <UserContext.Provider value={user}>
      <div className="layout">
        <aside className="sidebar">
          <div className="brand">People IQ<small>Recruiter Agent</small></div>
          <nav>
            <NavLink to="/dashboard">Dashboard</NavLink>
            <NavLink to="/jobs">Jobs & Screening</NavLink>
            <NavLink to="/tracker">Tracker</NavLink>
            <NavLink to="/outbox">Email Outbox</NavLink>
            <NavLink to="/content">Content Library</NavLink>
            <NavLink to="/governance">Governance</NavLink>
          </nav>
          <div className="foot">
            {user.full_name}<br /><span className="badge info">{user.role.replaceAll('_', ' ')}</span>
            <br /><button onClick={logout}>Sign out</button>
          </div>
        </aside>
        <main className="main">
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/login" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/jobs" element={<Jobs />} />
            <Route path="/jobs/:jobId" element={<JobDetail />} />
            <Route path="/candidates/:candidateId" element={<CandidateDetail />} />
            <Route path="/tracker" element={<Tracker />} />
            <Route path="/outbox" element={<Outbox />} />
            <Route path="/content" element={<ContentLibrary />} />
            <Route path="/governance" element={<Governance />} />
          </Routes>
        </main>
      </div>
    </UserContext.Provider>
  )
}
