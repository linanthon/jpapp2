import { useEffect, useState } from 'react'
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
