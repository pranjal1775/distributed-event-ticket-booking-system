import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import api from '../api/client'
import { useAuth } from '../context/AuthContext'
import SeatGrid from '../components/SeatGrid'
import { Spinner } from '../components/BookingCard'

export default function EventDetailPage() {
  const { id }   = useParams()
  const { user } = useAuth()
  const navigate = useNavigate()

  const [event, setEvent]       = useState(null)
  const [seats, setSeats]       = useState([])
  const [selected, setSelected] = useState([])
  const [loading, setLoading]   = useState(true)
  const [booking, setBooking]   = useState(false)
  const [error, setError]       = useState('')
  const [success, setSuccess]   = useState('')

  useEffect(() => {
    Promise.all([
      api.get(`/events/${id}`),
      api.get(`/events/${id}/seats`),
    ]).then(([evRes, seatsRes]) => {
      setEvent(evRes.data)
      setSeats(seatsRes.data)
    }).finally(() => setLoading(false))
  }, [id])

  function toggleSeat(seatId) {
    setSelected(prev =>
      prev.includes(seatId) ? prev.filter(s => s !== seatId) : [...prev, seatId]
    )
  }

  async function handleBook() {
    if (!user) { navigate('/login'); return }
    setError('')
    setSuccess('')
    setBooking(true)
    try {
      await api.post('/bookings/', { event_id: Number(id), seat_ids: selected })
      setSuccess('Booking confirmed! 🎉')
      setSelected([])
      // Refresh seats
      const r = await api.get(`/events/${id}/seats`)
      setSeats(r.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Booking failed')
    } finally {
      setBooking(false)
    }
  }

  if (loading) return <Spinner />
  if (!event)  return <p className="empty-state">Event not found.</p>

  const selectedSeats = seats.filter(s => selected.includes(s.id))
  const total = selectedSeats.length * Number(event.price)

  return (
    <div className="page">
      <button className="btn btn-ghost" style={{ marginBottom: '1.25rem', fontSize: '.82rem' }} onClick={() => navigate(-1)}>
        ← Back
      </button>

      <div className="detail-layout">
        {/* Left: event info + seat grid */}
        <div>
          <h1 className="page-title">{event.name}</h1>
          <div className="detail-meta">
            <span>📅 {new Date(event.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' })}</span>
            <span>🕐 {event.time?.slice(0, 5)}</span>
            <span>📍 {event.venue}, {event.city}</span>
            <span>💺 {event.available_seats} available</span>
          </div>
          {event.description && (
            <p style={{ color: 'var(--muted)', fontSize: '.88rem', marginBottom: '1rem' }}>{event.description}</p>
          )}
          <hr className="divider" />
          <p style={{ fontSize: '.88rem', color: 'var(--muted)' }}>Select your seats below</p>
          <SeatGrid seats={seats} selected={selected} onToggle={toggleSeat} />
        </div>

        {/* Right: booking summary */}
        <div className="booking-summary">
          <h3 style={{ fontWeight: 700, marginBottom: '1rem' }}>Booking Summary</h3>

          <div className="summary-row">
            <span>Price per seat</span>
            <span>₹{Number(event.price).toFixed(2)}</span>
          </div>
          <div className="summary-row">
            <span>Seats selected</span>
            <span>{selected.length}</span>
          </div>

          {selected.length > 0 && (
            <div className="selected-seats">
              {selectedSeats.map(s => <span key={s.id} className="seat-tag">{s.seat_label}</span>)}
            </div>
          )}

          <div className="summary-total">
            <span>Total</span>
            <span>₹{total.toFixed(2)}</span>
          </div>

          {error   && <p className="error-msg" style={{ marginTop: '.75rem' }}>{error}</p>}
          {success && <p style={{ color: 'var(--success)', fontSize: '.85rem', marginTop: '.75rem' }}>{success}</p>}

          <button
            className="btn btn-primary btn-full"
            style={{ marginTop: '1rem' }}
            disabled={selected.length === 0 || booking}
            onClick={handleBook}
          >
            {booking ? 'Processing…' : `Book ${selected.length || ''} Seat${selected.length !== 1 ? 's' : ''}`}
          </button>

          {!user && (
            <p style={{ fontSize: '.78rem', color: 'var(--muted)', textAlign: 'center', marginTop: '.6rem' }}>
              You need to <a href="/login">sign in</a> to book
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
