import sqlite3

conn = sqlite3.connect('lostandfound.db')
conn.execute(
    'INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)',
    ('admin', 'admin', 'admin')
)
conn.commit()
conn.close()
print('Admin account created: username=admin, password=admin')