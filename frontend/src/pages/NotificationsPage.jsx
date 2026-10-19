import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'
import { useAuth } from '../context/AuthContext'
import { Spinner } from '../components/BookingCard'

export default function NotificationsPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [notifs, setNotifs]   = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!user) { navigate('/login'); return }
    api.get('/notifications/my').then(r => setNotifs(r.data)).finally(() => setLoading(false))
  }, [user])

  if (loading) return <Spinner />

  return (
    <div className="page">
      <h1 className="page-title">Notifications</h1>
      <p className="page-subtitle">{notifs.length} notification{notifs.length !== 1 ? 's' : ''}</p>

      {notifs.length === 0 ? (
        <p className="empty-state">No notifications yet.</p>
      ) : (
        <div className="notif-list">
          {[...notifs].reverse().map(n => (
            <div key={n.id} className="card notif-card">
              <span className="notif-icon">🎟</span>
              <div className="notif-body">
                <p className="notif-msg">{n.message}</p>
                <p className="notif-time">
                  Booking #{n.booking_id} · {new Date(n.created_at).toLocaleString()} · Clock #{n.logical_clock}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
