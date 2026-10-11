#!/usr/bin/env python3
"""Server lokal Kantin Tycoon.

Menyajikan game di http://127.0.0.1:8765 dan menyimpan akun + savegame ke file SQLite
(kantin-tycoon.sqlite, di folder yang sama). Hanya memakai pustaka standar Python.

Jalankan:  python server.py          (atau klik dua kali jalankan.bat)
Opsi:      --port 9000   --no-browser
"""
import argparse
import contextlib
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import sqlite3
import sys
import threading
import time
import urllib.request
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

BASE = os.path.dirname(os.path.abspath(__file__))
GAME_FILE = os.path.join(BASE, 'kantin-tycoon.html')
DB_FILE = os.path.join(BASE, 'kantin-tycoon.sqlite')
HOST = '127.0.0.1'
MAX_BODY = 8 * 1024 * 1024
ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,40}$')
USER_RE = re.compile(r'^[A-Za-z0-9_.-]{3,20}$')
PW_MIN, PW_MAX = 6, 128
PBKDF2_ROUNDS = 200_000
SESSION_SECS = 30 * 24 * 3600
COOKIE_NAME = 'kt_session'
DB_LOCK = threading.Lock()
FAILS = {}   # nama pengguna (huruf kecil) -> [jumlah gagal, terkunci sampai]

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ukey    TEXT NOT NULL UNIQUE,      -- nama pengguna huruf kecil (untuk pencocokan)
    name    TEXT NOT NULL,             -- nama pengguna sesuai ejaan pendaftaran
    pw      TEXT NOT NULL,             -- pbkdf2$putaran$salt$hash
    created INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token   TEXT PRIMARY KEY,          -- SHA-256 dari token di cookie
    user_id INTEGER NOT NULL,
    created INTEGER NOT NULL,
    expires INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS slots (
    id      TEXT PRIMARY KEY,
    user_id INTEGER,                   -- pemilik; NULL = belum diklaim (data lama)
    name    TEXT NOT NULL,
    created INTEGER NOT NULL,
    updated INTEGER NOT NULL,
    summary TEXT NOT NULL,
    data    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    slot_id TEXT NOT NULL,
    time    INTEGER NOT NULL,
    reason  TEXT NOT NULL,
    summary TEXT NOT NULL,
    data    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_slot ON snapshots(slot_id, id);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,            -- 'active:<id pengguna>'
    value TEXT
);
"""


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


@contextlib.contextmanager
def connect():
    """Koneksi per permintaan: commit bila sukses, rollback bila galat, lalu ditutup."""
    con = sqlite3.connect(DB_FILE, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        with con:
            yield con
    finally:
        con.close()


def backup_db():
    """Salin file DB ke kantin-tycoon.sqlite.bak sebelum menyentuhnya (jaring pengaman)."""
    try:
        if os.path.exists(DB_FILE) and os.path.getsize(DB_FILE) > 0:
            shutil.copy2(DB_FILE, DB_FILE + '.bak')
    except OSError as e:
        print('Peringatan: gagal membuat cadangan DB:', e, file=sys.stderr)


def init_db():
    backup_db()
    with connect() as con:
        con.executescript(SCHEMA)
        cols = [r['name'] for r in con.execute('PRAGMA table_info(slots)')]
        if 'user_id' not in cols:          # basis data dari versi sebelum ada akun
            con.execute('ALTER TABLE slots ADD COLUMN user_id INTEGER')


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))


def slot_meta(row):
    return {'id': row['id'], 'name': row['name'], 'created': row['created'],
            'updated': row['updated'], 'summary': json.loads(row['summary'])}


def need_id(value):
    if not isinstance(value, str) or not ID_RE.match(value):
        raise ApiError(400, 'id tidak valid')
    return value


def need_int(value, default=0):
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default


# ---------------------------------------------------------------- akun & sesi
def hash_password(pw, salt=None):
    salt = salt or os.urandom(16)
    h = hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), salt, PBKDF2_ROUNDS)
    return f'pbkdf2${PBKDF2_ROUNDS}${salt.hex()}${h.hex()}'


def verify_password(pw, stored):
    try:
        _, rounds, salt, want = stored.split('$')
        got = hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(got.hex(), want)
    except (ValueError, TypeError):
        return False


_DUMMY_HASH = hash_password('tidak-dipakai', b'\x00' * 16)   # menyamakan waktu untuk nama yang tidak ada


def need_credentials(body):
    if not isinstance(body, dict):
        raise ApiError(400, 'data tidak valid')
    name, pw = body.get('username'), body.get('password')
    if not isinstance(name, str) or not USER_RE.match(name):
        raise ApiError(400, 'Nama pengguna 3-20 karakter: huruf, angka, titik, garis bawah, atau strip.')
    if not isinstance(pw, str) or not (PW_MIN <= len(pw) <= PW_MAX):
        raise ApiError(400, f'Kata sandi minimal {PW_MIN} karakter.')
    return name, pw


def check_lock(key):
    rec = FAILS.get(key)
    if rec and rec[1] > time.time():
        raise ApiError(429, f'Terlalu banyak percobaan. Coba lagi dalam {int(rec[1] - time.time()) + 1} detik.')


def note_fail(key):
    rec = FAILS.setdefault(key, [0, 0])
    rec[0] += 1
    if rec[0] >= 5:
        rec[0], rec[1] = 0, time.time() + 30


def token_hash(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def cookie_header(token, max_age):
    return f'{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}'


def start_session(con, user_id):
    now = int(time.time())
    con.execute('DELETE FROM sessions WHERE expires < ?', (now,))
    token = secrets.token_urlsafe(32)
    con.execute('INSERT INTO sessions(token,user_id,created,expires) VALUES(?,?,?,?)',
                (token_hash(token), user_id, now, now + SESSION_SECS))
    return cookie_header(token, SESSION_SECS)


def current_user(con, token):
    if not token:
        return None
    return con.execute(
        'SELECT u.id, u.name FROM sessions s JOIN users u ON u.id = s.user_id '
        'WHERE s.token = ? AND s.expires > ?', (token_hash(token), int(time.time()))).fetchone()


def drop_user_data(con, uid):
    con.execute('DELETE FROM snapshots WHERE slot_id IN (SELECT id FROM slots WHERE user_id=?)', (uid,))
    con.execute('DELETE FROM slots WHERE user_id=?', (uid,))
    con.execute('DELETE FROM meta WHERE key=?', (f'active:{uid}',))


def own_slot(con, sid, uid, cols='*'):
    row = con.execute(f'SELECT {cols} FROM slots WHERE id=? AND user_id=?', (sid, uid)).fetchone()
    if not row:
        raise ApiError(404, 'slot tidak ada')
    return row


# ---------------------------------------------------------------------- API
def handle_api(method, parts, body, token):
    """Mengembalikan (status, objek-json, header-Set-Cookie atau None). DB_LOCK sudah terkunci."""
    with connect() as con:
        # ---- publik
        if parts == ['ping'] and method == 'GET':
            return 200, {'ok': True, 'file': os.path.basename(DB_FILE), 'accounts': True}, None

        if parts == ['me'] and method == 'GET':
            u = current_user(con, token)
            return 200, {'user': {'id': u['id'], 'name': u['name']} if u else None}, None

        if parts == ['register'] and method == 'POST':
            name, pw = need_credentials(body)
            ukey = name.lower()
            if con.execute('SELECT 1 FROM users WHERE ukey=?', (ukey,)).fetchone():
                raise ApiError(409, 'Nama pengguna sudah dipakai.')
            first = con.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0
            uid = con.execute('INSERT INTO users(ukey,name,pw,created) VALUES(?,?,?,?)',
                              (ukey, name, hash_password(pw), int(time.time()))).lastrowid
            if first:   # akun pertama mengambil alih simpanan lama yang belum bertuan
                con.execute('UPDATE slots SET user_id=? WHERE user_id IS NULL', (uid,))
                old = con.execute("SELECT value FROM meta WHERE key='active'").fetchone()
                if old:
                    con.execute('INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)', (f'active:{uid}', old['value']))
            return 200, {'user': {'id': uid, 'name': name}}, start_session(con, uid)

        if parts == ['login'] and method == 'POST':
            name, pw = need_credentials(body)
            ukey = name.lower()
            check_lock(ukey)
            row = con.execute('SELECT id,name,pw FROM users WHERE ukey=?', (ukey,)).fetchone()
            ok = verify_password(pw, row['pw'] if row else _DUMMY_HASH)
            if not row or not ok:
                note_fail(ukey)
                raise ApiError(401, 'Nama pengguna atau kata sandi salah.')
            FAILS.pop(ukey, None)
            return 200, {'user': {'id': row['id'], 'name': row['name']}}, start_session(con, row['id'])

        if parts == ['logout'] and method == 'POST':
            if token:
                con.execute('DELETE FROM sessions WHERE token=?', (token_hash(token),))
            return 200, {'ok': True}, cookie_header('', 0)

        # ---- selebihnya wajib masuk
        user = current_user(con, token)
        if not user:
            raise ApiError(401, 'Belum masuk.')
        uid = user['id']

        if parts == ['password'] and method == 'POST':
            old, new = (body or {}).get('old'), (body or {}).get('new')
            if not isinstance(new, str) or not (PW_MIN <= len(new) <= PW_MAX):
                raise ApiError(400, f'Kata sandi baru minimal {PW_MIN} karakter.')
            row = con.execute('SELECT pw, ukey FROM users WHERE id=?', (uid,)).fetchone()
            check_lock(row['ukey'])
            if not isinstance(old, str) or not verify_password(old, row['pw']):
                note_fail(row['ukey'])
                raise ApiError(401, 'Kata sandi lama salah.')
            con.execute('UPDATE users SET pw=? WHERE id=?', (hash_password(new), uid))
            con.execute('DELETE FROM sessions WHERE user_id=? AND token<>?', (uid, token_hash(token)))
            return 200, {'ok': True}, None

        if parts == ['account', 'delete'] and method == 'POST':
            pw = (body or {}).get('password')
            row = con.execute('SELECT pw, ukey FROM users WHERE id=?', (uid,)).fetchone()
            check_lock(row['ukey'])
            if not isinstance(pw, str) or not verify_password(pw, row['pw']):
                note_fail(row['ukey'])
                raise ApiError(401, 'Kata sandi salah.')
            drop_user_data(con, uid)
            con.execute('DELETE FROM sessions WHERE user_id=?', (uid,))
            con.execute('DELETE FROM users WHERE id=?', (uid,))
            return 200, {'ok': True}, cookie_header('', 0)

        if parts == ['slots'] and method == 'GET':
            rows = con.execute('SELECT id,name,created,updated,summary FROM slots '
                               'WHERE user_id=? ORDER BY updated DESC', (uid,)).fetchall()
            return 200, [slot_meta(r) for r in rows], None

        if len(parts) == 2 and parts[0] == 'slots':
            sid = need_id(parts[1])
            if method == 'GET':
                row = own_slot(con, sid, uid)
                rec = slot_meta(row)
                rec['data'] = json.loads(row['data'])
                return 200, rec, None
            if method == 'PUT':
                if not isinstance(body, dict) or not isinstance(body.get('data'), dict):
                    raise ApiError(400, 'isi slot tidak valid')
                existing = con.execute('SELECT user_id FROM slots WHERE id=?', (sid,)).fetchone()
                if existing and existing['user_id'] not in (None, uid):
                    raise ApiError(403, 'slot milik akun lain')
                name = str(body.get('name', ''))[:60] or 'Tanpa nama'
                con.execute(
                    'INSERT INTO slots(id,user_id,name,created,updated,summary,data) VALUES(?,?,?,?,?,?,?) '
                    'ON CONFLICT(id) DO UPDATE SET user_id=excluded.user_id, name=excluded.name, '
                    'updated=excluded.updated, summary=excluded.summary, data=excluded.data',
                    (sid, uid, name, need_int(body.get('created')), need_int(body.get('updated')),
                     dumps(body.get('summary') or {}), dumps(body['data'])))
                return 200, {'ok': True}, None
            if method == 'DELETE':
                own_slot(con, sid, uid, 'id')
                con.execute('DELETE FROM snapshots WHERE slot_id=?', (sid,))
                con.execute('DELETE FROM slots WHERE id=?', (sid,))
                return 200, {'ok': True}, None

        if len(parts) == 3 and parts[0] == 'slots' and parts[2] == 'snapshots' and method == 'GET':
            sid = need_id(parts[1])
            own_slot(con, sid, uid, 'id')
            rows = con.execute('SELECT id,time,reason,summary FROM snapshots WHERE slot_id=? ORDER BY id',
                               (sid,)).fetchall()
            return 200, [{'id': r['id'], 'time': r['time'], 'reason': r['reason'],
                          'summary': json.loads(r['summary'])} for r in rows], None

        if parts == ['snapshots'] and method == 'POST':
            if not isinstance(body, dict) or not isinstance(body.get('data'), dict):
                raise ApiError(400, 'isi cadangan tidak valid')
            sid = need_id(body.get('slotId'))
            own_slot(con, sid, uid, 'id')
            keep = min(max(need_int(body.get('max'), 10), 1), 50)
            con.execute('INSERT INTO snapshots(slot_id,time,reason,summary,data) VALUES(?,?,?,?,?)',
                        (sid, need_int(body.get('time')), str(body.get('reason', ''))[:80],
                         dumps(body.get('summary') or {}), dumps(body['data'])))
            con.execute('DELETE FROM snapshots WHERE slot_id=? AND id NOT IN '
                        '(SELECT id FROM snapshots WHERE slot_id=? ORDER BY id DESC LIMIT ?)', (sid, sid, keep))
            return 200, {'ok': True}, None

        if len(parts) == 2 and parts[0] == 'snapshots' and method == 'GET':
            row = con.execute('SELECT n.* FROM snapshots n JOIN slots s ON s.id = n.slot_id '
                              'WHERE n.id=? AND s.user_id=?', (need_int(parts[1], -1), uid)).fetchone()
            if not row:
                raise ApiError(404, 'cadangan tidak ada')
            return 200, {'id': row['id'], 'slotId': row['slot_id'], 'time': row['time'], 'reason': row['reason'],
                         'summary': json.loads(row['summary']), 'data': json.loads(row['data'])}, None

        if parts == ['meta', 'active']:
            key = f'active:{uid}'
            if method == 'GET':
                row = con.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
                return 200, {'value': row['value'] if row else None}, None
            if method == 'PUT':
                value = need_id(body.get('value') if isinstance(body, dict) else None)
                own_slot(con, value, uid, 'id')
                con.execute('INSERT INTO meta(key,value) VALUES(?,?) '
                            'ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, value))
                return 200, {'ok': True}, None

        if parts == ['reset'] and method == 'POST':
            drop_user_data(con, uid)       # hanya data akun ini, bukan akun lain
            return 200, {'ok': True}, None

    raise ApiError(404, 'endpoint tidak dikenal')


class Handler(BaseHTTPRequestHandler):
    server_version = 'KantinTycoon/2.0'

    def log_message(self, fmt, *args):
        pass

    # --- keamanan: hanya klien dari halaman sendiri yang boleh memakai API
    def allowed_hosts(self):
        port = self.server.server_port
        return {f'127.0.0.1:{port}', f'localhost:{port}'}

    def send_bytes(self, status, payload, ctype, cookie=None):
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(payload)

    def send_json(self, status, obj, cookie=None):
        self.send_bytes(status, dumps(obj).encode('utf-8'), 'application/json; charset=utf-8', cookie)

    def read_body(self):
        length = int(self.headers.get('Content-Length') or 0)
        if length > MAX_BODY:
            raise ApiError(413, 'terlalu besar')
        if not length:
            return None
        try:
            return json.loads(self.rfile.read(length).decode('utf-8'))
        except ValueError:
            raise ApiError(400, 'JSON tidak valid')

    def session_token(self):
        raw = self.headers.get('Cookie')
        if not raw:
            return None
        try:
            c = SimpleCookie(raw)
        except Exception:
            return None
        m = c.get(COOKIE_NAME)
        return m.value if m else None

    def route(self, method):
        try:
            if self.headers.get('Host', '') not in self.allowed_hosts():
                raise ApiError(403, 'host ditolak')
            path = urlparse(self.path).path
            if not path.startswith('/api/'):
                if method == 'GET' and path in ('/', '/index.html', '/kantin-tycoon.html'):
                    with open(GAME_FILE, 'rb') as f:
                        return self.send_bytes(200, f.read(), 'text/html; charset=utf-8')
                raise ApiError(404, 'tidak ditemukan')
            origin = self.headers.get('Origin')
            if self.headers.get('X-Kantin') != '1' or (origin and urlparse(origin).netloc not in self.allowed_hosts()):
                raise ApiError(403, 'permintaan ditolak')
            parts = [unquote(p) for p in path[5:].strip('/').split('/') if p]
            body = self.read_body() if method in ('PUT', 'POST') else None
            with DB_LOCK:
                status, obj, cookie = handle_api(method, parts, body, self.session_token())
            self.send_json(status, obj, cookie)
        except ApiError as e:
            self.send_json(e.status, {'error': e.message})
        except Exception as e:  # jangan biarkan server mati karena satu permintaan
            print('Galat:', repr(e), file=sys.stderr)
            self.send_json(500, {'error': 'galat server'})

    def do_GET(self): self.route('GET')
    def do_PUT(self): self.route('PUT')
    def do_POST(self): self.route('POST')
    def do_DELETE(self): self.route('DELETE')
    def do_HEAD(self): self.route('GET')


def already_running(port):
    try:
        req = urllib.request.Request(f'http://{HOST}:{port}/api/ping', headers={'X-Kantin': '1'})
        with urllib.request.urlopen(req, timeout=1) as r:
            return json.load(r).get('ok') is True
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(description='Server savegame Kantin Tycoon')
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--no-browser', action='store_true')
    args = ap.parse_args()

    if not os.path.exists(GAME_FILE):
        sys.exit(f'File game tidak ditemukan: {GAME_FILE}')
    if already_running(args.port):
        url = f'http://{HOST}:{args.port}/'
        print(f'Server sudah berjalan di {url}')
        if not args.no_browser:
            webbrowser.open(url)
        return

    init_db()

    srv = None
    for port in range(args.port, args.port + 20):
        try:
            srv = ThreadingHTTPServer((HOST, port), Handler)
            break
        except OSError:
            continue
    if srv is None:
        sys.exit('Tidak ada port kosong.')

    url = f'http://{HOST}:{srv.server_port}/'
    print('Kantin Tycoon berjalan di', url)
    print('File simpanan :', DB_FILE)
    print('Tekan Ctrl+C atau tutup jendela ini untuk berhenti.')
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == '__main__':
    main()
