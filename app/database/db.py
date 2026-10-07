"""
ShopMate database — PostgreSQL schema, initialisation, and seed data.

Public API:
  init_schema()  — create all tables (idempotent, called at startup)
  seed_data()    — insert demo data if tables are empty
"""
import logging
from collections.abc import AsyncGenerator
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.engine import async_session, engine

logger = logging.getLogger("shopmate.db")


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id          TEXT PRIMARY KEY,
    email            TEXT UNIQUE NOT NULL,
    password_hash    TEXT NOT NULL,
    name             TEXT NOT NULL DEFAULT '',
    shipping_address TEXT DEFAULT '',
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_preferences (
    id         SERIAL PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    pref_key   TEXT NOT NULL,
    pref_value TEXT NOT NULL,
    source     TEXT DEFAULT 'agent',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, pref_key)
);

CREATE TABLE IF NOT EXISTS products (
    product_key TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    price       INTEGER NOT NULL,
    stock       INTEGER DEFAULT 0,
    rating      REAL DEFAULT 0,
    reviews     INTEGER DEFAULT 0,
    description TEXT,
    category    TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS product_offers (
    id          SERIAL PRIMARY KEY,
    product_key TEXT NOT NULL REFERENCES products(product_key) ON DELETE CASCADE,
    offer_text  TEXT NOT NULL,
    active      BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS product_synonyms (
    id          SERIAL PRIMARY KEY,
    product_key TEXT NOT NULL REFERENCES products(product_key) ON DELETE CASCADE,
    synonym     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_product_synonyms_synonym ON product_synonyms(synonym);
CREATE INDEX IF NOT EXISTS idx_product_synonyms_key    ON product_synonyms(product_key);

CREATE TABLE IF NOT EXISTS price_history (
    id          SERIAL PRIMARY KEY,
    product_key TEXT NOT NULL REFERENCES products(product_key) ON DELETE CASCADE,
    price       INTEGER NOT NULL,
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_price_history_product ON price_history(product_key, recorded_at DESC);

CREATE TABLE IF NOT EXISTS coupons (
    code         TEXT PRIMARY KEY,
    type         TEXT NOT NULL,
    value        REAL NOT NULL,
    min_order    REAL DEFAULT 0,
    max_discount REAL DEFAULT 0,
    description  TEXT,
    active       BOOLEAN DEFAULT TRUE,
    expires_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cart_items (
    id          SERIAL PRIMARY KEY,
    session_id  TEXT NOT NULL,
    user_id     TEXT REFERENCES users(user_id) ON DELETE SET NULL,
    product_key TEXT NOT NULL REFERENCES products(product_key) ON DELETE CASCADE,
    quantity    INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    added_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(session_id, product_key)
);
CREATE INDEX IF NOT EXISTS idx_cart_items_session ON cart_items(session_id);

CREATE TABLE IF NOT EXISTS cart_sessions (
    session_id  TEXT PRIMARY KEY,
    user_id     TEXT REFERENCES users(user_id) ON DELETE SET NULL,
    coupon_code TEXT REFERENCES coupons(code) ON DELETE SET NULL,
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orders (
    order_id     TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    status       TEXT NOT NULL DEFAULT 'Processing',
    subtotal     REAL NOT NULL,
    discount     REAL DEFAULT 0,
    tax          REAL DEFAULT 0,
    delivery_fee REAL DEFAULT 0,
    total        REAL NOT NULL,
    coupon_code  TEXT,
    carrier      TEXT,
    tracking_num TEXT,
    placed_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id, placed_at DESC);

CREATE TABLE IF NOT EXISTS order_items (
    id          SERIAL PRIMARY KEY,
    order_id    TEXT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    product_key TEXT,
    name        TEXT NOT NULL,
    price       INTEGER NOT NULL,
    quantity    INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);

CREATE TABLE IF NOT EXISTS order_timeline (
    id          SERIAL PRIMARY KEY,
    order_id    TEXT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    step        TEXT NOT NULL,
    occurred_at TEXT,
    completed   BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS draft_orders (
    session_id   TEXT PRIMARY KEY,
    order_id     TEXT NOT NULL,
    summary_json JSONB NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS complaints (
    ticket_id   TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    session_id  TEXT,
    summary     TEXT NOT NULL,
    urgency     TEXT NOT NULL DEFAULT 'MEDIUM',
    status      TEXT NOT NULL DEFAULT 'QUEUED',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_complaints_user ON complaints(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS refunds (
    refund_id    TEXT PRIMARY KEY,
    order_id     TEXT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    user_id      TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    amount       REAL NOT NULL CHECK (amount > 0),
    reason       TEXT,
    status       TEXT NOT NULL DEFAULT 'Processing',
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_refunds_user ON refunds(user_id);

CREATE TABLE IF NOT EXISTS sessions (
    session_id    TEXT PRIMARY KEY,
    user_id       TEXT REFERENCES users(user_id) ON DELETE SET NULL,
    message_count INTEGER DEFAULT 0,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS session_messages (
    id         SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_session_messages_session ON session_messages(session_id, created_at);
"""


async def init_schema() -> None:
    """Create all tables. Safe to call on every startup."""
    async with engine.begin() as conn:
        for stmt in _SCHEMA_SQL.split(";"):
            stmt = stmt.strip()
            if stmt:
                await conn.execute(text(stmt))
    logger.info("Database schema ready.")


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a scoped async database session."""
    async with async_session() as session:
        yield session


# ---------------------------------------------------------------------------
# Synchronous connection helper for agent tools
#
# Agent tools (cart_api, product_api, etc.) are synchronous functions that
# run inside ThreadPoolExecutor via LangChain. They cannot use async
# SQLAlchemy directly. get_conn() provides a psycopg2 connection whose rows
# behave like dicts (psycopg2.extras.RealDictCursor), so the existing
# row["key"] syntax works unchanged.
# ---------------------------------------------------------------------------



@contextmanager
def get_conn():
    """
    Synchronous psycopg2 context manager.

    Usage:
        with get_conn() as conn:
            rows = conn.execute("SELECT * FROM products WHERE ...").fetchall()
    """
    import psycopg2
    import psycopg2.extras

    from app.database.engine import DATABASE_URL

    # Convert SQLAlchemy async URL back to standard psycopg2 DSN
    dsn = (DATABASE_URL
           .replace("postgresql+asyncpg://", "postgresql://", 1)
           .replace("postgres+asyncpg://",   "postgresql://", 1))

    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    conn.autocommit = False
    try:
        yield _PsycoConnWrapper(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


class _PsycoConnWrapper:
    """
    Thin wrapper around a psycopg2 connection that adapts the execute() API
    to match what the agent tools expect (sqlite3-style interface).

    Differences handled:
      - sqlite3 uses '?' placeholders; psycopg2 uses '%s'. We convert on the fly.
      - sqlite3.Cursor.fetchone() / fetchall() return sqlite3.Row (dict-like);
        psycopg2 with RealDictCursor returns dicts natively.
    """

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql: str, params=()) -> "_PsycoCursorWrapper":
        sql = sql.replace("?", "%s")
        cur = self._conn.cursor()
        cur.execute(sql, params)
        return _PsycoCursorWrapper(cur)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


class _PsycoCursorWrapper:
    """Wraps a psycopg2 cursor with a sqlite3-compatible interface."""

    def __init__(self, cur):
        self._cur = cur

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    @property
    def lastrowid(self):
        return self._cur.fetchone().get("id") if self._cur.description else None



_PRODUCTS = [
    ("laptop", "Dell XPS 15 (2026)", 124990, 14, 4.7, 2341,
     '15.6" OLED, Intel Core Ultra 9, 32GB RAM, 1TB NVMe SSD, NVIDIA RTX 4070 GPU.', "Laptop",
     ["10% off with HDFC cards", "Free laptop bag worth Rs.3,999"],
     ["computer", "pc", "dell", "xps", "notebook", "gaming laptop"]),
    ("samsung", "Samsung Galaxy S26 Ultra", 107999, 22, 4.6, 5632,
     '6.8" Dynamic AMOLED 2X, 200MP camera, Snapdragon 8 Elite, 6000mAh, S Pen.', "Smartphone",
     ["Free Galaxy Watch 7 (worth Rs.22,999)", "3-month YouTube Premium"],
     ["galaxy", "s26", "android", "phone", "smartphone", "mobile", "samsung phone"]),
    ("mouse", "Logitech MX Master 4", 9995, 76, 4.9, 12043,
     "Ergonomic wireless mouse, 4000 DPI, Bluetooth & USB-C, 70-day battery.", "Peripherals",
     ["Flat Rs.500 off on orders above Rs.5,000"],
     ["logitech", "mx master", "wireless mouse", "ergonomic"]),
    ("keyboard", "Keychron K8 Pro Wireless", 11490, 0, 4.6, 4201,
     "Tenkeyless mechanical keyboard, hot-swappable, RGB, Mac & Windows.", "Peripherals",
     [], ["keychron", "mechanical", "wireless keyboard", "mechanical keyboard"]),
    ("headphones", "Sony WH-1000XM6", 29990, 31, 4.9, 9876,
     "Industry-leading ANC, 35hr battery, Multipoint BT, Hi-Res, foldable.", "Audio",
     ["Exchange offer: up to Rs.5,000 off"],
     ["sony", "wh1000xm6", "noise cancelling", "anc", "earphones", "headset", "wireless headphones"]),
    ("monitor", "LG UltraSharp 27UN880", 54990, 9, 4.5, 1876,
     '27" 4K IPS NanoCell, USB-C 96W PD, Ergo stand, VESA DisplayHDR 400.', "Monitors",
     ["Free HDMI cable included"],
     ["lg", "4k monitor", "27 inch", "usb-c monitor", "ultrawide"]),
    ("macbook", "Apple MacBook Pro 16 (M4 Pro)", 249900, 7, 4.9, 3421,
     '16" Liquid Retina XDR, M4 Pro chip, 24GB unified memory, 512GB SSD.', "Laptop",
     ["Student discount: Rs.10,000 off", "Free AirPods with purchase"],
     ["apple", "mac", "macbook", "apple laptop", "m4", "macbook 16"]),
    ("ipad", "Apple iPad Pro 13-inch (M4)", 129900, 24, 4.9, 4512,
     '13" Ultra Retina XDR, M4 chip, 256GB, Wi-Fi, Space Black.', "Tablet",
     ["Student discount available"],
     ["apple", "ipad", "tablet", "m4", "ipad pro"]),
    ("ps5", "Sony PlayStation 5 Pro", 54990, 12, 4.8, 12543,
     "Next-gen gaming console, 8K support, 2TB SSD, DualSense Edge included.", "Gaming",
     ["Free Spider-Man 2 game bundle"],
     ["sony", "playstation", "ps5", "gaming console", "ps5 pro"]),
    ("watch", "Apple Watch Ultra 2", 89900, 18, 4.7, 3211,
     "Titanium case, Precision dual-frequency GPS, Cellular, Alpine Loop.", "Wearables",
     ["Up to Rs.3,000 cashback with ICICI cards"],
     ["apple", "watch", "smartwatch", "ultra 2", "wearable"]),
    ("tv", "Samsung 65-inch Neo QLED 8K", 299990, 5, 4.6, 891,
     '65" 8K Quantum HDR, Neural Quantum Processor 8K, Dolby Atmos.', "Television",
     ["Free soundbar worth Rs.24,990"],
     ["samsung", "tv", "television", "qled", "8k", "smart tv"]),
    ("kindle", "Amazon Kindle Paperwhite (16GB)", 14999, 150, 4.8, 45213,
     '6.8" display, adjustable warm light, waterproof, 16GB storage.', "E-Reader",
     ["Free Kindle Unlimited for 3 months"],
     ["amazon", "kindle", "ereader", "paperwhite", "book"]),
    ("iphone18pro", "Apple iPhone 18 Pro (256GB)", 165000, 50, 4.9, 120,
     '6.5" Super Retina XDR, A20 Pro chip, 50MP camera.', "Smartphone",
     [], ["apple", "iphone", "iphone18", "iphone 18 pro"]),
    ("iphone18promax", "Apple iPhone 18 Pro Max (256GB)", 180000, 40, 4.9, 150,
     '6.9" Super Retina XDR, A20 Pro chip, 50MP camera.', "Smartphone",
     [], ["apple", "iphone", "iphone18", "iphone 18 pro max"]),
    ("earbuds_pro", "AirPods Pro (3rd Gen)", 24900, 100, 4.8, 5000,
     "Active Noise Cancellation, Adaptive Audio.", "Audio",
     [], ["apple", "earbuds", "airpods", "tws"]),
    ("headphones_bose", "Bose QuietComfort Ultra", 35900, 60, 4.7, 2500,
     "World-class noise cancellation, immersive audio.", "Audio",
     [], ["bose", "headphones", "anc", "over-ear"]),
    ("laptop_mac_air", "Apple MacBook Air (M3)", 114900, 80, 4.8, 4500,
     '13.6" Liquid Retina, M3 chip, 8GB RAM, 256GB SSD.', "Laptop",
     [], ["apple", "mac", "macbook air", "laptop"]),
    ("tablet_samsung", "Samsung Galaxy Tab S9", 72999, 50, 4.7, 2100,
     '11" Dynamic AMOLED 2X, Snapdragon 8 Gen 2, S Pen.', "Tablet",
     [], ["samsung", "tablet", "galaxy tab"]),
    ("camera_sony", "Sony Alpha ILCE-7RM5", 349990, 15, 4.9, 800,
     "61MP full-frame mirrorless camera, AI autofocus.", "Cameras",
     [], ["camera", "sony", "mirrorless", "alpha"]),
    ("drone", "DJI Mini 4 Pro", 89990, 18, 4.9, 1500,
     "Sub-250g drone with 4K/60fps HDR true vertical shooting.", "Cameras",
     [], ["drone", "dji", "camera", "quadcopter"]),
    ("vr_headset", "Meta Quest 3 (128GB)", 49999, 55, 4.7, 3400,
     "Breakthrough mixed reality headset.", "Gaming",
     [], ["meta", "quest", "vr", "virtual reality", "gaming"]),
    ("mic", "Shure SM7B", 35999, 45, 4.9, 6700,
     "Iconic dynamic vocal microphone for broadcast and podcast.", "Audio",
     [], ["shure", "microphone", "mic", "audio"]),
    ("powerbank", "Anker PowerCore 20000mAh", 3999, 150, 4.6, 8000,
     "High capacity portable charger with fast charging.", "Accessories",
     [], ["powerbank", "charger", "anker", "battery"]),
    ("echodot", "Echo Dot (4th Gen) Smart Speaker", 3999, 110, 4.5, 23000,
     "Smart speaker with Alexa. Spherical design with rich sound.", "Smart Home",
     [], ["echo dot", "alexa", "smart speaker", "amazon"]),
    ("ssd_1tb", "Samsung 990 PRO 1TB PCIe 4.0 NVMe", 11999, 120, 4.9, 8900,
     "Blazing fast NVMe SSD for gaming and creation.", "Storage",
     [], ["samsung", "ssd", "nvme", "storage", "1tb"]),
]

_PRICE_HISTORY = {
    "laptop":        [129990, 126990, 124990, 124990],
    "samsung":       [110999, 108999, 107999, 107999],
    "macbook":       [249900, 249900, 249900, 249900],
    "mouse":         [10995, 9995, 9995, 9995],
    "keyboard":      [11990, 11490, 11490, 11490],
    "headphones":    [31990, 30990, 29990, 29990],
    "monitor":       [56990, 55990, 54990, 54990],
    "ipad":          [129900, 129900, 129900, 129900],
    "ps5":           [59990, 59990, 54990, 54990],
    "watch":         [89900, 89900, 89900, 89900],
    "tv":            [319990, 319990, 299990, 299990],
    "kindle":        [14999, 14999, 13999, 14999],
    "iphone18pro":   [165000, 165000, 165000, 165000],
    "iphone18promax":[180000, 180000, 180000, 180000],
    "earbuds_pro":   [24900, 24900, 24900, 24900],
    "headphones_bose":[35900, 35900, 35900, 35900],
    "laptop_mac_air":[114900, 114900, 114900, 114900],
    "camera_sony":   [349990, 349990, 349990, 349990],
    "drone":         [89990, 89990, 89990, 89990],
    "vr_headset":    [49999, 49999, 49999, 49999],
    "ssd_1tb":       [11999, 11999, 11999, 11999],
    "powerbank":     [3999, 3999, 3999, 3999],
}

_COUPONS = [
    ("SAVE10",        "percent", 10.0, 5000.0,  0.0,    "10% off orders above Rs.5,000"),
    ("FLAT500",       "flat",    500.0, 5000.0,  500.0,  "Rs.500 off on orders above Rs.5,000"),
    ("NEWUSER",       "percent", 15.0,  0.0,     2000.0, "15% off for new users, max Rs.2,000"),
    ("ELECTRONICS20", "percent", 20.0,  10000.0, 3000.0, "20% off electronics, max Rs.3,000"),
]


async def seed_data() -> None:
    """Populate demo data. Only inserts when the relevant table is empty."""
    import bcrypt

    async with async_session() as session:
        # Products
        count = (await session.execute(text("SELECT COUNT(*) FROM products"))).scalar()
        if count == 0:
            logger.info("Seeding products...")
            for p in _PRODUCTS:
                key, name, price, stock, rating, reviews, desc, cat, offers, synonyms = p
                await session.execute(text("""
                    INSERT INTO products (product_key, name, price, stock, rating, reviews, description, category)
                    VALUES (:k, :n, :pr, :st, :r, :rv, :d, :c)
                    ON CONFLICT (product_key) DO NOTHING
                """), {"k": key, "n": name, "pr": price, "st": stock, "r": rating,
                       "rv": reviews, "d": desc, "c": cat})
                for offer_text in offers:
                    await session.execute(text("""
                        INSERT INTO product_offers (product_key, offer_text) VALUES (:k, :o)
                    """), {"k": key, "o": offer_text})
                for syn in synonyms:
                    await session.execute(text("""
                        INSERT INTO product_synonyms (product_key, synonym) VALUES (:k, :s)
                    """), {"k": key, "s": syn})

        # Price history
        if (await session.execute(text("SELECT COUNT(*) FROM price_history"))).scalar() == 0:
            logger.info("Seeding price history...")
            for product_key, prices in _PRICE_HISTORY.items():
                for i, price in enumerate(prices):
                    await session.execute(text("""
                        INSERT INTO price_history (product_key, price, recorded_at)
                        VALUES (:k, :p, NOW() - INTERVAL '1 week' * :weeks)
                    """), {"k": product_key, "p": price, "weeks": len(prices) - 1 - i})

        # Coupons
        if (await session.execute(text("SELECT COUNT(*) FROM coupons"))).scalar() == 0:
            logger.info("Seeding coupons...")
            for code, ctype, value, min_order, max_discount, desc in _COUPONS:
                await session.execute(text("""
                    INSERT INTO coupons (code, type, value, min_order, max_discount, description)
                    VALUES (:code, :t, :v, :mo, :md, :d)
                    ON CONFLICT (code) DO NOTHING
                """), {"code": code, "t": ctype, "v": value, "mo": min_order,
                       "md": max_discount, "d": desc})

        # Demo user and orders
        if (await session.execute(text("SELECT COUNT(*) FROM users"))).scalar() == 0:
            logger.info("Seeding demo user and orders...")
            demo_hash = bcrypt.hashpw(b"demo", bcrypt.gensalt()).decode()
            await session.execute(text("""
                INSERT INTO users (user_id, email, password_hash, name, shipping_address)
                VALUES ('user_1', 'demo@gmail.com', :h, 'Demo User', '')
                ON CONFLICT (user_id) DO NOTHING
            """), {"h": demo_hash})
            await session.execute(text("""
                INSERT INTO user_preferences (user_id, pref_key, pref_value, source)
                VALUES ('user_1', 'preferred_budget', 'flexible', 'agent'),
                       ('user_1', 'interests', 'electronics, gadgets', 'agent')
                ON CONFLICT (user_id, pref_key) DO NOTHING
            """))

            demo_orders = [
                ("123", "user_1", "Out for Delivery", 124990, 0, 9999.20, 0, 134989.20, "BlueDart Express", "BD9283746501"),
                ("456", "user_1", "On the way",       165000, 0, 13200.00, 0, 178200.00, "Delhivery",        "DL7654321098"),
                ("999", "user_1", "Delivered",         29990, 0, 2399.20,  0, 32389.20,  "DTDC",             "DTDC00192837465"),
            ]
            order_items_map = {
                "123": [("laptop",     "Dell XPS 15 (2026)",         124990, 1)],
                "456": [("iphone18pro","Apple iPhone 18 Pro (256GB)", 165000, 1)],
                "999": [("headphones", "Sony WH-1000XM6",              29990, 1)],
            }
            order_timelines = {
                "123": [
                    ("Order Placed",      "24 Sep, 10:32 AM", True),
                    ("Payment Confirmed", "24 Sep, 10:33 AM", True),
                    ("Packed & Shipped",  "25 Sep, 08:15 PM", True),
                    ("Out for Delivery",  "28 Sep, 09:20 AM", True),
                    ("Delivered",         "Expected today",   False),
                ],
                "456": [
                    ("Order Placed",      "28 Sep, 03:45 PM", True),
                    ("Payment Confirmed", "28 Sep, 03:46 PM", True),
                    ("Packed & Shipped",  "29 Sep, 10:00 AM", True),
                    ("Out for Delivery",  "Pending",          False),
                    ("Delivered",         "Estimated 2 Oct",  False),
                ],
                "999": [
                    ("Order Placed",      "20 Sep, 11:00 AM", True),
                    ("Payment Confirmed", "20 Sep, 11:01 AM", True),
                    ("Packed & Shipped",  "22 Sep, 02:00 PM", True),
                    ("Out for Delivery",  "23 Sep, 08:00 AM", True),
                    ("Delivered",         "23 Sep, 01:30 PM", True),
                ],
            }
            for oid, uid, status, sub, disc, tax, fee, total, carrier, tracking in demo_orders:
                await session.execute(text("""
                    INSERT INTO orders (order_id, user_id, status, subtotal, discount, tax,
                                        delivery_fee, total, carrier, tracking_num)
                    VALUES (:oid, :uid, :s, :sub, :d, :t, :f, :tot, :c, :tr)
                    ON CONFLICT (order_id) DO NOTHING
                """), {"oid": oid, "uid": uid, "s": status, "sub": sub, "d": disc,
                       "t": tax, "f": fee, "tot": total, "c": carrier, "tr": tracking})
                for pkey, name, price, qty in order_items_map[oid]:
                    await session.execute(text("""
                        INSERT INTO order_items (order_id, product_key, name, price, quantity)
                        VALUES (:oid, :pk, :n, :p, :q)
                    """), {"oid": oid, "pk": pkey, "n": name, "p": price, "q": qty})
                for step, occurred_at, completed in order_timelines[oid]:
                    await session.execute(text("""
                        INSERT INTO order_timeline (order_id, step, occurred_at, completed)
                        VALUES (:oid, :s, :o, :c)
                    """), {"oid": oid, "s": step, "o": occurred_at, "c": completed})

        await session.commit()
    logger.info("Seed complete.")
