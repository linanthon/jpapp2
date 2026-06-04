import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ApiError,
  checkAdminAccess,
  getAdminJobDetail,
  type AdminJobDetailResponse,
  type AdminJobType,
} from '../lib/api'
import { getAccessToken } from '../lib/auth'

function stringifyValue(value: unknown) {
  if (value === null || value === undefined || value === '') {
    return '-'
  }
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch {
      return String(value)
    }
  }
  return String(value)
}

function stripExtension(name: string) {
  if (!name) {
    return ''
  }
  return name.replace(/\.[^/.]+$/, '')
}

function isDetailJobType(value: string): value is Exclude<AdminJobType, 'all'> {
  return value === 'book_batch' || value === 'tts' || value === 'scrape'
}

export function JobDetailPage() {
  const navigate = useNavigate()
  const params = useParams()
  const token = getAccessToken()
  const jobType = params.jobType ?? ''
  const jobId = params.jobId ?? ''

  const [status, setStatus] = useState<'idle' | 'loading' | 'ok' | 'error'>(
    token && jobType && jobId ? 'loading' : 'idle',
  )
  const [isAdmin, setIsAdmin] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [detail, setDetail] = useState<AdminJobDetailResponse | null>(null)

  useEffect(() => {
    if (!token || !jobId || !isDetailJobType(jobType)) {
      return
    }

    const loadDetail = async () => {
      setStatus('loading')
      setErrorMessage('')

      try {
        const adminFlag = await checkAdminAccess(token)
        if (!adminFlag) {
          setIsAdmin(false)
          setDetail(null)
          setStatus('ok')
          return
        }

        setIsAdmin(true)
        const payload = await getAdminJobDetail(token, jobType, jobId)
        setDetail(payload)
        setStatus('ok')
      } catch (error: unknown) {
        setStatus('error')
        if (error instanceof ApiError) {
          setErrorMessage(error.message)
        } else {
          setErrorMessage('Failed to load job details.')
        }
      }
    }

    void loadDetail()
  }, [token, jobType, jobId])

  const detailEntries = useMemo(() => {
    if (!detail) {
      return [] as Array<[string, unknown]>
    }

    if (detail.job_type === 'book_batch') {
      return Object.entries(detail.batch)
    }

    return Object.entries(detail.job)
  }, [detail])

  const onReturn = () => {
    if (window.history.length > 1) {
      navigate(-1)
      return
    }
    navigate('/jobs')
  }

  return (
    <section className="panel">
      <div className="panel-top-row">
        <div>
          <p className="eyebrow">Admin</p>
          <h2 className="panel-title">Job Detail</h2>
        </div>
        <button className="btn btn--ghost" type="button" onClick={onReturn}>
          Return
        </button>
      </div>
      <p className="panel-copy">Inspect one job record and child items for batch insert jobs.</p>

      {!token && (
        <div className="notice-wrap">
          <p className="notice notice--error">Login is required to view admin job details.</p>
          <Link className="btn" to="/login">
            Go To Login
          </Link>
        </div>
      )}

      {token && !isDetailJobType(jobType) && (
        <p className="notice notice--error">Unsupported job type. Use book_batch, tts, or scrape.</p>
      )}

      {token && status === 'loading' && <p className="notice">Loading job details...</p>}
      {token && status === 'error' && <p className="notice notice--error">{errorMessage}</p>}

      {token && status === 'ok' && !isAdmin && (
        <p className="notice notice--error">Admin role is required to access this page.</p>
      )}

      {token && status === 'ok' && isAdmin && detail && (
        <>
          <article className="subpanel subpanel--full">
            <div className="row-head">
              <h3>
                {detail.job_type.toUpperCase()} / {detail.job_id}
              </h3>
            </div>

            <ul className="metric-list">
              {detailEntries.map(([key, value]) => (
                <li key={key}>
                  <strong>{key}</strong>
                  <span>{stringifyValue(value)}</span>
                </li>
              ))}
            </ul>
          </article>

          {detail.job_type === 'book_batch' && (
            <article className="subpanel subpanel--full">
              <div className="row-head">
                <h3>Batch Children</h3>
                <span className="field-inline">{detail.children.length} items</span>
              </div>

              <ul className="data-list">
                {detail.children.length === 0 && (
                  <li>
                    <strong>No child items</strong>
                    <span>This batch does not contain child jobs.</span>
                  </li>
                )}
                {detail.children.map((child) => {
                  const childId = stringifyValue(child.id)
                  const childStatus = stringifyValue(child.status)
                  const childFile = stripExtension(stringifyValue(child.file_name))
                  const childError = stringifyValue(child.error)
                  return (
                    <li key={childId}>
                      <strong>{childFile}</strong>
                      <span>ID: {childId}</span>
                      <span>Status: {childStatus}</span>
                      <span>Error: {childError}</span>
                    </li>
                  )
                })}
              </ul>
            </article>
          )}
        </>
      )}
    </section>
  )
}
