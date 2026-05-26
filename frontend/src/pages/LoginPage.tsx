import { Link } from 'react-router-dom'

export function LoginPage() {
  return (
    <section className="panel panel--narrow">
      <p className="eyebrow">Auth</p>
      <h2 className="panel-title">Login</h2>
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
