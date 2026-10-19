export default function SeatGrid({ seats, selected, onToggle }) {
  // Group seats by row letter
  const rows = seats.reduce((acc, seat) => {
    const row = seat.seat_label[0]
    if (!acc[row]) acc[row] = []
    acc[row].push(seat)
    return acc
  }, {})

  return (
    <div className="seat-section">
      <div className="seat-legend">
        <span><span className="seat-dot seat-dot-available" /> Available</span>
        <span><span className="seat-dot seat-dot-selected"  /> Selected</span>
        <span><span className="seat-dot seat-dot-booked"    /> Booked</span>
      </div>

      {/* Stage indicator */}
      <div style={{ textAlign: 'center', marginBottom: '1.25rem' }}>
        <div style={{
          display: 'inline-block', padding: '.3rem 3rem',
          background: 'var(--border)', borderRadius: '4px',
          fontSize: '.72rem', color: 'var(--muted)', letterSpacing: '.1em',
        }}>STAGE</div>
      </div>

      {Object.entries(rows).map(([rowLabel, rowSeats]) => (
        <div key={rowLabel} className="seat-row">
          <span className="seat-row-label">{rowLabel}</span>
          {rowSeats
            .sort((a, b) => parseInt(a.seat_label.slice(1)) - parseInt(b.seat_label.slice(1)))
            .map(seat => {
              const isBooked   = seat.status === 'booked'
              const isSelected = selected.includes(seat.id)
              const cls = isBooked ? 'seat seat-booked'
                        : isSelected ? 'seat seat-selected'
                        : 'seat seat-available'
              return (
                <div
                  key={seat.id}
                  className={cls}
                  title={seat.seat_label}
                  onClick={() => !isBooked && onToggle(seat.id)}
                >
                  {seat.seat_label.slice(1)}
                </div>
              )
            })}
        </div>
      ))}
    </div>
  )
}
