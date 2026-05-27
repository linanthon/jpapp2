import { useEffect, useState } from 'react'
import { ApiError, getQuizHome } from '../lib/api'

export function HomePage() {
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>('loading')
  const [bookCount, setBookCount] = useState<number>(0)
  const [statusDetail, setStatusDetail] = useState('')

  useEffect(() => {
    const controller = new AbortController()

    getQuizHome(controller.signal)
      .then((data) => {
        setBookCount(data.all_books.length)
        setStatusDetail('')
        setStatus('ok')
      })
      .catch((error: unknown) => {
        if (error instanceof ApiError) {
          if (error.status === 404) {
            setStatusDetail('API route not found from this origin. In preview, set VITE_API_ORIGIN to backend URL.')
          } else {
            setStatusDetail(error.message)
          }
        } else {
          setStatusDetail('Network/CORS failure. Check backend server and allowed origins.')
        }
        setStatus('error')
      })

    return () => controller.abort()
  }, [])

  return (
    <section className="panel">
      <p className="eyebrow">Home</p>
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
          {status === 'error' && statusDetail && <p>{statusDetail}</p>}
        </article>
        <article className="stat-card">
          <h3>Books Seen</h3>
          <p>{status === 'ok' ? bookCount : '-'}</p>
        </article>
      </div>
    </section>
  )
}
