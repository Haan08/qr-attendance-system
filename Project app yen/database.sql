-- USERS (Admins / Teachers)
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    full_name VARCHAR(100),
    email VARCHAR(100) UNIQUE NOT NULL,
    password TEXT NOT NULL
);

-- STUDENTS
CREATE TABLE IF NOT EXISTS students (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    campusid VARCHAR(100) UNIQUE NOT NULL,
    course VARCHAR(100)
);

-- QRCODES
CREATE TABLE IF NOT EXISTS qrcodes (
    id UUID PRIMARY KEY,
    course VARCHAR(100),
    scan_limit INT,
    latitude FLOAT,
    longitude FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ATTENDANCE LOGS
CREATE TABLE IF NOT EXISTS attendance_logs (
    id SERIAL PRIMARY KEY,
    campusid VARCHAR(100) REFERENCES students(campusid) ON DELETE CASCADE,
    name VARCHAR(100),
    date DATE,
    attendance VARCHAR(20),
    qr_id UUID REFERENCES qrcodes(id) ON DELETE CASCADE
);

-- Unique Constraint (for QR-based attendance)
ALTER TABLE attendance_logs
ADD CONSTRAINT IF NOT EXISTS unique_attendance_per_qr
UNIQUE (campusid, qr_id);

-- Optional Indexes
CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance_logs(date);
CREATE INDEX IF NOT EXISTS idx_qrcodes_course ON qrcodes(course);
