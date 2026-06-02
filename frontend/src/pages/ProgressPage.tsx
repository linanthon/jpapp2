import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, type ProgressResponse, getProgress } from '../lib/api'
import { getAccessToken } from '../lib/auth'

function formatMetric(value: unknown) {
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : value.toFixed(1)
  }
  return String(value)
}

export function ProgressPage() {
  const token = getAccessToken()
  const [status, setStatus] = useState<'idle' | 'loading' | 'error' | 'ok'>(
    token ? 'loading' : 'idle',
  )
  const [progress, setProgress] = useState<ProgressResponse>({})
  const [errorMessage, setErrorMessage] = useState('')

  useEffect(() => {
    if (!token) {
      return
    }

    getProgress(token)
      .then((data) => {
        setProgress(data)
        setStatus('ok')
      })
      .catch((error: unknown) => {
        setStatus('error')
        if (error instanceof ApiError) {
          setErrorMessage(error.message)
          return
        }
        setErrorMessage('Failed to load progress metrics.')
      })
  }, [token])

  return (
    <section className="panel">
      <p className="eyebrow">Progress</p>
      <h2 className="panel-title">Study Stats</h2>
      <p className="panel-copy">
        Track your JLPT and total completion metrics from the authenticated API.
      </p>

      {!token && (
        <div className="notice-wrap">
          <p className="notice notice--error">Login is required to view progress analytics.</p>
          <Link className="btn" to="/login">
            Go To Login
          </Link>
        </div>
      )}

      {token && status === 'loading' && <p className="notice">Loading progress...</p>}
      {token && status === 'error' && <p className="notice notice--error">{errorMessage}</p>}
      {token && status === 'ok' && Object.keys(progress).length === 0 && (
        <p className="notice">No progress data returned yet.</p>
      )}

      {token && status === 'ok' && Object.keys(progress).length > 0 && (
        <div className="stat-row">
          {Object.entries(progress).map(([bucket, metrics]) => (
            <article className="stat-card" key={bucket}>
              <h3>{bucket.toUpperCase()}</h3>
              <ul className="metric-list">
                {Object.entries(metrics).map(([name, value]) => (
                  <li key={name}>
                    <span>{name}</span>
                    <strong>{formatMetric(value)}</strong>
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
