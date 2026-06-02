import { useEffect, useRef, useState } from 'react'
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
const STATUS_OPTIONS = [
  'FINISHED',
  'FAILED',
  'QUEUED',
  'RUNNING',
  'PROCESSING',
  'SCRAPING',
  'UPLOADING',
  'QUEUED_PROCESS',
  'UPDATING_WORDS',
] as const

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
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const hasLoadedOnceRef = useRef(false)
  const [jobs, setJobs] = useState<AdminJobListItem[]>([])
  const [pageCount, setPageCount] = useState(0)
  const [totalCount, setTotalCount] = useState(0)
  const [filterStatusInput, setFilterStatusInput] = useState('')
  const [filterUserInput, setFilterUserInput] = useState('')
  const [appliedStatusFilter, setAppliedStatusFilter] = useState('')
  const [appliedUserFilter, setAppliedUserFilter] = useState('')

  useEffect(() => {
    if (!token) {
      return
    }

    const loadJobs = async () => {
      if (hasLoadedOnceRef.current) {
        setIsRefreshing(true)
      } else {
        setStatus('loading')
      }
      setErrorMessage('')

      try {
        const adminFlag = await checkAdminAccess(token)
        if (!adminFlag) {
          setIsAdmin(false)
          setJobs([])
          setPageCount(0)
          setTotalCount(0)
          setStatus('ok')
          setHasLoadedOnce(true)
          hasLoadedOnceRef.current = true
          return
        }

        setIsAdmin(true)
        const payload = await getAdminJobs(token, {
          page,
          limit: PAGE_SIZE,
          job_type: jobType,
          status: appliedStatusFilter || undefined,
          user: appliedUserFilter || undefined,
        })
        setJobs(payload.jobs)
        setPageCount(payload.page_count)
        setTotalCount(payload.total)
        setStatus('ok')
        setHasLoadedOnce(true)
        hasLoadedOnceRef.current = true
      } catch (error: unknown) {
        setStatus('error')
        if (error instanceof ApiError) {
          setErrorMessage(error.message)
        } else {
          setErrorMessage('Failed to load jobs.')
        }
      } finally {
        setIsRefreshing(false)
      }
    }

    void loadJobs()
  }, [token, page, jobType, appliedStatusFilter, appliedUserFilter])

  const onApplyFilters = () => {
    setPage(1)
    setAppliedStatusFilter(filterStatusInput)
    setAppliedUserFilter(filterUserInput.trim())
  }

  const onResetFilters = () => {
    setPage(1)
    setFilterStatusInput('')
    setFilterUserInput('')
    setAppliedStatusFilter('')
    setAppliedUserFilter('')
  }

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

      {token && status === 'loading' && !hasLoadedOnce && <p className="notice">Loading jobs...</p>}
      {token && status === 'error' && <p className="notice notice--error">{errorMessage}</p>}

      {token && hasLoadedOnce && status === 'ok' && !isAdmin && (
        <p className="notice notice--error">Admin role is required to access this page.</p>
      )}

      {token && hasLoadedOnce && status === 'ok' && isAdmin && (
        <>
          <div className="toolbar-row job-filter-row">
            <div className="job-filter-grid">
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

              <label className="field-label" htmlFor="job-status-filter">
                Status
              </label>
              <select
                id="job-status-filter"
                className="field-input field-input--inline"
                value={filterStatusInput}
                onChange={(event) => setFilterStatusInput(event.target.value)}
              >
                <option value="">All Statuses</option>
                {STATUS_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>

              <label className="field-label" htmlFor="job-user-filter">
                User
              </label>
              <input
                id="job-user-filter"
                className="field-input field-input--inline"
                type="text"
                placeholder="User id contains..."
                value={filterUserInput}
                onChange={(event) => setFilterUserInput(event.target.value)}
              />

              <span className="field-inline">
                Total: {totalCount}
                {isRefreshing ? ' (Refreshing...)' : ''}
              </span>
            </div>

            <div className="job-filter-actions">
              <button type="button" className="btn btn--ghost" onClick={onResetFilters}>
                Reset Filters
              </button>
              <button type="button" className="btn" onClick={onApplyFilters}>
                Apply Filters
              </button>
            </div>
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
