"""
Central SQLite Database for ShopMate.

Manages all persistent tables:
  - products       (catalog)
  - orders         (tracking)
  - price_history  (for deals/pricing agent)
  - coupons        (discount codes)
  - carts          (per-session)
  - confirmed_orders (checkout results)
  - complaints     (escalation log)
  - refunds        (issued refunds)
  - sessions       (short-term chat history, survives restarts)
  - draft_orders   (pending checkout summaries — replaces _latest_summaries dict)

All tables are created and seeded on import via init_db().
"""
import json
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "shopmate.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent read support
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _apply_migrations(c: sqlite3.Connection):
    """Apply any schema migrations that may not exist in older DBs."""
    # Add shipping_address to users if it doesn't exist yet
    cols = [r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()]
    if "shipping_address" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN shipping_address TEXT DEFAULT ''")

    # Add delivery_fee to confirmed_orders if missing
    cols_co = [r[1] for r in c.execute("PRAGMA table_info(confirmed_orders)").fetchall()]
    if "delivery_fee" not in cols_co:
        c.execute("ALTER TABLE confirmed_orders ADD COLUMN delivery_fee REAL DEFAULT 0")

    c.commit()


_db_initialized = False


def init_db():
    """Create all tables and seed with demo data if empty."""
    global _db_initialized
    if _db_initialized:
        return  # Already initialized in this process (e.g. module import + lifespan)
    _db_initialized = True
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_conn() as c:
        # ── Products ──────────────────────────────────────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS products (
                product_key  TEXT PRIMARY KEY,
                name         TEXT NOT NULL,
                price        INTEGER NOT NULL,
                stock        INTEGER DEFAULT 0,
                rating       REAL DEFAULT 0,
                reviews      INTEGER DEFAULT 0,
                description  TEXT,
                category     TEXT,
                offers_json  TEXT DEFAULT '[]',
                synonyms     TEXT DEFAULT ''
            )
        """)
        # ── Users ─────────────────────────────────────────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id          TEXT PRIMARY KEY,
                email            TEXT UNIQUE,
                password_hash    TEXT,
                name             TEXT,
                created_at       TEXT,
                shipping_address TEXT DEFAULT ''
            )
        """)
        # ── Orders ────────────────────────────────────────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id      TEXT PRIMARY KEY,
                user_id       TEXT,
                product       TEXT,
                status        TEXT,
                eta           TEXT,
                carrier       TEXT,
                tracking_num  TEXT,
                placed_on     TEXT,
                amount        TEXT,
                timeline_json TEXT DEFAULT '[]'
            )
        """)
        # ── Price History ─────────────────────────────────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                product_key  TEXT PRIMARY KEY,
                prices_json  TEXT DEFAULT '[]'
            )
        """)
        # ── Coupons ───────────────────────────────────────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS coupons (
                code        TEXT PRIMARY KEY,
                type        TEXT,
                value       REAL,
                min_order   REAL DEFAULT 0,
                description TEXT,
                active      INTEGER DEFAULT 1
            )
        """)
        # ── Carts ─────────────────────────────────────────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS carts (
                session_id   TEXT PRIMARY KEY,
                items_json   TEXT DEFAULT '[]',
                coupon_code  TEXT,
                updated_at   TEXT
            )
        """)
        # ── Draft Orders (replaces _latest_summaries in-memory dict) ──────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS draft_orders (
                session_id   TEXT PRIMARY KEY,
                summary_json TEXT NOT NULL,
                created_at   TEXT
            )
        """)
        # ── Confirmed Orders ──────────────────────────────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS confirmed_orders (
                order_id        TEXT PRIMARY KEY,
                session_id      TEXT,
                user_id         TEXT,
                items_json      TEXT,
                subtotal        REAL,
                discount        REAL,
                tax             REAL,
                delivery_fee    REAL DEFAULT 0,
                total           REAL,
                coupon_code     TEXT,
                placed_at       TEXT,
                status          TEXT DEFAULT 'Confirmed - Processing'
            )
        """)
        # ── Complaints ────────────────────────────────────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS complaints (
                ticket_id   TEXT PRIMARY KEY,
                user_id     TEXT,
                session_id  TEXT,
                summary     TEXT,
                urgency     TEXT,
                status      TEXT DEFAULT 'QUEUED',
                created_at  TEXT
            )
        """)
        # ── Refunds ───────────────────────────────────────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS refunds (
                refund_id   TEXT PRIMARY KEY,
                order_id    TEXT,
                user_id     TEXT,
                amount      REAL,
                reason      TEXT,
                status      TEXT DEFAULT 'Processing',
                created_at  TEXT
            )
        """)
        # ── Sessions (short-term memory) ─────────────────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id   TEXT PRIMARY KEY,
                history_json TEXT DEFAULT '[]',
                updated_at   TEXT
            )
        """)
        # ── Indexes for performance ───────────────────────────────────────────
        c.execute("CREATE INDEX IF NOT EXISTS idx_confirmed_orders_user ON confirmed_orders(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_confirmed_orders_placed ON confirmed_orders(placed_at DESC)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_complaints_user ON complaints(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_refunds_user ON refunds(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at)")
        c.commit()

        # Apply any column migrations for existing DBs
        _apply_migrations(c)

        _seed(c)


def _seed(c: sqlite3.Connection):
    """Populate tables with demo data if they are empty."""
    # Seed products
    if not c.execute("SELECT 1 FROM products LIMIT 1").fetchone():
        products = [
            ("laptop", "Dell XPS 15 (2026)", 124990, 14, 4.7, 2341,
             "15.6\" OLED, Intel Core Ultra 9, 32GB RAM, 1TB NVMe SSD, NVIDIA RTX 4070 GPU.",
             "Laptop", json.dumps(["10% off with HDFC cards", "Free laptop bag worth Rs.3,999"]),
             "computer,pc,dell,xps,notebook,gaming laptop"),
            ("samsung", "Samsung Galaxy S26 Ultra", 107999, 22, 4.6, 5632,
             "6.8\" Dynamic AMOLED 2X, 200MP camera, Snapdragon 8 Elite, 6000mAh, S Pen.",
             "Smartphone", json.dumps(["Free Galaxy Watch 7 (worth Rs.22,999)", "3-month YouTube Premium"]),
             "galaxy,s26,android,phone,smartphone,mobile,samsung phone"),
            ("mouse", "Logitech MX Master 4", 9995, 76, 4.9, 12043,
             "Ergonomic wireless mouse, 4000 DPI, Bluetooth & USB-C, 70-day battery.",
             "Peripherals", json.dumps(["Flat Rs.500 off on orders above Rs.5,000"]),
             "logitech,mx master,wireless mouse,ergonomic"),
            ("keyboard", "Keychron K8 Pro Wireless", 11490, 0, 4.6, 4201,
             "Tenkeyless mechanical keyboard, hot-swappable, RGB, Mac & Windows.",
             "Peripherals", json.dumps([]),
             "keychron,mechanical,wireless keyboard,mechanical keyboard"),
            ("headphones", "Sony WH-1000XM6", 29990, 31, 4.9, 9876,
             "Industry-leading ANC, 35hr battery, Multipoint BT, Hi-Res, foldable.",
             "Audio", json.dumps(["Exchange offer: up to Rs.5,000 off"]),
             "sony,wh1000xm6,noise cancelling,anc,earphones,headset,wireless headphones"),
            ("monitor", "LG UltraSharp 27UN880", 54990, 9, 4.5, 1876,
             "27\" 4K IPS NanoCell, USB-C 96W PD, Ergo stand, VESA DisplayHDR 400.",
             "Monitors", json.dumps(["Free HDMI cable included"]),
             "lg,4k monitor,27 inch,usb-c monitor,ultrawide"),
            ("macbook", "Apple MacBook Pro 16 (M4 Pro)", 249900, 7, 4.9, 3421,
             "16\" Liquid Retina XDR, M4 Pro chip, 24GB unified memory, 512GB SSD.",
             "Laptop", json.dumps(["Student discount: Rs.10,000 off", "Free AirPods with purchase"]),
             "apple,mac,macbook,apple laptop,m4,macbook 16"),
            ("ipad", "Apple iPad Pro 13-inch (M4)", 129900, 24, 4.9, 4512,
             "13\" Ultra Retina XDR, M4 chip, 256GB, Wi-Fi, Space Black.",
             "Tablet", json.dumps(["Student discount available"]), "apple,ipad,tablet,m4,ipad pro"),
            ("ps5", "Sony PlayStation 5 Pro", 54990, 12, 4.8, 12543,
             "Next-gen gaming console, 8K support, 2TB SSD, DualSense Edge included.",
             "Gaming", json.dumps(["Free Spider-Man 2 game bundle"]), "sony,playstation,ps5,gaming console,ps5 pro"),
            ("watch", "Apple Watch Ultra 2", 89900, 18, 4.7, 3211,
             "Titanium case, Precision dual-frequency GPS, Cellular, Alpine Loop.",
             "Wearables", json.dumps(["Up to Rs.3,000 cashback with ICICI cards"]), "apple,watch,smartwatch,ultra 2,wearable"),
            ("tv", "Samsung 65-inch Neo QLED 8K", 299990, 5, 4.6, 891,
             "65\" 8K Quantum HDR, Neural Quantum Processor 8K, Dolby Atmos.",
             "Television", json.dumps(["Free soundbar worth Rs.24,990"]), "samsung,tv,television,qled,8k,smart tv"),
            ("kindle", "Amazon Kindle Paperwhite (16GB)", 14999, 150, 4.8, 45213,
             "6.8\" display, adjustable warm light, waterproof, 16GB storage.",
             "E-Reader", json.dumps(["Free Kindle Unlimited for 3 months"]), "amazon,kindle,ereader,paperwhite,book"),
            ("pendrive64", "SanDisk Ultra 64GB USB 3.0 Flash Drive", 549, 150, 4.5, 8500,
             "High-speed USB 3.0 flash drive for fast data transfer. 64GB capacity.",
             "Accessories", json.dumps([]), "usb, flash drive, pendrive, storage, 64gb, sandisk"),
            ("powerbank", "Mi 10000mAh Power Bank 3i", 1299, 85, 4.4, 12400,
             "10000mAh portable charger with 18W fast charging and dual USB output.",
             "Accessories", json.dumps([]), "power bank, portable charger, battery, mi power bank, 10000mah"),
            ("earbuds", "boAt Airdopes 141 Bluetooth TWS", 1499, 200, 4.1, 45000,
             "True wireless earbuds with 42H playtime, beast mode, and water resistance.",
             "Audio", json.dumps([]), "earbuds, tws, bluetooth earphones, boat, wireless"),
            ("smartbulb", "Wipro 9W LED Smart Color Bulb", 699, 120, 4.2, 5400,
             "Wi-Fi enabled smart LED bulb. 16 million colors, works with Alexa/Google.",
             "Smart Home", json.dumps([]), "smart bulb, rgb bulb, wipro, wifi bulb, led"),
            ("router", "TP-Link Archer C50 AC1200 Wi-Fi Router", 1799, 45, 4.3, 8900,
             "Dual-band Wi-Fi router with 4 antennas for strong coverage and fast speeds.",
             "Networking", json.dumps([]), "router, wifi, tp-link, internet, ac1200"),
            ("webcam", "Logitech C270 HD Webcam", 2495, 30, 4.5, 11200,
             "HD 720p video calling and recording. Built-in noise reducing microphone.",
             "Peripherals", json.dumps([]), "webcam, camera, logitech, 720p, video call"),
            ("mousepad", "Redgear Pro Series Gaming Mousepad", 599, 300, 4.6, 21000,
             "Speed-type gaming mouse pad with anti-slip rubber base.",
             "Peripherals", json.dumps([]), "mousepad, gaming pad, redgear, desk mat"),
            ("smartplug", "Amazon Smart Plug", 1999, 50, 4.5, 9500,
             "Add voice control to any outlet. Works seamlessly with Alexa.",
             "Smart Home", json.dumps([]), "smart plug, alexa plug, wifi plug, switch, amazon"),
            ("speaker", "JBL Go 2 Wireless Portable Bluetooth Speaker", 2999, 60, 4.4, 32000,
             "Waterproof portable Bluetooth speaker with up to 5 hours of playtime.",
             "Audio", json.dumps([]), "bluetooth speaker, jbl, portable speaker, go 2"),
            ("keyboard_cheap", "HP 150 Wired Keyboard", 799, 90, 4.3, 4100,
             "Ergonomic wired keyboard with chiclet-style keys and numeric keypad.",
             "Peripherals", json.dumps([]), "keyboard, wired keyboard, hp, typing"),
            ("fitnessband", "OnePlus Smart Band", 2799, 75, 4.2, 8900,
             "Fitness tracker with SpO2, heart rate monitoring, and 14-day battery.",
             "Wearables", json.dumps([]), "fitness band, smart band, oneplus band, tracker"),
            ("harddrive", "WD Elements 1TB Portable External HDD", 4299, 40, 4.6, 45000,
             "1TB portable external hard drive, USB 3.0 compatible.",
             "Storage", json.dumps([]), "hdd, external hard drive, 1tb, wd, storage, western digital"),
            ("cablestypec", "AmazonBasics Braided USB Type-C Cable", 599, 400, 4.3, 12500,
             "Nylon braided USB-A to Type-C fast charging cable, 3 feet.",
             "Accessories", json.dumps([]), "type-c cable, charging cable, usb c, amazonbasics, wire"),
            ("echodot", "Echo Dot (4th Gen) Smart Speaker", 3999, 110, 4.5, 23000,
             "Smart speaker with Alexa. Spherical design with rich sound.",
             "Smart Home", json.dumps([]), "echo dot, alexa, smart speaker, amazon"),
            ("ssd256", "Crucial BX500 240GB 3D NAND SATA SSD", 1899, 65, 4.5, 14500,
             "Internal Solid State Drive for faster boot-ups and application loading.",
             "Storage", json.dumps([]), "ssd, solid state drive, 240gb, crucial, internal storage"),
            ("iphone18pro", "Apple iPhone 18 Pro (256GB)", 165000, 50, 4.9, 120, 
             "6.5\" Super Retina XDR, A20 Pro chip, 50MP camera.", 
             "Smartphone", json.dumps([]), "apple,iphone,iphone18,iphone 18 pro"),
            ("iphone18promax", "Apple iPhone 18 Pro Max (256GB)", 180000, 40, 4.9, 150, 
             "6.9\" Super Retina XDR, A20 Pro chip, 50MP camera.", 
             "Smartphone", json.dumps([]), "apple,iphone,iphone18,iphone 18 pro max"),
            ("iphoneduo", "Apple iPhone Duo (256GB)", 299000, 10, 5.0, 50, 
             "Foldable Super Retina XDR, A20 Pro, Dual Screens.", 
             "Smartphone", json.dumps([]), "apple,iphone,iphone duo,foldable"),
            ("earbuds_pro", "AirPods Pro (3rd Gen)", 24900, 100, 4.8, 5000, 
             "Active Noise Cancellation, Adaptive Audio.", 
             "Audio", json.dumps([]), "apple,earbuds,airpods,tws"),
            ("earphones_wired", "Apple EarPods with USB-C", 1900, 200, 4.5, 3000, 
             "Classic wired earphones with USB-C connector.", 
             "Audio", json.dumps([]), "apple,earphones,wired,earpods"),
            ("headphones_bose", "Bose QuietComfort Ultra", 35900, 60, 4.7, 2500, 
             "World-class noise cancellation, immersive audio.", 
             "Audio", json.dumps([]), "bose,headphones,anc,over-ear"),
            ("powerbank_anker", "Anker PowerCore 20000mAh", 3999, 150, 4.6, 8000, 
             "High capacity portable charger with fast charging.", 
             "Accessories", json.dumps([]), "powerbank,charger,anker,battery"),
            ("charger_apple", "Apple 20W USB-C Power Adapter", 1900, 300, 4.8, 15000, 
             "Fast charging for iPhone and iPad.", 
             "Accessories", json.dumps([]), "charger,adapter,apple,usb-c"),
            ("selfiestick", "DJI OM 6 Smartphone Gimbal", 12999, 45, 4.8, 1200, 
             "3-axis stabilization, built-in extension rod.", 
             "Accessories", json.dumps([]), "selfie stick,gimbal,dji,stabilizer"),
            ("camera_sony", "Sony Alpha ILCE-7RM5", 349990, 15, 4.9, 800, 
             "61MP full-frame mirrorless camera, AI autofocus.", 
             "Cameras", json.dumps([]), "camera,sony,mirrorless,alpha"),
            ("camera_canon", "Canon EOS R5", 339995, 12, 4.8, 950, 
             "45MP full-frame mirrorless, 8K video recording.", 
             "Cameras", json.dumps([]), "camera,canon,eos,mirrorless"),
            ("laptop_mac_air", "Apple MacBook Air (M3)", 114900, 80, 4.8, 4500, 
             "13.6\" Liquid Retina, M3 chip, 8GB RAM, 256GB SSD.", 
             "Laptop", json.dumps([]), "apple,mac,macbook air,laptop"),
            ("tablet_samsung", "Samsung Galaxy Tab S9", 72999, 50, 4.7, 2100, 
             "11\" Dynamic AMOLED 2X, Snapdragon 8 Gen 2, S Pen.", 
             "Tablet", json.dumps([]), "samsung,tablet,galaxy tab"),
            ("mouse_razer", "Razer DeathAdder V3 Pro", 12999, 40, 4.6, 3200, 
             "Ultra-lightweight wireless ergonomic esports mouse.", 
             "Peripherals", json.dumps([]), "razer,mouse,gaming mouse,wireless"),
            ("keyboard_logi", "Logitech MX Keys S", 10995, 65, 4.7, 5400, 
             "Advanced wireless illuminated keyboard.", 
             "Peripherals", json.dumps([]), "logitech,keyboard,wireless,mx keys"),
            ("monitor_dell", "Dell UltraSharp 32 4K USB-C Hub", 75000, 20, 4.8, 1100, 
             "31.5\" 4K IPS Black technology, 90W power delivery.", 
             "Monitors", json.dumps([]), "dell,monitor,4k,display"),
            ("watch_garmin", "Garmin Fenix 7 Pro", 84990, 25, 4.8, 1800, 
             "Multisport GPS watch with solar charging.", 
             "Wearables", json.dumps([]), "garmin,watch,smartwatch,fitness"),
            ("smart_display", "Google Nest Hub (2nd Gen)", 7999, 90, 4.5, 4200, 
             "Smart display with Google Assistant.", 
             "Smart Home", json.dumps([]), "google,nest,display,smart home"),
            ("ssd_1tb", "Samsung 990 PRO 1TB PCIe 4.0 NVMe", 11999, 120, 4.9, 8900, 
             "Blazing fast NVMe SSD for gaming and creation.", 
             "Storage", json.dumps([]), "samsung,ssd,nvme,storage,1tb"),
            ("backpack", "Peak Design Everyday Backpack 20L", 25999, 35, 4.8, 2200, 
             "Versatile, rugged everyday and photo carry.", 
             "Accessories", json.dumps([]), "backpack,bag,peak design"),
            ("drone", "DJI Mini 4 Pro", 89990, 18, 4.9, 1500, 
             "Sub-250g drone with 4K/60fps HDR true vertical shooting.", 
             "Cameras", json.dumps([]), "drone,dji,camera,quadcopter"),
            ("vr_headset", "Meta Quest 3 (128GB)", 49999, 55, 4.7, 3400, 
             "Breakthrough mixed reality headset.", 
             "Gaming", json.dumps([]), "meta,quest,vr,virtual reality,gaming"),
            ("mic", "Shure SM7B", 35999, 45, 4.9, 6700, 
             "Iconic dynamic vocal microphone for broadcast and podcast.", 
             "Audio", json.dumps([]), "shure,microphone,mic,audio"),
            ("webcam_4k", "Logitech MX Brio 4K", 19999, 40, 4.6, 950, 
             "Ultra HD 4K webcam with AI enhancement.", 
             "Peripherals", json.dumps([]), "logitech,webcam,camera,4k"),
            ("router_mesh", "Eero Pro 6 Mesh Wi-Fi System (3-pack)", 59999, 20, 4.7, 1200, 
             "Gigabit speeds, coverage up to 6,000 sq ft.", 
             "Networking", json.dumps([]), "amazon,eero,router,mesh,wifi"),
            ("charger_wireless", "Belkin BoostCharge Pro 3-in-1", 14900, 60, 4.6, 2100, 
             "MagSafe wireless charging stand for iPhone, Watch, AirPods.", 
             "Accessories", json.dumps([]), "belkin,charger,wireless,magsafe"),
            ("cable_micro_usb", "AmazonBasics Micro USB Cable", 99, 500, 4.2, 8500, "Durable micro USB charging and data cable.", "Accessories", json.dumps([]), "cable,micro usb,charging"),
            ("screen_guard_iphone", "Spigen Tempered Glass Screen Protector", 149, 300, 4.5, 12000, "High transparency scratch resistant screen guard.", "Accessories", json.dumps([]), "screen guard,tempered glass,iphone,protector"),
            ("phone_case_clear", "Pooch Transparent TPU Case", 199, 400, 4.3, 5600, "Clear slim flexible phone case.", "Accessories", json.dumps([]), "case,cover,transparent,tpu"),
            ("mousepad_small", "Generic Black Mousepad (Small)", 150, 600, 4.0, 3000, "Basic small size mouse pad with rubber base.", "Peripherals", json.dumps([]), "mousepad,small,black"),
            ("earphones_wired_cheap", "Boat Bassheads 100 Wired", 299, 800, 4.2, 65000, "In-ear wired earphones with mic.", "Audio", json.dumps([]), "boat,earphones,wired,bassheads"),
            ("usb_otg_adapter", "Amkette USB OTG Adapter", 99, 250, 4.4, 4300, "Type-C to USB-A OTG adapter.", "Accessories", json.dumps([]), "otg,usb c,adapter,converter"),
            ("cable_tie_velcro", "Velcro Reusable Cable Ties (Pack of 10)", 120, 200, 4.6, 2100, "Keep your wires organized and tidy.", "Accessories", json.dumps([]), "cable tie,velcro,organizer"),
            ("cleaning_cloth", "Microfiber Cleaning Cloths (5 Pack)", 150, 350, 4.7, 5000, "Lint-free cloths for screens and lenses.", "Accessories", json.dumps([]), "cleaning,cloth,microfiber,wipe"),
            ("mobile_stand", "Portronics Modesk Mobile Stand", 199, 150, 4.5, 9800, "Adjustable metal desktop stand for phones.", "Accessories", json.dumps([]), "mobile stand,holder,desktop,portronics"),
            ("sim_ejector", "SIM Card Ejector Pin Tool (5 Pack)", 49, 1000, 4.1, 1500, "Universal SIM tray ejector tools.", "Accessories", json.dumps([]), "sim,pin,ejector,tool"),
            ("aux_cable", "Boat Aux Cable 1.5m", 149, 450, 4.3, 7600, "3.5mm male to male audio cable.", "Audio", json.dumps([]), "aux,cable,3.5mm,audio"),
            ("laptop_sleeve", "Targus 15.6 inch Laptop Sleeve", 399, 120, 4.4, 3200, "Protective neoprene sleeve for laptops.", "Accessories", json.dumps([]), "laptop,sleeve,cover,bag,targus"),
            ("webcam_cover", "Webcam Privacy Cover Slider (3 Pack)", 99, 300, 4.5, 4500, "Ultra thin camera cover for laptops and phones.", "Accessories", json.dumps([]), "webcam,cover,privacy,slider"),
            ("usb_hub", "Portronics 4-Port USB Hub", 299, 180, 4.2, 5400, "Expand your USB ports with this 4-in-1 hub.", "Accessories", json.dumps([]), "usb,hub,portronics,4 port"),
        ]
        c.executemany("""
            INSERT OR IGNORE INTO products
            (product_key, name, price, stock, rating, reviews, description, category, offers_json, synonyms)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, products)

    # ── Seed orders (exclusively for demo user_1) ─────────────────────────────
    if not c.execute("SELECT 1 FROM orders LIMIT 1").fetchone():
        orders = [
            ("123", "user_1", "Dell XPS 15 (2026)", "Out for Delivery", "Today by 8:00 PM", "BlueDart Express",
             "BD9283746501", "24 Sep 2026", "Rs.1,24,990", json.dumps([
                 {"step": "Order Placed", "time": "24 Sep, 10:32 AM", "done": True},
                 {"step": "Payment Confirmed", "time": "24 Sep, 10:33 AM", "done": True},
                 {"step": "Packed & Shipped", "time": "25 Sep, 08:15 PM", "done": True},
                 {"step": "Out for Delivery", "time": "28 Sep, 09:20 AM", "done": True},
                 {"step": "Delivered", "time": "Expected today", "done": False},
             ])),
            ("456", "user_1", "Apple iPhone 18 Pro (256GB, Black Titanium)", "On the way", "3-4 business days",
             "Delhivery", "DL7654321098", "28 Sep 2026", "Rs.1,65,000", json.dumps([
                 {"step": "Order Placed", "time": "28 Sep, 03:45 PM", "done": True},
                 {"step": "Payment Confirmed", "time": "28 Sep, 03:46 PM", "done": True},
                 {"step": "Packed & Shipped", "time": "29 Sep, 10:00 AM", "done": True},
                 {"step": "Out for Delivery", "time": "Pending", "done": False},
                 {"step": "Delivered", "time": "Estimated 2 Oct", "done": False},
             ])),
            ("999", "user_1", "Sony WH-1000XM6 Headphones", "Delivered", "Delivered on 23 Sep", "DTDC",
             "DTDC00192837465", "20 Sep 2026", "Rs.29,990", json.dumps([
                 {"step": "Order Placed", "time": "20 Sep, 11:00 AM", "done": True},
                 {"step": "Payment Confirmed", "time": "20 Sep, 11:01 AM", "done": True},
                 {"step": "Packed & Shipped", "time": "22 Sep, 02:00 PM", "done": True},
                 {"step": "Out for Delivery", "time": "23 Sep, 08:00 AM", "done": True},
                 {"step": "Delivered", "time": "23 Sep, 01:30 PM", "done": True},
             ])),
        ]
        c.executemany("""
            INSERT OR IGNORE INTO orders
            (order_id, user_id, product, status, eta, carrier, tracking_num, placed_on, amount, timeline_json)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, orders)

    # ── Seed confirmed orders (exclusively for demo user_1's frontend UI) ──
    if not c.execute("SELECT 1 FROM confirmed_orders LIMIT 1").fetchone():
        confirmed_orders = [
            (
                "ORD-123", "demo_session", "user_1", 
                json.dumps([{"name": "Dell XPS 15 (2026)", "price": 124990, "qty": 1}]),
                124990, 0, 9999.20, 0, 134989.20, "", "2026-09-24T10:32:00", "Out for Delivery"
            ),
            (
                "ORD-456", "demo_session", "user_1", 
                json.dumps([{"name": "Apple iPhone 18 Pro", "price": 165000, "qty": 1}]),
                165000, 0, 13200.00, 0, 178200.00, "", "2026-09-28T15:45:00", "On the way"
            ),
            (
                "ORD-999", "demo_session", "user_1", 
                json.dumps([{"name": "Sony WH-1000XM6", "price": 29990, "qty": 1}]),
                29990, 0, 2399.20, 0, 32389.20, "", "2026-09-20T11:00:00", "Delivered"
            ),
        ]
        c.executemany("""
            INSERT OR IGNORE INTO confirmed_orders
            (order_id, session_id, user_id, items_json, subtotal, discount, tax, delivery_fee, total, coupon_code, placed_at, status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, confirmed_orders)

    # Seed price history
    if not c.execute("SELECT 1 FROM price_history LIMIT 1").fetchone():
        ph = [
            ("laptop", json.dumps([129990, 126990, 124990, 124990])),
            ("samsung", json.dumps([110999, 108999, 107999, 107999])),
            ("macbook", json.dumps([249900, 249900, 249900, 249900])),
            ("mouse", json.dumps([10995, 9995, 9995, 9995])),
            ("keyboard", json.dumps([11990, 11490, 11490, 11490])),
            ("headphones", json.dumps([31990, 30990, 29990, 29990])),
            ("monitor", json.dumps([56990, 55990, 54990, 54990])),
            ("ipad", json.dumps([129900, 129900, 129900, 129900])),
            ("ps5", json.dumps([59990, 59990, 54990, 54990])),
            ("watch", json.dumps([89900, 89900, 89900, 89900])),
            ("tv", json.dumps([319990, 319990, 299990, 299990])),
            ("kindle", json.dumps([14999, 14999, 13999, 14999])),
            ("pendrive64", json.dumps([649, 599, 549, 549])),
            ("powerbank", json.dumps([1499, 1399, 1299, 1299])),
            ("earbuds", json.dumps([1999, 1599, 1499, 1499])),
            ("smartbulb", json.dumps([899, 799, 699, 699])),
            ("router", json.dumps([1999, 1899, 1799, 1799])),
            ("webcam", json.dumps([2595, 2595, 2495, 2495])),
            ("mousepad", json.dumps([799, 699, 599, 599])),
            ("smartplug", json.dumps([1999, 1999, 1999, 1999])),
            ("speaker", json.dumps([3499, 3199, 2999, 2999])),
            ("keyboard_cheap", json.dumps([999, 899, 799, 799])),
            ("fitnessband", json.dumps([2999, 2899, 2799, 2799])),
            ("harddrive", json.dumps([4599, 4399, 4299, 4299])),
            ("cablestypec", json.dumps([699, 649, 599, 599])),
            ("echodot", json.dumps([4499, 4299, 3999, 3999])),
            ("ssd256", json.dumps([2199, 1999, 1899, 1899])),
            ("iphone18pro", json.dumps([165000, 165000, 165000, 165000])),
            ("iphone18promax", json.dumps([180000, 180000, 180000, 180000])),
            ("iphoneduo", json.dumps([299000, 299000, 299000, 299000])),
            ("earbuds_pro", json.dumps([24900, 24900, 24900, 24900])),
            ("earphones_wired", json.dumps([1900, 1900, 1900, 1900])),
            ("headphones_bose", json.dumps([35900, 35900, 35900, 35900])),
            ("powerbank_anker", json.dumps([3999, 3999, 3999, 3999])),
            ("charger_apple", json.dumps([1900, 1900, 1900, 1900])),
            ("selfiestick", json.dumps([12999, 12999, 12999, 12999])),
            ("camera_sony", json.dumps([349990, 349990, 349990, 349990])),
            ("camera_canon", json.dumps([339995, 339995, 339995, 339995])),
            ("laptop_mac_air", json.dumps([114900, 114900, 114900, 114900])),
            ("tablet_samsung", json.dumps([72999, 72999, 72999, 72999])),
            ("mouse_razer", json.dumps([12999, 12999, 12999, 12999])),
            ("keyboard_logi", json.dumps([10995, 10995, 10995, 10995])),
            ("monitor_dell", json.dumps([75000, 75000, 75000, 75000])),
            ("watch_garmin", json.dumps([84990, 84990, 84990, 84990])),
            ("smart_display", json.dumps([7999, 7999, 7999, 7999])),
            ("ssd_1tb", json.dumps([11999, 11999, 11999, 11999])),
            ("backpack", json.dumps([25999, 25999, 25999, 25999])),
            ("drone", json.dumps([89990, 89990, 89990, 89990])),
            ("vr_headset", json.dumps([49999, 49999, 49999, 49999])),
            ("mic", json.dumps([35999, 35999, 35999, 35999])),
            ("webcam_4k", json.dumps([19999, 19999, 19999, 19999])),
            ("router_mesh", json.dumps([59999, 59999, 59999, 59999])),
            ("charger_wireless", json.dumps([14900, 14900, 14900, 14900])),
            ("cable_micro_usb", json.dumps([99, 99, 99, 99])),
            ("screen_guard_iphone", json.dumps([149, 149, 149, 149])),
            ("phone_case_clear", json.dumps([199, 199, 199, 199])),
            ("mousepad_small", json.dumps([150, 150, 150, 150])),
            ("earphones_wired_cheap", json.dumps([299, 299, 299, 299])),
            ("usb_otg_adapter", json.dumps([99, 99, 99, 99])),
            ("cable_tie_velcro", json.dumps([120, 120, 120, 120])),
            ("cleaning_cloth", json.dumps([150, 150, 150, 150])),
            ("mobile_stand", json.dumps([199, 199, 199, 199])),
            ("sim_ejector", json.dumps([49, 49, 49, 49])),
            ("aux_cable", json.dumps([149, 149, 149, 149])),
            ("laptop_sleeve", json.dumps([399, 399, 399, 399])),
            ("webcam_cover", json.dumps([99, 99, 99, 99])),
            ("usb_hub", json.dumps([299, 299, 299, 299])),
        ]
        c.executemany("INSERT OR IGNORE INTO price_history (product_key, prices_json) VALUES (?,?)", ph)

    # Seed coupons
    if not c.execute("SELECT 1 FROM coupons LIMIT 1").fetchone():
        coupons = [
            ("SAVE10", "percent", 10, 5000, "10% off orders above Rs.5,000"),
            ("FLAT500", "flat", 500, 5000, "Rs.500 off on orders above Rs.5,000"),
            ("NEWUSER", "percent", 15, 0, "15% off for new users, max discount Rs.2,000"),
            ("ELECTRONICS20", "percent", 20, 10000, "20% off electronics, max discount Rs.3,000"),
        ]
        c.executemany("INSERT OR IGNORE INTO coupons (code, type, value, min_order, description) VALUES (?,?,?,?,?)", coupons)

    # ── Seed the demo user only if the users table is empty ───────────────────
    # CRITICAL: Do NOT wipe all users on every startup — that would destroy
    # all registered user accounts on each server restart!
    # We only seed the demo user the first time (empty table), or
    # upsert just the demo row if for some reason it was removed.
    import bcrypt

    existing_users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if existing_users == 0:
        # Fresh DB — seed only the demo account
        demo_hash = bcrypt.hashpw("demo".encode(), bcrypt.gensalt()).decode()
        c.execute("""
            INSERT INTO users (user_id, email, password_hash, name, created_at, shipping_address)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("user_1", "demo@gmail.com", demo_hash, "Demo User", datetime.utcnow().isoformat(), ""))
    else:
        # DB already has users — only ensure demo account exists, don't touch others
        demo_exists = c.execute(
            "SELECT 1 FROM users WHERE user_id = 'user_1'"
        ).fetchone()
        if not demo_exists:
            demo_hash = bcrypt.hashpw("demo".encode(), bcrypt.gensalt()).decode()
            c.execute("""
                INSERT OR IGNORE INTO users (user_id, email, password_hash, name, created_at, shipping_address)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("user_1", "demo@gmail.com", demo_hash, "Demo User", datetime.utcnow().isoformat(), ""))

    c.commit()


# Run on import
init_db()
