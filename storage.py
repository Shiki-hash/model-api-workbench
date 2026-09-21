"""SQLite task/version storage with idempotent legacy import."""
import json
import sqlite3
from pathlib import Path


def connect(root):
    root=Path(root);root.mkdir(exist_ok=True,parents=True)
    db=sqlite3.connect(root/'tasks.sqlite3',timeout=10)
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, topic TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS versions(id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id),
      created_at TEXT NOT NULL, payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS facts(version_id TEXT NOT NULL REFERENCES versions(id), position INTEGER NOT NULL,
      payload TEXT NOT NULL, PRIMARY KEY(version_id,position));
    CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    ''')
    if not db.execute("SELECT 1 FROM metadata WHERE key='legacy_import'").fetchone():
        records=[json.loads(p.read_text(encoding='utf-8')) for p in root.glob('*.json')]
        lookup={r['id']:r for r in records}
        for r in records:
            ancestor=r;seen=set()
            while ancestor.get('parent') in lookup and ancestor['id'] not in seen:
                seen.add(ancestor['id']);ancestor=lookup[ancestor['parent']]
            r['task_id']=ancestor['id']
            _insert(db,r)
        db.execute("INSERT INTO metadata VALUES('legacy_import','1')")
    db.commit()
    return db


def _insert(db,r):
    db.execute('INSERT OR IGNORE INTO tasks VALUES(?,?,?)',(r['task_id'],r['topic'],r['created_at']))
    db.execute('INSERT INTO versions VALUES(?,?,?,?)',(r['id'],r['task_id'],r['created_at'],json.dumps(r,ensure_ascii=False)))
    db.executemany('INSERT INTO facts VALUES(?,?,?)',[(r['id'],i,json.dumps(f,ensure_ascii=False)) for i,f in enumerate(r['facts'])])


def save(root,r):
    db=connect(root)
    try:
        with db:
            row=db.execute('SELECT payload FROM versions WHERE id=?',(r['id'],)).fetchone()
            if row:
                previous=json.loads(row[0])
                if any(previous.get(k)!=r.get(k) for k in ['facts','report','topic','parent','round','task_id','assumptions','costs','brief','decision']):
                    raise ValueError('已有版本内容不可覆盖，请新建修订。')
                if previous['status']!='awaiting_human' or r['status']!='approved':
                    raise ValueError('当前版本状态已变化，请刷新后重试。')
                db.execute('UPDATE versions SET payload=? WHERE id=?',(json.dumps(r,ensure_ascii=False),r['id']))
            else:_insert(db,r)
    finally:db.close()


def get(root,id):
    db=connect(root)
    try:row=db.execute('SELECT payload FROM versions WHERE id=?',(id,)).fetchone()
    finally:db.close()
    if not row:raise ValueError('记录不存在。')
    return json.loads(row[0])


def history(root):
    db=connect(root)
    try:return [json.loads(row[0]) for row in db.execute('SELECT payload FROM versions ORDER BY created_at DESC LIMIT 100')]
    finally:db.close()
