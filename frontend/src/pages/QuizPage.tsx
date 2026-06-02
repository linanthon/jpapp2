import { useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  ApiError,
  type QuizMode,
  type QuizQuestion,
  getQuizByMode,
  submitWordPriorityBatch,
} from '../lib/api'
import { getAccessToken } from '../lib/auth'

type QuizItem = QuizQuestion & { word_id: number }
const JLPT_OPTIONS = ['', 'N5', 'N4', 'N3', 'N2', 'N1', 'N0'] as const

function isJapaneseText(value: string) {
  return /[\u3040-\u30ff\u3400-\u9fff]/.test(value)
}

function formatElapsedTime(ms: number) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

export function QuizPage() {
  const navigate = useNavigate()
  const token = getAccessToken()
  const [optionsCollapsed, setOptionsCollapsed] = useState(false)
  const [mode, setMode] = useState<QuizMode>('jp')
  const [jlptLevel, setJlptLevel] = useState('')
  const [starredOnly, setStarredOnly] = useState(false)
  const [questionLimit, setQuestionLimit] = useState(10)
  const [distractorSource, setDistractorSource] = useState<'books' | 'jamdict'>('books')
  const [items, setItems] = useState<QuizItem[]>([])
  const [status, setStatus] = useState<'idle' | 'loading' | 'error' | 'ready' | 'summary'>('idle')
  const [errorMessage, setErrorMessage] = useState('')
  const [currentIndex, setCurrentIndex] = useState(0)
  const [selected, setSelected] = useState<Record<number, string>>({})
  const [submitState, setSubmitState] = useState<'idle' | 'submitting' | 'done' | 'error'>('idle')
  const [submitMessage, setSubmitMessage] = useState('')
  const [startedAtMs, setStartedAtMs] = useState<number | null>(null)
  const [endedAtMs, setEndedAtMs] = useState<number | null>(null)
  const hasSavedSessionRef = useRef(false)

  const currentItem = items[currentIndex]
  const score = useMemo(() => {
    return items.reduce((sum, item) => {
      const answer = selected[item.word_id]
      return sum + (answer && answer === item.correct ? 1 : 0)
    }, 0)
  }, [items, selected])

  const elapsedTimeMs = useMemo(() => {
    if (!startedAtMs || !endedAtMs) {
      return 0
    }
    return Math.max(0, endedAtMs - startedAtMs)
  }, [startedAtMs, endedAtMs])

  const saveSessionIfNeeded = async () => {
    if (!token || items.length === 0 || hasSavedSessionRef.current) {
      return
    }

    const answers = items
      .filter((item) => selected[item.word_id])
      .map((item) => ({
        word_id: item.word_id,
        is_correct: selected[item.word_id] === item.correct,
        quized: item.quized,
        occurrence: item.occurrence,
      }))

    if (answers.length === 0) {
      hasSavedSessionRef.current = true
      setSubmitState('idle')
      setSubmitMessage('')
      return
    }

    hasSavedSessionRef.current = true
    setSubmitState('submitting')
    setSubmitMessage('Saving session...')

    try {
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

  const startQuiz = async () => {
    if (!token) {
      return
    }

    setOptionsCollapsed(true)

    setStatus('loading')
    setErrorMessage('')
    setSubmitState('idle')
    setSubmitMessage('')
    hasSavedSessionRef.current = false

    try {
      const data = await getQuizByMode(mode, token, {
        limit: questionLimit,
        jlpt_level: jlptLevel || undefined,
        star: starredOnly || undefined,
        use_priority: true,
        get_distractors_from_db: distractorSource === 'books',
      })
      const nextItems = Object.entries(data.quizes).map(([wordId, quiz]) => ({
        ...quiz,
        word_id: Number(wordId),
      }))

      setItems(nextItems)
      setSelected({})
      setCurrentIndex(0)
      setStartedAtMs(Date.now())
      setEndedAtMs(null)
      setStatus('ready')
    } catch (error: unknown) {
      setStatus('error')
      if (error instanceof ApiError) {
        setErrorMessage(error.message)
      } else {
        setErrorMessage('Failed to load quiz questions.')
      }
    }
  }

  const finishQuiz = async () => {
    setEndedAtMs(Date.now())
    setStatus('summary')
    await saveSessionIfNeeded()
  }

  const openWordDetail = async () => {
    if (!currentItem || !token || !isJapaneseText(currentItem.question)) {
      return
    }
    await saveSessionIfNeeded()
    navigate(`/view/word/${currentItem.word_id}`)
  }

  const currentAnswer = currentItem ? selected[currentItem.word_id] : ''
  const hasAnsweredCurrent = Boolean(currentAnswer)

  const onChoiceSelect = (choice: string) => {
    if (!currentItem || hasAnsweredCurrent) {
      return
    }
    setSelected((prev) => ({ ...prev, [currentItem.word_id]: choice }))
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
          <article className={`subpanel subpanel--full quiz-setup-section ${optionsCollapsed ? 'quiz-setup-section--collapsed' : ''}`}>
            <div className="row-head">
              <h3>Quiz Start Options</h3>
              <button
                type="button"
                className="btn btn--ghost"
                onClick={() => setOptionsCollapsed((prev) => !prev)}
                aria-expanded={!optionsCollapsed}
                aria-controls="quiz-start-options"
              >
                {optionsCollapsed ? 'Expand Options' : 'Collapse Options'}
              </button>
            </div>

            {!optionsCollapsed ? (
              <div id="quiz-start-options" className="toolbar-row quiz-setup-grid">
                <label className="field-inline" htmlFor="quiz-mode">
                  Mode
                </label>
                <select
                  id="quiz-mode"
                  className="field-input field-input--inline"
                  value={mode}
                  onChange={(event) => setMode(event.target.value as QuizMode)}
                >
                  <option value="jp">JP -&gt; EN</option>
                  <option value="en">EN -&gt; JP</option>
                  <option value="known">Known</option>
                </select>

                <label className="field-inline" htmlFor="quiz-jlpt">
                  JLPT Level
                </label>
                <select
                  id="quiz-jlpt"
                  className="field-input field-input--inline"
                  value={jlptLevel}
                  onChange={(event) => setJlptLevel(event.target.value)}
                >
                  <option value="">All Levels</option>
                  {JLPT_OPTIONS.filter(Boolean).map((level) => (
                    <option key={level} value={level}>
                      {level}
                    </option>
                  ))}
                </select>

                <label className="field-inline" htmlFor="quiz-starred">
                  Starred
                </label>
                <select
                  id="quiz-starred"
                  className="field-input field-input--inline"
                  value={starredOnly ? 'starred' : 'all'}
                  onChange={(event) => setStarredOnly(event.target.value === 'starred')}
                >
                  <option value="all">All Words</option>
                  <option value="starred">Starred Only</option>
                </select>

                <label className="field-inline" htmlFor="quiz-limit">
                  Number Of Questions
                </label>
                <input
                  id="quiz-limit"
                  className="field-input field-input--inline"
                  type="number"
                  min={1}
                  max={100}
                  value={questionLimit}
                  onChange={(event) => {
                    const parsed = Number.parseInt(event.target.value, 10)
                    if (Number.isNaN(parsed)) {
                      setQuestionLimit(10)
                      return
                    }
                    setQuestionLimit(Math.min(100, Math.max(1, parsed)))
                  }}
                />

                <label className="field-inline" htmlFor="quiz-distractors">
                  Incorrect Choices Source
                </label>
                <select
                  id="quiz-distractors"
                  className="field-input field-input--inline"
                  value={distractorSource}
                  onChange={(event) => setDistractorSource(event.target.value as 'books' | 'jamdict')}
                >
                  <option value="books">From Inserted Books (Fast)</option>
                  <option value="jamdict">From Jamdict (Slow)</option>
                </select>

                <div className="inline-actions">
                  <button className="btn" type="button" onClick={startQuiz} disabled={status === 'loading'}>
                    {status === 'loading' ? 'Starting...' : 'Start'}
                  </button>
                </div>
              </div>
            ) : (
              <p className="panel-copy quiz-setup-collapsed-text">
                Options are collapsed. Expand to review or modify quiz settings.
              </p>
            )}
          </article>

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
              {isJapaneseText(currentItem.question) ? (
                <button type="button" className="quiz-question-link" onClick={openWordDetail}>
                  {currentItem.question}
                </button>
              ) : (
                <h3 className="quiz-question">{currentItem.question}</h3>
              )}
              {currentItem.spelling && <p className="quiz-hint">{currentItem.spelling}</p>}

              <div className="choice-grid">
                {currentItem.choices.map((choice) => (
                  (() => {
                    const selectedAnswer = selected[currentItem.word_id]
                    const isCorrectChoice = choice === currentItem.correct
                    const isWrongChosen = selectedAnswer === choice && selectedAnswer !== currentItem.correct
                    const choiceClass = [
                      'choice-btn',
                      isCorrectChoice && selectedAnswer ? 'choice-btn--correct' : '',
                      isWrongChosen ? 'choice-btn--wrong' : '',
                    ]
                      .filter(Boolean)
                      .join(' ')

                    return (
                  <button
                    key={choice}
                    type="button"
                    className={choiceClass}
                    disabled={hasAnsweredCurrent}
                    onClick={() => onChoiceSelect(choice)}
                  >
                    {choice}
                  </button>
                    )
                  })()
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
                  onClick={() => {
                    if (currentIndex >= items.length - 1) {
                      void finishQuiz()
                      return
                    }
                    setCurrentIndex((prev) => Math.min(items.length - 1, prev + 1))
                  }}
                >
                  {currentIndex >= items.length - 1 ? 'Finish Quiz' : 'Next'}
                </button>
              </div>
            </article>
          )}

          {status === 'summary' && (
            <article className="subpanel subpanel--full">
              <h3>Quiz Summary</h3>
              <p className="panel-copy">
                Correct: {score}/{items.length}
              </p>
              <p className="panel-copy">Time Spent: {formatElapsedTime(elapsedTimeMs)}</p>
              <div className="inline-actions">
                <button className="btn" type="button" onClick={startQuiz}>
                  Start New Quiz
                </button>
              </div>
            </article>
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
