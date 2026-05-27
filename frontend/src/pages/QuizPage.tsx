import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ApiError,
  type QuizMode,
  type QuizQuestion,
  getQuizByMode,
  submitWordPriorityBatch,
} from '../lib/api'
import { getAccessToken } from '../lib/auth'

type QuizItem = QuizQuestion & { word_id: number }

export function QuizPage() {
  const token = getAccessToken()
  const [mode, setMode] = useState<QuizMode>('jp')
  const [items, setItems] = useState<QuizItem[]>([])
  const [status, setStatus] = useState<'idle' | 'loading' | 'error' | 'ready'>(
    token ? 'loading' : 'idle',
  )
  const [errorMessage, setErrorMessage] = useState('')
  const [currentIndex, setCurrentIndex] = useState(0)
  const [selected, setSelected] = useState<Record<number, string>>({})
  const [submitState, setSubmitState] = useState<'idle' | 'submitting' | 'done' | 'error'>('idle')
  const [submitMessage, setSubmitMessage] = useState('')

  useEffect(() => {
    if (!token) {
      return
    }

    getQuizByMode(mode, token, { limit: 10, use_priority: true, get_distractors_from_db: true })
      .then((data) => {
        const nextItems = Object.entries(data.quizes).map(([wordId, quiz]) => ({
          ...quiz,
          word_id: Number(wordId),
        }))
        setItems(nextItems)
        setSelected({})
        setCurrentIndex(0)
        setSubmitState('idle')
        setSubmitMessage('')
        setStatus('ready')
      })
      .catch((error: unknown) => {
        setStatus('error')
        if (error instanceof ApiError) {
          setErrorMessage(error.message)
          return
        }
        setErrorMessage('Failed to load quiz questions.')
      })
  }, [mode, token])

  const currentItem = items[currentIndex]
  const answeredCount = useMemo(() => Object.keys(selected).length, [selected])
  const score = useMemo(() => {
    return items.reduce((sum, item) => {
      const answer = selected[item.word_id]
      return sum + (answer && answer === item.correct ? 1 : 0)
    }, 0)
  }, [items, selected])

  const submitSession = async () => {
    if (!token || items.length === 0) {
      return
    }

    setSubmitState('submitting')
    setSubmitMessage('')
    try {
      const answers = items
        .filter((item) => selected[item.word_id])
        .map((item) => ({
          word_id: item.word_id,
          is_correct: selected[item.word_id] === item.correct,
          quized: item.quized,
          occurrence: item.occurrence,
        }))

      const result = await submitWordPriorityBatch(token, answers)
      setSubmitState('done')
      setSubmitMessage(
        `Session saved. Updated ${result.updated}/${result.total} words (${result.failed} failed).`,
      )
    } catch (error) {
      setSubmitState('error')
      if (error instanceof ApiError) {
        setSubmitMessage(error.message)
      } else {
        setSubmitMessage('Failed to save quiz result.')
      }
    }
  }

  return (
    <section className="panel">
      <p className="eyebrow">Quiz</p>
      <h2 className="panel-title">Quiz Workspace</h2>
      <p className="panel-copy">
        Run JP/EN/Known quiz sessions and submit score deltas in one batch.
      </p>

      {!token && (
        <div className="notice-wrap">
          <p className="notice notice--error">You need to log in before starting quiz routes.</p>
          <Link className="btn" to="/login">
            Go To Login
          </Link>
        </div>
      )}

      {token && (
        <>
          <div className="toolbar-row">
            <label className="field-inline" htmlFor="quiz-mode">
              Mode
            </label>
            <select
              id="quiz-mode"
              className="field-input field-input--inline"
              value={mode}
              onChange={(event) => {
                setStatus('loading')
                setErrorMessage('')
                setMode(event.target.value as QuizMode)
              }}
            >
              <option value="jp">JP -&gt; EN</option>
              <option value="en">EN -&gt; JP</option>
              <option value="known">Known</option>
            </select>
          </div>

          {status === 'loading' && <p className="notice">Loading quiz data...</p>}
          {status === 'error' && <p className="notice notice--error">{errorMessage}</p>}
          {status === 'ready' && items.length === 0 && (
            <p className="notice">No quizzes returned for this mode/filter yet.</p>
          )}

          {status === 'ready' && currentItem && (
            <article className="quiz-card">
              <p className="quiz-meta">
                Question {currentIndex + 1} of {items.length}
              </p>
              <h3 className="quiz-question">{currentItem.question}</h3>
              {currentItem.spelling && <p className="quiz-hint">{currentItem.spelling}</p>}

              <div className="choice-grid">
                {currentItem.choices.map((choice) => (
                  <button
                    key={choice}
                    type="button"
                    className={`choice-btn ${selected[currentItem.word_id] === choice ? 'choice-btn--selected' : ''}`}
                    onClick={() => {
                      setSelected((prev) => ({ ...prev, [currentItem.word_id]: choice }))
                    }}
                  >
                    {choice}
                  </button>
                ))}
              </div>

              <div className="inline-actions">
                <button
                  className="btn btn--ghost"
                  type="button"
                  disabled={currentIndex === 0}
                  onClick={() => setCurrentIndex((prev) => Math.max(0, prev - 1))}
                >
                  Previous
                </button>
                <button
                  className="btn"
                  type="button"
                  disabled={currentIndex >= items.length - 1}
                  onClick={() => setCurrentIndex((prev) => Math.min(items.length - 1, prev + 1))}
                >
                  Next
                </button>
              </div>
            </article>
          )}

          {items.length > 0 && (
            <div className="stat-row">
              <article className="stat-card">
                <h3>Answered</h3>
                <p>
                  {answeredCount}/{items.length}
                </p>
              </article>
              <article className="stat-card">
                <h3>Current Score</h3>
                <p>
                  {score}/{items.length}
                </p>
              </article>
            </div>
          )}

          {items.length > 0 && (
            <div className="inline-actions">
              <button
                className="btn"
                type="button"
                disabled={answeredCount === 0 || submitState === 'submitting'}
                onClick={submitSession}
              >
                {submitState === 'submitting' ? 'Saving Session...' : 'Save Session'}
              </button>
              <button
                className="btn btn--ghost"
                type="button"
                onClick={() => {
                  setSelected({})
                  setCurrentIndex(0)
                  setSubmitState('idle')
                  setSubmitMessage('')
                }}
              >
                Reset Answers
              </button>
            </div>
          )}

          {submitState !== 'idle' && (
            <p className={`notice ${submitState === 'error' ? 'notice--error' : 'notice--success'}`}>
              {submitMessage}
            </p>
          )}
        </>
      )}
    </section>
  )
}
