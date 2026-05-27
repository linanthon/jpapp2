import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, getBooks, getWords, searchWords } from '../lib/api'
import { getAccessToken } from '../lib/auth'

export function ViewPage() {
  const token = getAccessToken()
  const [wordsStatus, setWordsStatus] = useState<'idle' | 'loading' | 'error' | 'ok'>(
    token ? 'loading' : 'idle',
  )
  const [booksStatus, setBooksStatus] = useState<'idle' | 'loading' | 'error' | 'ok'>(
    token ? 'loading' : 'idle',
  )
  const [errorMessage, setErrorMessage] = useState('')
  const [wordItems, setWordItems] = useState<Array<Record<string, unknown>>>([])
  const [bookItems, setBookItems] = useState<Array<Record<string, unknown>>>([])

  const [searchTerm, setSearchTerm] = useState('')
  const [searchStatus, setSearchStatus] = useState<'idle' | 'loading' | 'error' | 'ok'>('idle')
  const [searchItems, setSearchItems] = useState<Array<Record<string, unknown>>>([])

  useEffect(() => {
    if (!token) {
      return
    }

    getWords(token, { page: 1, limit: 20 })
      .then((data) => {
        setWordItems(data.word_list)
        setWordsStatus('ok')
      })
      .catch((error: unknown) => {
        setWordsStatus('error')
        if (error instanceof ApiError) {
          setErrorMessage(error.message)
        } else {
          setErrorMessage('Failed to load words list.')
        }
      })

    getBooks(token, { page: 1, limit: 20 })
      .then((data) => {
        setBookItems(data.book_list)
        setBooksStatus('ok')
      })
      .catch((error: unknown) => {
        setBooksStatus('error')
        if (error instanceof ApiError) {
          setErrorMessage(error.message)
        } else {
          setErrorMessage('Failed to load books list.')
        }
      })
  }, [token])

  const onSearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!token || !searchTerm.trim()) {
      return
    }

    setSearchStatus('loading')
    setErrorMessage('')
    try {
      const response = await searchWords(token, searchTerm.trim(), 20)
      setSearchItems(response.results)
      setSearchStatus('ok')
    } catch (error) {
      setSearchStatus('error')
      if (error instanceof ApiError) {
        setErrorMessage(error.message)
      } else {
        setErrorMessage('Word search failed.')
      }
    }
  }

  return (
    <section className="panel">
      <p className="eyebrow">View</p>
      <h2 className="panel-title">Collection Browser</h2>
      <p className="panel-copy">
        Browse words and books, then run direct search on authenticated routes.
      </p>

      {!token && (
        <div className="notice-wrap">
          <p className="notice notice--error">Login is required for collection APIs.</p>
          <Link className="btn" to="/login">
            Go To Login
          </Link>
        </div>
      )}

      {token && errorMessage && <p className="notice notice--error">{errorMessage}</p>}

      {token && (
        <>
          <div className="split-grid">
            <article className="subpanel">
              <h3>Words</h3>
              {wordsStatus === 'loading' && <p className="notice">Loading words...</p>}
              {wordsStatus === 'ok' && wordItems.length === 0 && <p className="notice">No words yet.</p>}
              {wordsStatus === 'ok' && wordItems.length > 0 && (
                <ul className="data-list">
                  {wordItems.map((item, index) => (
                    <li key={String(item.word_id ?? item.id ?? index)}>
                      <strong>{String(item.word ?? item.jp ?? 'Unknown')}</strong>
                      <span>{String(item.senses ?? item.meanings ?? '-')}</span>
                    </li>
                  ))}
                </ul>
              )}
            </article>

            <article className="subpanel">
              <h3>Books</h3>
              {booksStatus === 'loading' && <p className="notice">Loading books...</p>}
              {booksStatus === 'ok' && bookItems.length === 0 && <p className="notice">No books yet.</p>}
              {booksStatus === 'ok' && bookItems.length > 0 && (
                <ul className="data-list">
                  {bookItems.map((item, index) => (
                    <li key={String(item.book_id ?? item.id ?? index)}>
                      <strong>{String(item.name ?? 'Untitled')}</strong>
                      <span>star: {String(item.star ?? false)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </article>
          </div>

          <article className="subpanel subpanel--full">
            <h3>Search</h3>
            <form className="inline-form" onSubmit={onSearch}>
              <input
                className="field-input"
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
                placeholder="Search JP, kana, romaji, or EN"
              />
              <button className="btn" type="submit" disabled={searchStatus === 'loading'}>
                {searchStatus === 'loading' ? 'Searching...' : 'Search'}
              </button>
            </form>

            {searchStatus === 'ok' && searchItems.length === 0 && (
              <p className="notice">No matching word found.</p>
            )}
            {searchStatus === 'ok' && searchItems.length > 0 && (
              <ul className="data-list">
                {searchItems.map((item, index) => (
                  <li key={String(item.word_id ?? item.id ?? index)}>
                    <strong>{String(item.word ?? item.jp ?? 'Unknown')}</strong>
                    <span>{String(item.senses ?? '-')}</span>
                  </li>
                ))}
              </ul>
            )}
          </article>
        </>
      )}
    </section>
  )
}
