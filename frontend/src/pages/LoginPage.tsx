import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ApiError, loginUser } from '../lib/api'
import { setStoredTokens } from '../lib/auth'

export function LoginPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [status, setStatus] = useState<'idle' | 'submitting' | 'error'>('idle')
  const [errorMessage, setErrorMessage] = useState('')

  const registrationSuccess = useMemo(() => searchParams.get('registered') === '1', [searchParams])

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setStatus('submitting')
    setErrorMessage('')

    try {
      const tokens = await loginUser({ username: username.trim(), password })
      setStoredTokens(tokens)
      navigate('/home', { replace: true })
    } catch (error) {
      setStatus('error')
      if (error instanceof ApiError) {
        setErrorMessage(error.message)
      } else {
        setErrorMessage('Login failed. Please try again.')
      }
    }
  }

  return (
    <section className="panel panel--narrow">
      <p className="eyebrow">Auth</p>
      <h2 className="panel-title">Login</h2>
      <p className="panel-copy">
        Sign in to access quiz, view, and progress endpoints that require a
        valid access token.
      </p>

      {registrationSuccess && <p className="notice notice--success">Registration complete. You can log in now.</p>}
      {status === 'error' && <p className="notice notice--error">{errorMessage}</p>}

      <form className="stack-form" onSubmit={onSubmit}>
        <label className="field-label" htmlFor="username">
          Username
        </label>
        <input
          id="username"
          className="field-input"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          autoComplete="username"
          required
        />

        <label className="field-label" htmlFor="password">
          Password
        </label>
        <input
          id="password"
          className="field-input"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="current-password"
          required
        />

        <button className="btn btn--block" type="submit" disabled={status === 'submitting'}>
          {status === 'submitting' ? 'Logging In...' : 'Login'}
        </button>
      </form>

      <div className="inline-actions">
        <Link className="btn" to="/home">
          Back Home
        </Link>
        <Link className="btn btn--ghost" to="/register">
          Go To Register
        </Link>
      </div>
    </section>
  )
}
