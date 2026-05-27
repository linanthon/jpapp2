import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, getInsertJob, queueInsertFile, queueInsertString } from '../lib/api'
import { getAccessToken } from '../lib/auth'

function createIdempotencyKey() {
  if ('randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `idem-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function InsertPage() {
  const token = getAccessToken()
  const [mode, setMode] = useState<'string' | 'file'>('string')
  const [stringName, setStringName] = useState('')
  const [stringBody, setStringBody] = useState('')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [status, setStatus] = useState<'idle' | 'submitting' | 'error' | 'ok'>('idle')
  const [jobInfo, setJobInfo] = useState<{ jobId: string; batchId: string } | null>(null)
  const [jobStatus, setJobStatus] = useState('')
  const [errorMessage, setErrorMessage] = useState('')

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!token) {
      return
    }

    setStatus('submitting')
    setErrorMessage('')
    setJobStatus('')

    try {
      const idempotencyKey = createIdempotencyKey()
      const result =
        mode === 'string'
          ? await queueInsertString(
              token,
              { stringName: stringName.trim(), stringBody },
              idempotencyKey,
            )
          : selectedFile
            ? await queueInsertFile(token, selectedFile, idempotencyKey)
            : null

      if (!result) {
        setStatus('error')
        setErrorMessage('Please choose a file first.')
        return
      }

      setJobInfo({ jobId: result.job_id, batchId: result.batch_id })
      setStatus('ok')
    } catch (error) {
      setStatus('error')
      if (error instanceof ApiError) {
        setErrorMessage(error.message)
      } else {
        setErrorMessage('Failed to queue insert job.')
      }
    }
  }

  const refreshJobStatus = async () => {
    if (!token || !jobInfo) {
      return
    }

    setJobStatus('Checking...')
    try {
      const result = await getInsertJob(token, jobInfo.jobId)
      setJobStatus(String(result.status ?? 'UNKNOWN'))
    } catch (error) {
      if (error instanceof ApiError) {
        setJobStatus(`Error: ${error.message}`)
      } else {
        setJobStatus('Error checking status')
      }
    }
  }

  return (
    <section className="panel">
      <p className="eyebrow">Insert</p>
      <h2 className="panel-title">Upload Content</h2>
      <p className="panel-copy">
        Queue background insert jobs with either text input or direct file upload.
      </p>

      {!token && (
        <div className="notice-wrap">
          <p className="notice notice--error">Login is required to queue insert jobs.</p>
          <Link className="btn" to="/login">
            Go To Login
          </Link>
        </div>
      )}

      {token && (
        <>
          {status === 'error' && <p className="notice notice--error">{errorMessage}</p>}

          <div className="inline-actions">
            <button
              className={`btn ${mode === 'string' ? '' : 'btn--ghost'}`}
              type="button"
              onClick={() => {
                setMode('string')
                setErrorMessage('')
              }}
            >
              Insert String
            </button>
            <button
              className={`btn ${mode === 'file' ? '' : 'btn--ghost'}`}
              type="button"
              onClick={() => {
                setMode('file')
                setErrorMessage('')
              }}
            >
              Upload File
            </button>
          </div>

          <form className="stack-form" onSubmit={onSubmit}>
            {mode === 'string' && (
              <>
                <label className="field-label" htmlFor="string-name">
                  Book Name
                </label>
                <input
                  id="string-name"
                  className="field-input"
                  value={stringName}
                  onChange={(event) => setStringName(event.target.value)}
                  placeholder="example_book"
                  required
                />

                <label className="field-label" htmlFor="string-body">
                  Japanese Text
                </label>
                <textarea
                  id="string-body"
                  className="field-input field-textarea"
                  value={stringBody}
                  onChange={(event) => setStringBody(event.target.value)}
                  placeholder="Paste Japanese content to process"
                  required
                />
              </>
            )}

            {mode === 'file' && (
              <>
                <label className="field-label" htmlFor="insert-file">
                  File
                </label>
                <input
                  id="insert-file"
                  className="field-input"
                  type="file"
                  accept=".txt,.pdf,.docx"
                  onChange={(event) => {
                    setSelectedFile(event.target.files?.[0] ?? null)
                  }}
                  required
                />
                <p className="panel-copy">Allowed types: .txt, .pdf, .docx</p>
              </>
            )}

            <button className="btn" type="submit" disabled={status === 'submitting'}>
              {status === 'submitting' ? 'Queueing...' : mode === 'string' ? 'Queue String Insert' : 'Queue File Upload'}
            </button>
          </form>

          {jobInfo && (
            <div className="subpanel subpanel--full">
              <h3>Latest Job</h3>
              <p className="panel-copy">job_id: {jobInfo.jobId}</p>
              <p className="panel-copy">batch_id: {jobInfo.batchId}</p>
              <div className="inline-actions">
                <button className="btn btn--ghost" type="button" onClick={refreshJobStatus}>
                  Refresh Status
                </button>
              </div>
              {jobStatus && <p className="notice">{jobStatus}</p>}
            </div>
          )}
        </>
      )}
    </section>
  )
}
