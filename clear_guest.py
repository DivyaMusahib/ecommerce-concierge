import sqlite3

conn = sqlite3.connect('data/users.db')
conn.execute('UPDATE users SET preferences_json = "{}" WHERE user_id = "guest"')
conn.commit()
conn.close()
print("Guest preferences cleared.")
