CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    full_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    age INTEGER NOT NULL,
    gender TEXT NOT NULL,
    consent_given INTEGER NOT NULL DEFAULT 0,

    -- network / device fingerprint
    mac_address TEXT,
    client_ip TEXT,
    user_agent TEXT,
    os_type TEXT,
    os_version TEXT,
    device_type TEXT,
    device_brand TEXT,
    browser TEXT,

    -- tier / access
    tier INTEGER NOT NULL,
    access_code TEXT,
    duration_minutes INTEGER,
    download_kbits INTEGER,
    upload_kbits INTEGER,

    -- payment
    amount_paid_cents INTEGER DEFAULT 0,
    payment_method TEXT,             -- card / apple_pay / google_pay / cashapp / code / n/a
    payment_reference TEXT,          -- stripe checkout session id
    payment_status TEXT DEFAULT 'pending',  -- pending / paid / free / failed

    -- session lifecycle
    session_start TIMESTAMP,
    session_end TIMESTAMP,
    granted INTEGER NOT NULL DEFAULT 0,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS access_codes (
    code TEXT PRIMARY KEY,
    label TEXT,
    max_uses INTEGER DEFAULT 0,      -- 0 = unlimited
    uses_count INTEGER DEFAULT 0,
    duration_minutes INTEGER DEFAULT 240,
    download_kbits INTEGER DEFAULT 4000,
    upload_kbits INTEGER DEFAULT 1000,
    active INTEGER DEFAULT 1,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_mac ON users(mac_address);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_status ON users(payment_status);
