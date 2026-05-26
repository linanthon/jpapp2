import { Link } from 'react-router-dom'

export function RegisterPage() {
  return (
    <section className="panel panel--narrow">
      <p className="eyebrow">Auth</p>
      <h2 className="panel-title">Register</h2>
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
