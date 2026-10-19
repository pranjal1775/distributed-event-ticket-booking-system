import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'
import { useAuth } from '../context/AuthContext'
import { Spinner, BookingCard } from '../components/BookingCard'

export default function BookingsPage() {
  const { user }  = useAuth()
  const navigate  = useNavigate()
  const [bookings, setBookings] = useState([])
  const [loading, setLoading]   = useState(true)

  useEffect(() => {
    if (!user) { navigate('/login'); return }
    api.get('/bookings/my').then(r => setBookings(r.data)).finally(() => setLoading(false))
  }, [user])

  if (loading) return <Spinner />

  return (
    <div className="page">
      <h1 className="page-title">My Bookings</h1>
      <p className="page-subtitle">{bookings.length} booking{bookings.length !== 1 ? 's' : ''}</p>

      {bookings.length === 0 ? (
        <div className="empty-state">
          <p>No bookings yet.</p>
          <button className="btn btn-primary" style={{ marginTop: '1rem' }} onClick={() => navigate('/')}>
            Browse Events
          </button>
        </div>
      ) : (
        <div className="booking-list">
          {bookings.map(b => <BookingCard key={b.id} booking={b} />)}
        </div>
      )}
    </div>
  )
}
