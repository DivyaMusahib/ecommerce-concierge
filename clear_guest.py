"""
clear_guest.py — Utility script to wipe all saved preferences for the guest user.

Run manually from the project root when you want to reset the guest
AI memory profile (e.g. after a demo session):

    python clear_guest.py

This targets the long-term memory database (data/users.db) — it does NOT
affect order history, cart state, or any other ShopMate data.
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "users.db")

if not os.path.exists(DB_PATH):
    print(f"users.db not found at {DB_PATH}. Nothing to clear.")
else:
    conn = sqlite3.connect(DB_PATH)
    conn.execute('UPDATE users SET preferences_json = "{}" WHERE user_id = "guest"')
    conn.commit()
    conn.close()
    print("Guest preferences cleared.")
