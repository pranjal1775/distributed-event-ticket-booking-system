-- ============================================================
-- Distributed Event Ticket Booking System
-- Database Schema and Seed Data
-- ============================================================

-- ============================================================
-- USERS TABLE
-- Owned by: user-service
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name       VARCHAR(255) NOT NULL,
    role            VARCHAR(20)  NOT NULL DEFAULT 'user',
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    CONSTRAINT users_role_check CHECK (role IN ('user', 'admin'))
);

-- ============================================================
-- EVENTS TABLE
-- Owned by: event-service
-- ============================================================
CREATE TABLE IF NOT EXISTS events (
    id               SERIAL PRIMARY KEY,
    name             VARCHAR(255)   NOT NULL,
    description      TEXT,
    date             DATE           NOT NULL,
    time             TIME           NOT NULL,
    venue            VARCHAR(255)   NOT NULL,
    city             VARCHAR(100)   NOT NULL,
    total_seats      INTEGER        NOT NULL CHECK (total_seats > 0),
    available_seats  INTEGER        NOT NULL CHECK (available_seats >= 0),
    price            NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
    status           VARCHAR(20)    NOT NULL DEFAULT 'active',
    created_at       TIMESTAMP      NOT NULL DEFAULT NOW(),
    CONSTRAINT events_status_check CHECK (status IN ('active', 'cancelled', 'completed')),
    CONSTRAINT events_seats_check CHECK (available_seats <= total_seats)
);

-- ============================================================
-- SEATS TABLE
-- Owned by: event-service
-- ============================================================
CREATE TABLE IF NOT EXISTS seats (
    id          SERIAL PRIMARY KEY,
    event_id    INTEGER     NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    seat_label  VARCHAR(10) NOT NULL,
    status      VARCHAR(20) NOT NULL DEFAULT 'available',
    CONSTRAINT seats_status_check CHECK (status IN ('available', 'booked')),
    CONSTRAINT seats_unique_label UNIQUE (event_id, seat_label)
);

-- ============================================================
-- BOOKINGS TABLE
-- Owned by: booking-service
-- ============================================================
CREATE TABLE IF NOT EXISTS bookings (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER        NOT NULL,
    event_id        INTEGER        NOT NULL,
    total_amount    NUMERIC(10, 2) NOT NULL,
    payment_status  VARCHAR(20)    NOT NULL DEFAULT 'pending',
    booking_status  VARCHAR(20)    NOT NULL DEFAULT 'pending',
    logical_clock   INTEGER,
    created_at      TIMESTAMP      NOT NULL DEFAULT NOW(),
    CONSTRAINT bookings_payment_status_check CHECK (payment_status IN ('pending', 'paid', 'failed')),
    CONSTRAINT bookings_booking_status_check CHECK (booking_status IN ('pending', 'confirmed', 'cancelled'))
);

-- ============================================================
-- BOOKING ITEMS TABLE
-- Owned by: booking-service
-- UNIQUE(seat_id) prevents the same seat from appearing in
-- two different bookings — database-level double-booking guard
-- ============================================================
CREATE TABLE IF NOT EXISTS booking_items (
    id          SERIAL PRIMARY KEY,
    booking_id  INTEGER     NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    seat_id     INTEGER     NOT NULL REFERENCES seats(id),
    seat_label  VARCHAR(10) NOT NULL,
    CONSTRAINT booking_items_unique_seat UNIQUE (seat_id)
);

-- ============================================================
-- NOTIFICATIONS TABLE
-- Owned by: notification-service
-- ============================================================
CREATE TABLE IF NOT EXISTS notifications (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER   NOT NULL,
    booking_id    INTEGER   NOT NULL,
    message       TEXT      NOT NULL,
    status        VARCHAR(20) NOT NULL DEFAULT 'sent',
    logical_clock INTEGER,
    created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT notifications_status_check CHECK (status IN ('sent', 'pending'))
);

-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_seats_event_id     ON seats(event_id);
CREATE INDEX IF NOT EXISTS idx_seats_status       ON seats(event_id, status);
CREATE INDEX IF NOT EXISTS idx_bookings_user_id   ON bookings(user_id);
CREATE INDEX IF NOT EXISTS idx_bookings_event_id  ON bookings(event_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);

-- ============================================================
-- SEED DATA
-- ============================================================

-- Admin user
-- Password: admin123 (bcrypt hash)
INSERT INTO users (email, hashed_password, full_name, role) VALUES
(
    'admin@ticketbook.com',
    '$2b$12$UGRqVh5IoVNnZT5Mko/J.ujfNsIpFIx8lylOvk7rSwtN5wxv3AiJO',
    'System Admin',
    'admin'
)
ON CONFLICT (email) DO NOTHING;

-- Regular test user
-- Password: user123 (bcrypt hash)
INSERT INTO users (email, hashed_password, full_name, role) VALUES
(
    'user@ticketbook.com',
    '$2b$12$f7ORW/OyeJ/6nf8kr7YbrejmTIgTeg2.kFGCv7S9T445qbIhSUNfa',
    'Test User',
    'user'
)
ON CONFLICT (email) DO NOTHING;

-- Sample events
INSERT INTO events (name, description, date, time, venue, city, total_seats, available_seats, price, status) VALUES
(
    'Tech Conference 2025',
    'Annual technology conference featuring talks on AI, cloud computing, and distributed systems.',
    '2025-09-15',
    '09:00:00',
    'Convention Center Hall A',
    'Bangalore',
    40,
    40,
    1500.00,
    'active'
),
(
    'Music Concert — Echoes Live',
    'An evening of live music featuring indie and fusion bands.',
    '2025-08-20',
    '19:00:00',
    'Open Air Amphitheatre',
    'Mumbai',
    40,
    40,
    800.00,
    'active'
),
(
    'Startup Meetup',
    'Network with founders, investors, and developers in the startup ecosystem.',
    '2025-07-10',
    '18:00:00',
    'Innovation Hub',
    'Pune',
    20,
    20,
    200.00,
    'active'
),
(
    'College Cultural Fest',
    'Annual cultural festival with performances, competitions, and exhibitions.',
    '2025-10-05',
    '10:00:00',
    'University Auditorium',
    'Delhi',
    40,
    40,
    100.00,
    'active'
),
(
    'Sports Day — Athletics Meet',
    'Inter-college athletics competition open to all spectators.',
    '2025-11-12',
    '08:00:00',
    'City Sports Complex',
    'Chennai',
    30,
    30,
    50.00,
    'active'
)
ON CONFLICT DO NOTHING;

-- ============================================================
-- SEAT GENERATION
-- Generate seats for each event: rows A-D, seats 1-10
-- Tech Conference and Music Concert: 4 rows x 10 = 40 seats
-- Startup Meetup: 2 rows x 10 = 20 seats
-- Cultural Fest: 4 rows x 10 = 40 seats
-- Sports Day: 3 rows x 10 = 30 seats
-- ============================================================

-- Tech Conference 2025 (event id 1) — rows A,B,C,D x 10
INSERT INTO seats (event_id, seat_label) VALUES
(1,'A1'),(1,'A2'),(1,'A3'),(1,'A4'),(1,'A5'),(1,'A6'),(1,'A7'),(1,'A8'),(1,'A9'),(1,'A10'),
(1,'B1'),(1,'B2'),(1,'B3'),(1,'B4'),(1,'B5'),(1,'B6'),(1,'B7'),(1,'B8'),(1,'B9'),(1,'B10'),
(1,'C1'),(1,'C2'),(1,'C3'),(1,'C4'),(1,'C5'),(1,'C6'),(1,'C7'),(1,'C8'),(1,'C9'),(1,'C10'),
(1,'D1'),(1,'D2'),(1,'D3'),(1,'D4'),(1,'D5'),(1,'D6'),(1,'D7'),(1,'D8'),(1,'D9'),(1,'D10')
ON CONFLICT DO NOTHING;

-- Music Concert (event id 2) — rows A,B,C,D x 10
INSERT INTO seats (event_id, seat_label) VALUES
(2,'A1'),(2,'A2'),(2,'A3'),(2,'A4'),(2,'A5'),(2,'A6'),(2,'A7'),(2,'A8'),(2,'A9'),(2,'A10'),
(2,'B1'),(2,'B2'),(2,'B3'),(2,'B4'),(2,'B5'),(2,'B6'),(2,'B7'),(2,'B8'),(2,'B9'),(2,'B10'),
(2,'C1'),(2,'C2'),(2,'C3'),(2,'C4'),(2,'C5'),(2,'C6'),(2,'C7'),(2,'C8'),(2,'C9'),(2,'C10'),
(2,'D1'),(2,'D2'),(2,'D3'),(2,'D4'),(2,'D5'),(2,'D6'),(2,'D7'),(2,'D8'),(2,'D9'),(2,'D10')
ON CONFLICT DO NOTHING;

-- Startup Meetup (event id 3) — rows A,B x 10
INSERT INTO seats (event_id, seat_label) VALUES
(3,'A1'),(3,'A2'),(3,'A3'),(3,'A4'),(3,'A5'),(3,'A6'),(3,'A7'),(3,'A8'),(3,'A9'),(3,'A10'),
(3,'B1'),(3,'B2'),(3,'B3'),(3,'B4'),(3,'B5'),(3,'B6'),(3,'B7'),(3,'B8'),(3,'B9'),(3,'B10')
ON CONFLICT DO NOTHING;

-- College Cultural Fest (event id 4) — rows A,B,C,D x 10
INSERT INTO seats (event_id, seat_label) VALUES
(4,'A1'),(4,'A2'),(4,'A3'),(4,'A4'),(4,'A5'),(4,'A6'),(4,'A7'),(4,'A8'),(4,'A9'),(4,'A10'),
(4,'B1'),(4,'B2'),(4,'B3'),(4,'B4'),(4,'B5'),(4,'B6'),(4,'B7'),(4,'B8'),(4,'B9'),(4,'B10'),
(4,'C1'),(4,'C2'),(4,'C3'),(4,'C4'),(4,'C5'),(4,'C6'),(4,'C7'),(4,'C8'),(4,'C9'),(4,'C10'),
(4,'D1'),(4,'D2'),(4,'D3'),(4,'D4'),(4,'D5'),(4,'D6'),(4,'D7'),(4,'D8'),(4,'D9'),(4,'D10')
ON CONFLICT DO NOTHING;

-- Sports Day (event id 5) — rows A,B,C x 10
INSERT INTO seats (event_id, seat_label) VALUES
(5,'A1'),(5,'A2'),(5,'A3'),(5,'A4'),(5,'A5'),(5,'A6'),(5,'A7'),(5,'A8'),(5,'A9'),(5,'A10'),
(5,'B1'),(5,'B2'),(5,'B3'),(5,'B4'),(5,'B5'),(5,'B6'),(5,'B7'),(5,'B8'),(5,'B9'),(5,'B10'),
(5,'C1'),(5,'C2'),(5,'C3'),(5,'C4'),(5,'C5'),(5,'C6'),(5,'C7'),(5,'C8'),(5,'C9'),(5,'C10')
ON CONFLICT DO NOTHING;
