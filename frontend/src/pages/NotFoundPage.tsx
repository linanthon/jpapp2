import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <section className="panel panel--narrow">
      <p className="eyebrow">404</p>
      <h2 className="panel-title">Page Not Found</h2>
      <p className="panel-copy">The route does not exist in the current app.</p>
      <div className="inline-actions">
        <Link className="btn" to="/home">
          Back Home
        </Link>
      </div>
    </section>
  )
}
