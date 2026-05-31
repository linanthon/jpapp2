import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ApiError,
  checkAdminAccess,
  getAdminJobs,
  type AdminJobListItem,
  type AdminJobType,
} from '../lib/api'
import { getAccessToken } from '../lib/auth'

const PAGE_SIZE = 10

function formatTimestamp(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString()
}

export function JobPage() {
  const token = getAccessToken()
  const [jobType, setJobType] = useState<AdminJobType>('all')
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState<'idle' | 'loading' | 'ok' | 'error'>(
    token ? 'loading' : 'idle',
  )
  const [errorMessage, setErrorMessage] = useState('')
  const [isAdmin, setIsAdmin] = useState(false)
  const [jobs, setJobs] = useState<AdminJobListItem[]>([])
  const [pageCount, setPageCount] = useState(0)
  const [totalCount, setTotalCount] = useState(0)

  useEffect(() => {
    if (!token) {
      return
    }

    const loadJobs = async () => {
      setStatus('loading')
      setErrorMessage('')

      try {
        const adminFlag = await checkAdminAccess(token)
        if (!adminFlag) {
          setIsAdmin(false)
          setJobs([])
          setPageCount(0)
          setTotalCount(0)
          setStatus('ok')
          return
        }

        setIsAdmin(true)
        const payload = await getAdminJobs(token, {
          page,
          limit: PAGE_SIZE,
          job_type: jobType,
        })
        setJobs(payload.jobs)
        setPageCount(payload.page_count)
        setTotalCount(payload.total)
        setStatus('ok')
      } catch (error: unknown) {
        setStatus('error')
        if (error instanceof ApiError) {
          setErrorMessage(error.message)
        } else {
          setErrorMessage('Failed to load jobs.')
        }
      }
    }

    void loadJobs()
  }, [token, page, jobType])

  return (
    <section className="panel">
      <div className="panel-top-row">
        <div>
          <p className="eyebrow">Admin</p>
          <h2 className="panel-title">Jobs</h2>
        </div>
      </div>
      <p className="panel-copy">Review TTS, scrape, and insert book batch jobs with pagination.</p>

      {!token && (
        <div className="notice-wrap">
          <p className="notice notice--error">Login is required to view admin jobs.</p>
          <Link className="btn" to="/login">
            Go To Login
          </Link>
        </div>
      )}

      {token && status === 'loading' && <p className="notice">Loading jobs...</p>}
      {token && status === 'error' && <p className="notice notice--error">{errorMessage}</p>}

      {token && status === 'ok' && !isAdmin && (
        <p className="notice notice--error">Admin role is required to access this page.</p>
      )}

      {token && status === 'ok' && isAdmin && (
        <>
          <div className="toolbar-row">
            <label className="field-label" htmlFor="job-type-filter">
              Job Type
            </label>
            <select
              id="job-type-filter"
              className="field-input field-input--inline"
              value={jobType}
              onChange={(event) => {
                setPage(1)
                setJobType(event.target.value as AdminJobType)
              }}
            >
              <option value="all">All</option>
              <option value="book_batch">Insert Book Batch</option>
              <option value="tts">TTS</option>
              <option value="scrape">Scrape</option>
            </select>
            <span className="field-inline">Total: {totalCount}</span>
          </div>

          <ul className="data-list">
            {jobs.length === 0 && (
              <li>
                <strong>No jobs found.</strong>
                <span>Try another filter.</span>
              </li>
            )}
            {jobs.map((job) => (
              <li key={`${job.job_type}:${job.id}`}>
                <div className="list-row">
                  <Link className="list-main" to={`/jobs/${job.job_type}/${job.id}`}>
                    <strong>{job.job_type.toUpperCase()}</strong>
                    <span className="job-meta-line">
                      ID: {job.id}
                      <span className="job-meta-sep" aria-hidden="true">
                        |
                      </span>
                      Status: {job.status}
                      <span className="job-meta-sep" aria-hidden="true">
                        |
                      </span>
                      User: {job.user_id ?? 'N/A'}
                      <span className="job-meta-sep" aria-hidden="true">
                        |
                      </span>
                      Created: {formatTimestamp(job.created_at)}
                    </span>
                  </Link>
                </div>
              </li>
            ))}
          </ul>

          <div className="pager-row">
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => setPage((prev) => Math.max(1, prev - 1))}
              disabled={page <= 1}
            >
              Prev
            </button>
            <span className="field-inline">
              Page {pageCount === 0 ? 0 : page} / {pageCount}
            </span>
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => setPage((prev) => (pageCount > 0 ? Math.min(pageCount, prev + 1) : prev + 1))}
              disabled={pageCount > 0 ? page >= pageCount : true}
            >
              Next
            </button>
          </div>
        </>
      )}
    </section>
  )
}
