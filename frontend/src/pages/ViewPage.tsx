import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import {
  ApiError,
  getBooks,
  getWords,
  searchWords,
  toggleStar,
  type BookListItem,
  type WordListItem,
} from '../lib/api'
import { getAccessToken } from '../lib/auth'

const SEARCH_PAGE_SIZE = 10

function clampPage(page: number, pageCount: number) {
  if (pageCount < 1) {
    return 1
  }
  return Math.min(Math.max(1, page), pageCount)
}

export function ViewPage() {
  const token = getAccessToken()
  const [wordsStatus, setWordsStatus] = useState<'idle' | 'loading' | 'error' | 'ok'>(
    token ? 'loading' : 'idle',
  )
  const [booksStatus, setBooksStatus] = useState<'idle' | 'loading' | 'error' | 'ok'>(
    token ? 'loading' : 'idle',
  )
  const [errorMessage, setErrorMessage] = useState('')
  const [wordItems, setWordItems] = useState<WordListItem[]>([])
  const [bookItems, setBookItems] = useState<BookListItem[]>([])
  const [wordPage, setWordPage] = useState(1)
  const [wordPageCount, setWordPageCount] = useState(1)
  const [bookPage, setBookPage] = useState(1)
  const [bookPageCount, setBookPageCount] = useState(1)
  const [wordJlptFilter, setWordJlptFilter] = useState('')
  const [wordStarOnly, setWordStarOnly] = useState(false)
  const [bookStarOnly, setBookStarOnly] = useState(false)
  const [wordStarMap, setWordStarMap] = useState<Record<number, boolean>>({})

  const [searchTerm, setSearchTerm] = useState('')
  const [searchStatus, setSearchStatus] = useState<'idle' | 'loading' | 'error' | 'ok'>('idle')
  const [searchItems, setSearchItems] = useState<WordListItem[]>([])
  const [searchPage, setSearchPage] = useState(1)
  const [searchJlptFilter, setSearchJlptFilter] = useState('')
  const [searchStarOnly, setSearchStarOnly] = useState(false)

  useEffect(() => {
    if (!token) {
      return
    }

    getWords(token, {
      page: wordPage,
      limit: 10,
      jlpt_level: wordJlptFilter,
      star: wordStarOnly,
    })
      .then((data) => {
        setWordItems(data.word_list)
        setWordPageCount(data.page_count)
        setWordPage(clampPage(data.page, data.page_count))
        setWordStarMap((prev) => {
          const next = { ...prev }
          data.word_list.forEach((item) => {
            next[item.word_id] = item.star
          })
          return next
        })
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
  }, [token, wordPage, wordJlptFilter, wordStarOnly])

  useEffect(() => {
    if (!token) {
      return
    }

    getBooks(token, { page: bookPage, limit: 10, star: bookStarOnly })
      .then((data) => {
        setBookItems(data.book_list)
        setBookPageCount(data.page_count)
        setBookPage(clampPage(data.page, data.page_count))
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
  }, [token, bookPage, bookStarOnly])

  const filteredSearchItems = useMemo(() => {
    return searchItems.filter((item) => {
      if (searchJlptFilter && (item.jlpt_level || '').toUpperCase() !== searchJlptFilter.toUpperCase()) {
        return false
      }

      if (searchStarOnly) {
        return Boolean(wordStarMap[item.word_id] ?? item.star)
      }
      return true
    })
  }, [searchItems, searchJlptFilter, searchStarOnly, wordStarMap])

  const searchPageCount = Math.max(1, Math.ceil(filteredSearchItems.length / SEARCH_PAGE_SIZE))
  const currentSearchPage = clampPage(searchPage, searchPageCount)
  const pagedSearchItems = filteredSearchItems.slice(
    (currentSearchPage - 1) * SEARCH_PAGE_SIZE,
    currentSearchPage * SEARCH_PAGE_SIZE,
  )

  const toggleWordStar = async (word: WordListItem, nextStar: boolean) => {
    if (!token) {
      return
    }

    try {
      await toggleStar(token, { id: word.word_id, objType: 'word', star: nextStar })
      setWordItems((prev) =>
        prev.map((item) => (item.word_id === word.word_id ? { ...item, star: nextStar } : item)),
      )
      setSearchItems((prev) =>
        prev.map((item) => (item.word_id === word.word_id ? { ...item, star: nextStar } : item)),
      )
      setWordStarMap((prev) => ({ ...prev, [word.word_id]: nextStar }))
    } catch (error) {
      if (error instanceof ApiError) {
        setErrorMessage(error.message)
      } else {
        setErrorMessage('Failed to update word star.')
      }
    }
  }

  const toggleBookStar = async (book: BookListItem, nextStar: boolean) => {
    if (!token) {
      return
    }

    try {
      await toggleStar(token, { id: book.book_id, objType: 'book', star: nextStar })
      setBookItems((prev) =>
        prev.map((item) => (item.book_id === book.book_id ? { ...item, star: nextStar } : item)),
      )
    } catch (error) {
      if (error instanceof ApiError) {
        setErrorMessage(error.message)
      } else {
        setErrorMessage('Failed to update book star.')
      }
    }
  }

  const onSearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!token || !searchTerm.trim()) {
      return
    }

    setSearchStatus('loading')
    setErrorMessage('')
    try {
      const response = await searchWords(token, searchTerm.trim(), 80)
      setSearchItems(response.results)
      setSearchPage(1)
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
          <article className="subpanel subpanel--full">
            <h3>Search</h3>
            <div className="toolbar-row">
              <label className="field-inline" htmlFor="search-jlpt">
                JLPT
              </label>
              <select
                id="search-jlpt"
                className="field-input field-input--inline"
                value={searchJlptFilter}
                onChange={(event) => {
                  setSearchJlptFilter(event.target.value)
                  setSearchPage(1)
                }}
              >
                <option value="">All</option>
                <option value="N5">N5</option>
                <option value="N4">N4</option>
                <option value="N3">N3</option>
                <option value="N2">N2</option>
                <option value="N1">N1</option>
                <option value="N0">N0</option>
              </select>
              <label className="toggle-line" htmlFor="search-star">
                <input
                  id="search-star"
                  type="checkbox"
                  checked={searchStarOnly}
                  onChange={(event) => {
                    setSearchStarOnly(event.target.checked)
                    setSearchPage(1)
                  }}
                />
                Starred only
              </label>
            </div>
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
            {searchStatus === 'ok' && pagedSearchItems.length > 0 && (
              <ul className="data-list">
                {pagedSearchItems.map((item, index) => (
                  <li key={String(item.word_id ?? index)}>
                    <div className="list-row">
                      <Link className="list-main" to={`/view/word/${item.word_id}`}>
                        <strong>{item.word || 'Unknown'}</strong>
                        <span>{item.senses || '-'}</span>
                      </Link>
                      <button
                        className={`star-btn ${(wordStarMap[item.word_id] ?? item.star) ? 'star-btn--active' : ''}`}
                        type="button"
                        aria-pressed={wordStarMap[item.word_id] ?? item.star}
                        onClick={() =>
                          toggleWordStar(item, !(wordStarMap[item.word_id] ?? item.star))
                        }
                      >
                        {wordStarMap[item.word_id] ?? item.star ? '★' : '☆'}
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {searchStatus === 'ok' && filteredSearchItems.length > 0 && (
              <div className="pager-row">
                <button
                  className="btn btn--ghost"
                  type="button"
                  disabled={currentSearchPage <= 1}
                  onClick={() => setSearchPage((prev) => Math.max(1, prev - 1))}
                >
                  Previous
                </button>
                <span>
                  Page {currentSearchPage} / {searchPageCount}
                </span>
                <button
                  className="btn btn--ghost"
                  type="button"
                  disabled={currentSearchPage >= searchPageCount}
                  onClick={() => setSearchPage((prev) => Math.min(searchPageCount, prev + 1))}
                >
                  Next
                </button>
              </div>
            )}
          </article>

          <div className="split-grid">
            <article className="subpanel">
              <h3>Words</h3>
              <div className="toolbar-row">
                <label className="field-inline" htmlFor="word-jlpt">
                  JLPT
                </label>
                <select
                  id="word-jlpt"
                  className="field-input field-input--inline"
                  value={wordJlptFilter}
                  onChange={(event) => {
                    setWordsStatus('loading')
                    setWordPage(1)
                    setWordJlptFilter(event.target.value)
                  }}
                >
                  <option value="">All</option>
                  <option value="N5">N5</option>
                  <option value="N4">N4</option>
                  <option value="N3">N3</option>
                  <option value="N2">N2</option>
                  <option value="N1">N1</option>
                  <option value="N0">N0</option>
                </select>
                <label className="toggle-line" htmlFor="word-star-filter">
                  <input
                    id="word-star-filter"
                    type="checkbox"
                    checked={wordStarOnly}
                    onChange={(event) => {
                      setWordsStatus('loading')
                      setWordPage(1)
                      setWordStarOnly(event.target.checked)
                    }}
                  />
                  Starred only
                </label>
              </div>
              {wordsStatus === 'loading' && <p className="notice">Loading words...</p>}
              {wordsStatus === 'ok' && wordItems.length === 0 && <p className="notice">No words yet.</p>}
              {wordsStatus === 'ok' && wordItems.length > 0 && (
                <ul className="data-list">
                  {wordItems.map((item, index) => (
                    <li key={String(item.word_id ?? index)}>
                      <div className="list-row">
                        <Link className="list-main" to={`/view/word/${item.word_id}`}>
                          <strong>{item.word || 'Unknown'}</strong>
                          <span>{item.senses || '-'}</span>
                        </Link>
                        <button
                          className={`star-btn ${item.star ? 'star-btn--active' : ''}`}
                          type="button"
                          aria-pressed={item.star}
                          onClick={() => toggleWordStar(item, !item.star)}
                        >
                          {item.star ? '★' : '☆'}
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              {wordsStatus === 'ok' && wordPageCount > 0 && (
                <div className="pager-row">
                  <button
                    className="btn btn--ghost"
                    type="button"
                    disabled={wordPage <= 1}
                    onClick={() => {
                      setWordsStatus('loading')
                      setWordPage((prev) => Math.max(1, prev - 1))
                    }}
                  >
                    Previous
                  </button>
                  <span>
                    Page {wordPage} / {wordPageCount}
                  </span>
                  <button
                    className="btn btn--ghost"
                    type="button"
                    disabled={wordPage >= wordPageCount}
                    onClick={() => {
                      setWordsStatus('loading')
                      setWordPage((prev) => Math.min(wordPageCount, prev + 1))
                    }}
                  >
                    Next
                  </button>
                </div>
              )}
            </article>

            <article className="subpanel">
              <h3>Books</h3>
              <div className="toolbar-row">
                <label className="toggle-line" htmlFor="book-star-filter">
                  <input
                    id="book-star-filter"
                    type="checkbox"
                    checked={bookStarOnly}
                    onChange={(event) => {
                      setBooksStatus('loading')
                      setBookPage(1)
                      setBookStarOnly(event.target.checked)
                    }}
                  />
                  Starred only
                </label>
              </div>
              {booksStatus === 'loading' && <p className="notice">Loading books...</p>}
              {booksStatus === 'ok' && bookItems.length === 0 && <p className="notice">No books yet.</p>}
              {booksStatus === 'ok' && bookItems.length > 0 && (
                <ul className="data-list">
                  {bookItems.map((item, index) => (
                    <li key={String(item.book_id ?? index)}>
                      <div className="list-row">
                        <Link className="list-main" to={`/view/book/${item.book_id}`}>
                          <strong>{item.name || 'Untitled'}</strong>
                          <span>Created: {item.created_at || '-'}</span>
                        </Link>
                        <button
                          className={`star-btn ${item.star ? 'star-btn--active' : ''}`}
                          type="button"
                          aria-pressed={item.star}
                          onClick={() => toggleBookStar(item, !item.star)}
                        >
                          {item.star ? '★' : '☆'}
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              {booksStatus === 'ok' && bookPageCount > 0 && (
                <div className="pager-row">
                  <button
                    className="btn btn--ghost"
                    type="button"
                    disabled={bookPage <= 1}
                    onClick={() => {
                      setBooksStatus('loading')
                      setBookPage((prev) => Math.max(1, prev - 1))
                    }}
                  >
                    Previous
                  </button>
                  <span>
                    Page {bookPage} / {bookPageCount}
                  </span>
                  <button
                    className="btn btn--ghost"
                    type="button"
                    disabled={bookPage >= bookPageCount}
                    onClick={() => {
                      setBooksStatus('loading')
                      setBookPage((prev) => Math.min(bookPageCount, prev + 1))
                    }}
                  >
                    Next
                  </button>
                </div>
              )}
            </article>
          </div>
        </>
      )}
    </section>
  )
}
