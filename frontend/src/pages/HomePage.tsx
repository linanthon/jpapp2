import { useEffect, useState } from 'react'
import { getQuizHome } from '../lib/api'

export function HomePage() {
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>('loading')
  const [bookCount, setBookCount] = useState<number>(0)

  useEffect(() => {
    const controller = new AbortController()

    getQuizHome(controller.signal)
      .then((data) => {
        setBookCount(data.all_books.length)
        setStatus('ok')
      })
      .catch(() => {
        setStatus('error')
      })

    return () => controller.abort()
  }, [])

  return (
    <section className="panel">
      <h2 className="panel-title">Routing and Layout Baseline Is Live</h2>
      <p className="panel-copy">
        The app now uses React Router navigation with a shared shell. This page
        also validates API connectivity with the backend.
      </p>

      <div className="stat-row">
        <article className="stat-card">
          <h3>Backend Link</h3>
          <p>
            {status === 'loading' && 'Checking API...'}
            {status === 'ok' && 'Connected'}
            {status === 'error' && 'Unavailable (login/CORS/server may be missing)'}
          </p>
        </article>
        <article className="stat-card">
          <h3>Books Seen</h3>
          <p>{status === 'ok' ? bookCount : '-'}</p>
        </article>
      </div>
    </section>
  )
}
