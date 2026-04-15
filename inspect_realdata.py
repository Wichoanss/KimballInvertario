import sqlite3, json

conn = sqlite3.connect(r'c:\Proyectos\KimballInvertario\realdata\inventory.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print('TABLES:', [r[0] for r in cur.fetchall()])

cur.execute("SELECT * FROM reels LIMIT 8")
rows = cur.fetchall()
print('\nREELS SAMPLE:')
for r in rows:
    print(dict(r))

cur.execute("SELECT rack, COUNT(*) as cnt FROM reels GROUP BY rack")
print('\nREELS BY RACK:')
for r in cur.fetchall():
    print(dict(r))

# Check juki_reels if exists
try:
    cur.execute("SELECT * FROM juki_reels LIMIT 5")
    print('\nJUKI REELS SAMPLE:')
    for r in cur.fetchall():
        print(dict(r))
    cur.execute("SELECT container_id, COUNT(*) cnt FROM juki_reels GROUP BY container_id")
    print('\nJUKI BY CONTAINER:')
    for r in cur.fetchall():
        print(dict(r))
except Exception as e:
    print(f'No juki_reels: {e}')

conn.close()
