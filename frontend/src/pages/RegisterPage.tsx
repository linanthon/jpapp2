import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError, registerUser } from '../lib/api'

export function RegisterPage() {
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [status, setStatus] = useState<'idle' | 'submitting' | 'error'>('idle')
  const [errorMessage, setErrorMessage] = useState('')

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setErrorMessage('')

    if (password !== confirmPassword) {
      setStatus('error')
      setErrorMessage('Passwords do not match.')
      return
    }

    setStatus('submitting')
    try {
      await registerUser({
        username: username.trim(),
        email: email.trim(),
        password,
      })
      navigate('/login?registered=1', { replace: true })
    } catch (error) {
      setStatus('error')
      if (error instanceof ApiError) {
        setErrorMessage(error.message)
      } else {
        setErrorMessage('Registration failed. Please try again.')
      }
    }
  }

  return (
    <section className="panel panel--narrow">
      <p className="eyebrow">Auth</p>
      <h2 className="panel-title">Register</h2>
      <p className="panel-copy">
        Create an account to unlock personalized quiz progress and saved study
        data.
      </p>

      {status === 'error' && <p className="notice notice--error">{errorMessage}</p>}

      <form className="stack-form" onSubmit={onSubmit}>
        <label className="field-label" htmlFor="register-username">
          Username
        </label>
        <input
          id="register-username"
          className="field-input"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          autoComplete="username"
          required
        />

        <label className="field-label" htmlFor="register-email">
          Email
        </label>
        <input
          id="register-email"
          className="field-input"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          autoComplete="email"
          required
        />

        <label className="field-label" htmlFor="register-password">
          Password
        </label>
        <input
          id="register-password"
          className="field-input"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="new-password"
          required
        />

        <label className="field-label" htmlFor="register-confirm-password">
          Confirm Password
        </label>
        <input
          id="register-confirm-password"
          className="field-input"
          type="password"
          value={confirmPassword}
          onChange={(event) => setConfirmPassword(event.target.value)}
          autoComplete="new-password"
          required
        />

        <button className="btn btn--block" type="submit" disabled={status === 'submitting'}>
          {status === 'submitting' ? 'Creating Account...' : 'Create Account'}
        </button>
      </form>

      <div className="inline-actions">
        <Link className="btn" to="/home">
          Back Home
        </Link>
        <Link className="btn btn--ghost" to="/login">
          Go To Login
        </Link>
      </div>
    </section>
  )
}
