import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Navbar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate('/login')
  }

  return (
    <nav className="navbar">
      <Link to="/" className="navbar-brand">🎟 TicketBook</Link>
      <div className="navbar-links">
        <Link to="/">Events</Link>
        {user ? (
          <>
            <Link to="/bookings">My Bookings</Link>
            <Link to="/notifications">Notifications</Link>
            <button className="btn btn-ghost" style={{ padding: '.35rem .9rem' }} onClick={handleLogout}>
              Logout
            </button>
          </>
        ) : (
          <>
            <Link to="/login">Login</Link>
            <Link to="/register">
              <button className="btn btn-primary" style={{ padding: '.35rem .9rem' }}>Register</button>
            </Link>
          </>
        )}
      </div>
    </nav>
  )
}
