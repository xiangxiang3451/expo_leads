CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    company TEXT NOT NULL
        CHECK (length(trim(company)) BETWEEN 1 AND 200),

    contact TEXT NOT NULL
        CHECK (length(trim(contact)) BETWEEN 1 AND 200),

    product TEXT NOT NULL
        CHECK (length(trim(product)) BETWEEN 1 AND 2000),

    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'contacted', 'quoted')),

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);