import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ApiError,
  getApiAssetUrl,
  getWordDetails,
  requestWordAudio,
  toggleStar,
  toggleWordKnown,
  type ViewSpecificWordResponse,
} from '../lib/api'
import { getAccessToken } from '../lib/auth'

const DEFAULT_SENTENCE_LIMIT = 5

type ParsedSense = {
  meaning: string
  partOfSpeech: string
}

function parseSenses(rawSenses: string): ParsedSense[] {
  const chunks = rawSenses
    .split(';')
    .map((chunk) => chunk.trim())
    .filter(Boolean)

  return chunks.map((chunk) => {
    const marker = chunk.lastIndexOf(', (')
    if (marker > 0 && chunk.endsWith(')')) {
      return {
        meaning: chunk.slice(0, marker).trim(),
        partOfSpeech: chunk.slice(marker + 3, -1).trim(),
      }
    }
    return { meaning: chunk, partOfSpeech: '-' }
  })
}

async function playStaticAudio(mapping: string[]) {
  for (const syllable of mapping) {
    const src = getApiAssetUrl(`/audio/${encodeURIComponent(syllable)}.wav`)
    const audio = new Audio(src)
    await new Promise<void>((resolve) => {
      audio.onended = () => resolve()
      audio.onerror = () => resolve()
      audio.play().catch(() => resolve())
    })
  }
}

export function WordDetailPage() {
  const navigate = useNavigate()
  const { wordId } = useParams()
  const token = getAccessToken()
  const [status, setStatus] = useState<'idle' | 'loading' | 'ok' | 'error'>(
    token && wordId ? 'loading' : 'idle',
  )
  const [errorMessage, setErrorMessage] = useState('')
  const [audioMessage, setAudioMessage] = useState('')
  const [wordPayload, setWordPayload] = useState<ViewSpecificWordResponse | null>(null)
  const [useTtsModel, setUseTtsModel] = useState(true)
  const [isPlayingAudio, setIsPlayingAudio] = useState(false)

  useEffect(() => {
    if (!token || !wordId) {
      return
    }

    getWordDetails(token, Number(wordId), DEFAULT_SENTENCE_LIMIT)
      .then((data) => {
        setWordPayload(data)
        setStatus('ok')
      })
      .catch((error: unknown) => {
        setStatus('error')
        if (error instanceof ApiError) {
          setErrorMessage(error.message)
        } else {
          setErrorMessage('Failed to load word details.')
        }
      })
  }, [token, wordId])

  const senses = useMemo(() => {
    const raw = wordPayload?.word_details?.senses ?? ''
    return parseSenses(raw)
  }, [wordPayload])

  const isKnown = (wordPayload?.word_details?.priority ?? 0) < 0

  const onToggleStar = async () => {
    if (!token || !wordPayload) {
      return
    }

    const nextStar = !wordPayload.word_details.star
    try {
      await toggleStar(token, {
        id: wordPayload.word_details.word_id,
        objType: 'word',
        star: nextStar,
      })
      setWordPayload({
        ...wordPayload,
        word_details: { ...wordPayload.word_details, star: nextStar },
      })
    } catch (error) {
      if (error instanceof ApiError) {
        setErrorMessage(error.message)
      } else {
        setErrorMessage('Failed to update word star.')
      }
    }
  }

  const onToggleKnown = async () => {
    if (!token || !wordPayload) {
      return
    }

    try {
      await toggleWordKnown(token, {
        word_id: wordPayload.word_details.word_id,
        update_to_known: !isKnown,
        quized: wordPayload.word_details.quized,
        occurrence: wordPayload.word_details.occurrence,
      })
      setWordPayload({
        ...wordPayload,
        word_details: {
          ...wordPayload.word_details,
          priority: isKnown ? 0 : -1,
        },
      })
    } catch (error) {
      if (error instanceof ApiError) {
        setErrorMessage(error.message)
      } else {
        setErrorMessage('Failed to update known status.')
      }
    }
  }

  const onPlayAudio = async () => {
    if (!wordPayload) {
      return
    }

    setAudioMessage('')
    setIsPlayingAudio(true)
    try {
      const audioResponse = await requestWordAudio(wordPayload.word_details.word, useTtsModel)
      if (audioResponse.type === 'blob') {
        const url = URL.createObjectURL(audioResponse.blob)
        const audio = new Audio(url)
        await audio.play()
        URL.revokeObjectURL(url)
      } else if (audioResponse.audio_mapping.length > 0) {
        await playStaticAudio(audioResponse.audio_mapping)
      } else {
        setAudioMessage('No audio mapping found for StaticA playback.')
      }
    } catch (error) {
      if (error instanceof ApiError) {
        setAudioMessage(error.message)
      } else {
        setAudioMessage('Failed to play audio.')
      }
    } finally {
      setIsPlayingAudio(false)
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
          <h2 className="panel-title">Word Details</h2>
        </div>
        <button className="btn btn--ghost" type="button" onClick={onReturn}>
          Return
        </button>
      </div>
      <p className="panel-copy">Review the full word profile and study controls.</p>

      {!token && (
        <div className="notice-wrap">
          <p className="notice notice--error">Login is required for word detail routes.</p>
          <Link className="btn" to="/login">
            Go To Login
          </Link>
        </div>
      )}

      {token && status === 'loading' && <p className="notice">Loading word details...</p>}
      {token && status === 'error' && <p className="notice notice--error">{errorMessage}</p>}

      {token && status === 'ok' && wordPayload && (
        <>
          <div className="detail-top-grid">
            <article className="subpanel">
              <div className="row-head">
                <h3>{wordPayload.word_details.word}</h3>
                <button
                  className={`star-btn ${wordPayload.word_details.star ? 'star-btn--active' : ''}`}
                  type="button"
                  aria-pressed={wordPayload.word_details.star}
                  onClick={onToggleStar}
                >
                  {wordPayload.word_details.star ? (
                    <span className="star-btn__label">
                      <span className="star-btn__icon">★</span>
                      <span className="star-btn__text">Starred</span>
                    </span>
                  ) : (
                    '☆ Star'
                  )}
                </button>
              </div>
              <p className="panel-copy">Spelling: {wordPayload.word_details.spelling || '-'}</p>
              <p className="panel-copy">JLPT: {wordPayload.word_details.jlpt_level || 'N0'}</p>
            </article>

            <article className="subpanel">
              <h3>Study Actions</h3>
              <div className="inline-actions">
                <button className="btn" type="button" disabled={isPlayingAudio} onClick={onPlayAudio}>
                  {isPlayingAudio ? 'Playing...' : 'Play Audio'}
                </button>
                <button className="btn btn--ghost" type="button" onClick={onToggleKnown}>
                  {isKnown ? 'Mark As Unknown' : 'Mark As Known'}
                </button>
              </div>
              <label className="toggle-line" htmlFor="audio-mode">
                <input
                  id="audio-mode"
                  type="checkbox"
                  checked={useTtsModel}
                  onChange={(event) => setUseTtsModel(event.target.checked)}
                />
                Use TTS model (off = StaticA)
              </label>
              {audioMessage && <p className="notice notice--error">{audioMessage}</p>}
            </article>
          </div>

          <article className="subpanel subpanel--full">
            <h3>Meanings and Part Of Speech</h3>
            <ul className="data-list">
              {senses.map((sense, index) => (
                <li key={`${sense.meaning}-${index}`}>
                  <strong>{sense.meaning}</strong>
                  <span>{sense.partOfSpeech}</span>
                </li>
              ))}
            </ul>
          </article>

          <article className="subpanel subpanel--full">
            <h3>Example Sentences</h3>
            {wordPayload.sen_ex.length === 0 && <p className="notice">No sentence examples found.</p>}
            {wordPayload.sen_ex.length > 0 && (
              <ol className="sentence-list">
                {wordPayload.sen_ex.map((sentence, index) => (
                  <li key={`${sentence}-${index}`}>{sentence}</li>
                ))}
              </ol>
            )}
          </article>
        </>
      )}
    </section>
  )
}
