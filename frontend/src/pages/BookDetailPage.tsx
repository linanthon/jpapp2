import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ApiError,
  checkAdminAccess,
  deleteBookInBackground,
  getBookDetails,
  toggleStar,
  type ViewSpecificBookResponse,
} from '../lib/api'
import { getAccessToken } from '../lib/auth'

function createIdempotencyKey() {
  if ('randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `idem-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function BookDetailPage() {
  const navigate = useNavigate()
  const { bookId } = useParams()
  const token = getAccessToken()
  const [status, setStatus] = useState<'idle' | 'loading' | 'ok' | 'error'>(
    token && bookId ? 'loading' : 'idle',
  )
  const [errorMessage, setErrorMessage] = useState('')
  const [bookPayload, setBookPayload] = useState<ViewSpecificBookResponse | null>(null)
  const [isAdmin, setIsAdmin] = useState(false)
  const [deleteMessage, setDeleteMessage] = useState('')
  const [bookTextResult, setBookTextResult] = useState<{
    key: string
    text: string
    error: string
    loaded: boolean
  }>({ key: '', text: '', error: '', loaded: false })

  useEffect(() => {
    if (!token || !bookId) {
      return
    }

    Promise.all([getBookDetails(token, Number(bookId)), checkAdminAccess(token)])
      .then(([bookResponse, adminFlag]) => {
        setBookPayload(bookResponse)
        setIsAdmin(adminFlag)
        setStatus('ok')
      })
      .catch((error: unknown) => {
        setStatus('error')
        if (error instanceof ApiError) {
          setErrorMessage(error.message)
        } else {
          setErrorMessage('Failed to load book details.')
        }
      })
  }, [token, bookId])

  const details = bookPayload?.book_details
  const downloadUrl = details?.download_url ?? ''
  const contentCacheKey = details?.object_name ? `book-content:${details.object_name}` : ''

  const cachedBookText = useMemo(() => {
    if (!contentCacheKey) {
      return ''
    }
    try {
      return sessionStorage.getItem(contentCacheKey) ?? ''
    } catch {
      return ''
    }
  }, [contentCacheKey])

  useEffect(() => {
    if (!downloadUrl || !contentCacheKey || cachedBookText) {
      return
    }

    let isCancelled = false
    const controller = new AbortController()

    fetch(downloadUrl, {
      method: 'GET',
      cache: 'force-cache',
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Download failed with status ${response.status}`)
        }
        return response.text()
      })
      .then((text) => {
        if (isCancelled) {
          return
        }
        setBookTextResult({ key: contentCacheKey, text, error: '', loaded: true })
        try {
          sessionStorage.setItem(contentCacheKey, text)
        } catch {
          // Best-effort cache only.
        }
      })
      .catch((error: unknown) => {
        if (isCancelled || (error instanceof Error && error.name === 'AbortError')) {
          return
        }
        setBookTextResult({
          key: contentCacheKey,
          text: '',
          error: error instanceof Error ? error.message : 'Failed to download book content.',
          loaded: false,
        })
      })

    return () => {
      isCancelled = true
      controller.abort()
    }
  }, [downloadUrl, contentCacheKey, cachedBookText])

  const resolvedBookText = cachedBookText || (bookTextResult.key === contentCacheKey ? bookTextResult.text : '')
  const resolvedBookError =
    !cachedBookText && bookTextResult.key === contentCacheKey ? bookTextResult.error : ''
  const hasLoadedRemote =
    !cachedBookText && bookTextResult.key === contentCacheKey && bookTextResult.loaded
  const isBookTextLoading = Boolean(downloadUrl) && !cachedBookText && !resolvedBookError && !hasLoadedRemote

  const onToggleStar = async () => {
    if (!token || !bookPayload) {
      return
    }

    const nextStar = !bookPayload.book_details.star
    try {
      const response = await toggleStar(token, {
        id: bookPayload.book_details.book_id,
        objType: 'book',
        star: nextStar,
      })
      if (!response.success) {
        setErrorMessage('Failed to update book star.')
        return
      }
      setBookPayload({
        ...bookPayload,
        book_details: { ...bookPayload.book_details, star: nextStar },
      })
    } catch (error) {
      if (error instanceof ApiError) {
        setErrorMessage(error.message)
      } else {
        setErrorMessage('Failed to update book star.')
      }
    }
  }

  const onDelete = async () => {
    if (!token || !bookPayload) {
      return
    }

    setDeleteMessage('')
    try {
      const result = await deleteBookInBackground(
        token,
        bookPayload.book_details.book_id,
        createIdempotencyKey(),
      )
      setDeleteMessage(`Delete job queued: ${result.job_id}`)
    } catch (error) {
      if (error instanceof ApiError) {
        setDeleteMessage(error.message)
      } else {
        setDeleteMessage('Failed to queue delete job.')
      }
    }
  }

  const onReturn = () => {
    if (window.history.length > 1) {
      navigate(-1)
      return
    }
    navigate('/view')
  }

  return (
    <section className="panel">
      <div className="panel-top-row">
        <div>
          <p className="eyebrow">View</p>
          <h2 className="panel-title">Book Details</h2>
        </div>
        <button className="btn btn--ghost" type="button" onClick={onReturn}>
          Return
        </button>
      </div>
      <p className="panel-copy">Inspect one book and manage star/delete actions.</p>

      {!token && (
        <div className="notice-wrap">
          <p className="notice notice--error">Login is required for book detail routes.</p>
          <Link className="btn" to="/login">
            Go To Login
          </Link>
        </div>
      )}

      {token && status === 'loading' && <p className="notice">Loading book details...</p>}
      {token && status === 'error' && <p className="notice notice--error">{errorMessage}</p>}

      {token && status === 'ok' && bookPayload && (
        <>
          <article className="subpanel subpanel--full">
            <div className="row-head">
              <h3>{bookPayload.book_details.name}</h3>
              <button
                className={`star-btn ${bookPayload.book_details.star ? 'star-btn--active' : ''}`}
                type="button"
                aria-pressed={bookPayload.book_details.star}
                onClick={onToggleStar}
              >
                {bookPayload.book_details.star ? (
                  <span className="star-btn__label">
                    <span className="star-btn__icon">★</span>
                    <span className="star-btn__text">Starred</span>
                  </span>
                ) : (
                  '☆ Star'
                )}
              </button>
            </div>
            <p className="panel-copy">Created: {bookPayload.book_details.created_at}</p>
            {bookPayload.book_details.download_url && (
              <div className="inline-actions">
                <a
                  className="btn btn--ghost"
                  href={bookPayload.book_details.download_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Download Original
                </a>
              </div>
            )}
          </article>

          <article className="subpanel subpanel--full">
            <h3>Book Content</h3>
            {!downloadUrl && <p className="notice">No downloadable content available.</p>}
            {isBookTextLoading && <p className="notice">Loading book content...</p>}
            {!!resolvedBookError && <p className="notice notice--error">{resolvedBookError}</p>}
            {(cachedBookText || hasLoadedRemote) && (
              <pre className="book-content">{resolvedBookText || 'Content is empty.'}</pre>
            )}
          </article>

          {isAdmin && (
            <article className="subpanel subpanel--full">
              <h3>Admin Actions</h3>
              <div className="inline-actions">
                <button className="btn btn--danger" type="button" onClick={onDelete}>
                  Delete Book
                </button>
              </div>
              {deleteMessage && <p className="notice">{deleteMessage}</p>}
            </article>
          )}
        </>
      )}
    </section>
  )
}
