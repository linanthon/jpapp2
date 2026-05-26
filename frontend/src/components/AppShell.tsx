import { NavLink, Outlet } from 'react-router-dom'

const navItems = [
  { to: '/home', label: 'Home' },
  { to: '/insert', label: 'Insert' },
  { to: '/view', label: 'View' },
  { to: '/quiz', label: 'Quiz' },
  { to: '/progress', label: 'Progress' },
]

export function AppShell() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <p className="kicker">JP-EN Learning</p>
          <h1 className="title">Study Console</h1>
        </div>
        <nav className="app-nav" aria-label="Primary">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `nav-chip ${isActive ? 'nav-chip--active' : ''}`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>

      <main className="content-wrap">
        <Outlet />
      </main>
    </div>
  )
}
