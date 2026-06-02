import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { ApiError, logoutUser } from '../lib/api'
import { clearStoredTokens, getStoredTokens, subscribeAuthChange } from '../lib/auth'

const navItems = [
  { to: '/home', label: 'Home' },
  { to: '/insert', label: 'Insert' },
  { to: '/view', label: 'View' },
  { to: '/jobs', label: 'Jobs' },
  { to: '/quiz', label: 'Quiz' },
  { to: '/progress', label: 'Progress' },
]

export function AppShell() {
  const [isLoggedIn, setIsLoggedIn] = useState(Boolean(getStoredTokens()?.access_token))
  const [statusMessage, setStatusMessage] = useState('')

  useEffect(() => {
    const unsubscribe = subscribeAuthChange(() => {
      setIsLoggedIn(Boolean(getStoredTokens()?.access_token))
    })
    return unsubscribe
  }, [])

  const onLogout = async () => {
    const tokens = getStoredTokens()
    if (!tokens?.access_token) {
      clearStoredTokens()
      return
    }

    try {
      await logoutUser(tokens.access_token)
      setStatusMessage('Logged out')
    } catch (error) {
      if (error instanceof ApiError) {
        setStatusMessage(`Logout request failed: ${error.message}`)
      } else {
        setStatusMessage('Logout request failed')
      }
    } finally {
      clearStoredTokens()
    }
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="header-top">
          <p className="kicker">JP-EN Learning</p>
          <h1 className="title">Study Console</h1>
        </div>
        <nav className="app-nav" aria-label="Primary">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `nav-chip ${isActive ? 'nav-chip--active' : ''}`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="auth-row">
          <span className="auth-state">{isLoggedIn ? 'Signed in' : 'Signed out'}</span>
          {isLoggedIn ? (
            <button type="button" className="btn btn--ghost" onClick={onLogout}>
              Logout
            </button>
          ) : (
            <div className="inline-actions">
              <NavLink to="/login" className="btn btn--ghost">
                Login
              </NavLink>
              <NavLink to="/register" className="btn">
                Register
              </NavLink>
            </div>
          )}
        </div>
        {statusMessage && <p className="status-line">{statusMessage}</p>}
      </header>

      <main className="content-wrap">
        <Outlet />
      </main>
    </div>
  )
}
