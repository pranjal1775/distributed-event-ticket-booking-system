import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'
import { Spinner } from '../components/BookingCard'

export default function EventsPage() {
  const [events, setEvents]   = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch]   = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    api.get('/events/').then(r => setEvents(r.data)).finally(() => setLoading(false))
  }, [])

  const filtered = events.filter(e =>
    e.name.toLowerCase().includes(search.toLowerCase()) ||
    e.city.toLowerCase().includes(search.toLowerCase())
  )

  if (loading) return <Spinner />

  return (
    <div className="page">
      <div className="section-header">
        <div>
          <h1 className="page-title">Events</h1>
          <p className="page-subtitle">{events.length} upcoming events</p>
        </div>
        <input
          style={{ width: '220px' }}
          placeholder="Search events or city…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      {filtered.length === 0 ? (
        <p className="empty-state">No events found.</p>
      ) : (
        <div className="event-grid">
          {filtered.map(event => (
            <div key={event.id} className="card event-card" onClick={() => navigate(`/events/${event.id}`)}>
              <div className="event-card-header">
                <span className="event-name">{event.name}</span>
                <span className="event-price">₹{Number(event.price).toFixed(0)}</span>
              </div>
              <div className="event-meta">
                <span>📅 {new Date(event.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}</span>
                <span>📍 {event.venue}, {event.city}</span>
                <span>🕐 {event.time?.slice(0, 5)}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '.75rem' }}>
                <span className="badge">{event.available_seats} seats left</span>
                {event.available_seats === 0 && <span className="badge badge-danger">Sold Out</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
