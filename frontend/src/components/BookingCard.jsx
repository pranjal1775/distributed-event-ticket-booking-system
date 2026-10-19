export function Spinner() {
  return <div className="spinner" />
}

export function BookingCard({ booking }) {
  const statusColor = booking.booking_status === 'confirmed' ? 'badge-success' : 'badge-danger'
  return (
    <div className="card">
      <div className="booking-card-header">
        <div>
          <span className="booking-id">Booking #{booking.id}</span>
          <div style={{ fontSize: '.82rem', color: 'var(--muted)', marginTop: '.15rem' }}>
            Event #{booking.event_id} · {new Date(booking.created_at).toLocaleDateString()}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div className="booking-amount">₹{Number(booking.total_amount).toFixed(2)}</div>
          <span className={`badge ${statusColor}`}>{booking.booking_status}</span>
        </div>
      </div>
      <hr className="divider" />
      <div style={{ fontSize: '.8rem', color: 'var(--muted)', marginBottom: '.4rem' }}>Seats</div>
      <div className="booking-seats">
        {booking.items.map(item => (
          <span key={item.id} className="seat-tag">{item.seat_label}</span>
        ))}
      </div>
      <div style={{ fontSize: '.75rem', color: 'var(--muted)', marginTop: '.75rem' }}>
        Clock #{booking.logical_clock} · Payment: {booking.payment_status}
      </div>
    </div>
  )
}
