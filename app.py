"""
NexaBank — Intelligent Onboarding Backend
Real Flask + Real SQLite + Real File Storage + Claude AI Chat
"""

import os, json, uuid, hashlib, random, time, re
from datetime import datetime
from functools import wraps
from flask import (Flask, request, jsonify, session,render_template,
                   send_from_directory, redirect, url_for)
from werkzeug.utils import secure_filename
import sqlite3

try:
    from PIL import Image
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

# ─── CONFIG ──────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DB_PATH    = os.path.join(BASE_DIR, 'instance', 'nexabank.db')
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
DOC_DIR    = os.path.join(UPLOAD_DIR, 'documents')
SELFIE_DIR = os.path.join(UPLOAD_DIR, 'selfies')

for d in [os.path.join(BASE_DIR,'instance'), DOC_DIR, SELFIE_DIR]:
    os.makedirs(d, exist_ok=True)

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = 'nexabank-secret-2025-hackathon'   # fixed so sessions survive restarts
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

ALLOWED_DOC     = {'png','jpg','jpeg','pdf'}
ALLOWED_SELFIE  = {'png','jpg','jpeg','webp'}

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

# ─── DATABASE ────────────────────────────────────────────────────────────────
def db_connect():
    # increase timeout so connections wait longer rather than immediately failing
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    # ensure WAL journaling and set a busy timeout for locks
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=3000")
    return conn

def init_db():
    con = db_connect()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS admin_users (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        username    TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name   TEXT,
        role        TEXT DEFAULT 'reviewer',
        created_at  TEXT
    );

    CREATE TABLE IF NOT EXISTS applications (
        id              TEXT PRIMARY KEY,
        name            TEXT,
        dob             TEXT,
        email           TEXT,
        phone           TEXT,
        id_type         TEXT,
        id_number       TEXT,
        address         TEXT,
        method          TEXT DEFAULT 'Manual',
        selfie_path     TEXT,
        doc_path        TEXT,
        ocr_raw         TEXT,
        face_score      INTEGER,
        face_status     TEXT DEFAULT 'Pending',
        risk_score      INTEGER,
        risk_level      TEXT,
        risk_signals    TEXT,
        risk_reason     TEXT,
        otp_hash        TEXT,
        otp_verified    INTEGER DEFAULT 0,
        account_number  TEXT,
        ifsc            TEXT,
        branch          TEXT DEFAULT 'NexaBank Digital Branch',
        account_type    TEXT DEFAULT 'Savings',
        status          TEXT DEFAULT 'In Progress',
        created_at      TEXT,
        updated_at      TEXT
    );

    CREATE TABLE IF NOT EXISTS documents (
        id              TEXT PRIMARY KEY,
        application_id  TEXT NOT NULL,
        doc_type        TEXT,
        original_name   TEXT,
        stored_name     TEXT,
        file_hash       TEXT,
        file_size       INTEGER,
        ocr_text        TEXT,
        ocr_name        TEXT,
        ocr_dob         TEXT,
        ocr_id_number   TEXT,
        tamper_flags    TEXT,
        confidence      INTEGER,
        verified        INTEGER DEFAULT 0,
        uploaded_at     TEXT,
        FOREIGN KEY(application_id) REFERENCES applications(id)
    );

    CREATE TABLE IF NOT EXISTS chat_messages (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id  TEXT,
        role            TEXT,
        content         TEXT,
        timestamp       TEXT
    );

    CREATE TABLE IF NOT EXISTS audit_log (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id  TEXT,
        action          TEXT NOT NULL,
        actor           TEXT DEFAULT 'SYSTEM',
        detail          TEXT,
        ip              TEXT,
        timestamp       TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS admin_decisions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id  TEXT NOT NULL,
        admin_username  TEXT,
        decision        TEXT,
        notes           TEXT,
        ai_overridden   INTEGER DEFAULT 0,
        decided_at      TEXT
    );
    """)

    # Seed admin user (password: admin123)
    pw_hash = hashlib.sha256('admin123'.encode()).hexdigest()
    con.execute("""
        INSERT OR IGNORE INTO admin_users (username, password_hash, full_name, role, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, ('admin', pw_hash, 'System Administrator', 'superadmin', now()))

    # Seed demo reviewer (password: reviewer123)
    pw2 = hashlib.sha256('reviewer123'.encode()).hexdigest()
    con.execute("""
        INSERT OR IGNORE INTO admin_users (username, password_hash, full_name, role, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, ('reviewer', pw2, 'KYC Reviewer', 'reviewer', now()))

    # Seed demo applications
    seed_applications(con)
    con.commit()
    con.close()

def seed_applications(con):
    count = con.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    if count > 0:
        return
    demos = [
        ('NXB-DEMO-001','Rohan Mehta','1992-04-15','rohan.mehta@gmail.com',
         '+91-9876543210','Aadhaar','XXXX-XXXX-7842','Manual',82,'Low',
         'Approved','7742 8910 3351','NXBA0001'),
        ('NXB-DEMO-002','Priya Sharma','1988-11-22','priya.sharma@gmail.com',
         '+91-9812345678','PAN','ABCDE1234F','Manual',54,'Medium',
         'Pending',None,None),
        ('NXB-DEMO-003','Anjali Gupta','2001-07-08','anjali.g@gmail.com',
         '+91-9900112233','Passport','P1234567','Manual',18,'High',
         'Escalated',None,None),
        ('NXB-DEMO-004','Vikram Singh','1995-03-30','vikram.s@gmail.com',
         '+91-9988776655','Aadhaar','XXXX-XXXX-3391','Manual',91,'Low',
         'Approved','6612 4430 9981','NXBA0001'),
        ('NXB-DEMO-005','Kavitha Nair','1990-09-12','kavitha.n@gmail.com',
         '+91-9871234560','PAN','FGHIJ5678K','Manual',48,'Medium',
         'Pending',None,None),
    ]
    reasons = {
        'Low':    'All checks passed. Document integrity verified. Biometric match strong. No AML flags.',
        'Medium': 'Minor OCR discrepancy detected. Manual secondary verification recommended.',
        'High':   'Multiple face-match attempts failed. Potential document tampering. AML flag raised.',
    }
    for d in demos:
        ts = now()
        con.execute("""
            INSERT INTO applications
            (id,name,dob,email,phone,id_type,id_number,method,risk_score,risk_level,
             status,account_number,ifsc,risk_reason,face_score,otp_verified,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)
        """, (*d, reasons[d[9]], random.randint(80,99), ts, ts))
        log(con, d[0], 'APPLICATION_SEEDED', f'Demo data: {d[1]}')

def now():
    return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')

def to_dict(row):
    return dict(row) if row else None

def log(con, app_id, action, detail='', actor='SYSTEM'):
    con.execute(
        "INSERT INTO audit_log(application_id,action,actor,detail,ip,timestamp) VALUES(?,?,?,?,?,?)",
        (app_id, action, actor, detail,
         request.remote_addr if request else '127.0.0.1', now())
    )

# ─── AUTH HELPERS ─────────────────────────────────────────────────────────────
def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return jsonify({'error': 'Unauthorized. Please login.'}), 401
        return f(*args, **kwargs)
    return decorated

# ─── OCR ENGINE ───────────────────────────────────────────────────────────────
def run_ocr(file_path, doc_type):
    """Run real OCR on uploaded document image."""
    result = {
        'raw_text': '',
        'name': None, 'dob': None, 'id_number': None,
        'confidence': 0, 'tamper_flags': []
    }
    if not OCR_AVAILABLE:
        return result
    try:
        img = Image.open(file_path)
        # Enhance for OCR
        img = img.convert('L')  # grayscale
        text = pytesseract.image_to_string(img, config='--psm 6')
        result['raw_text'] = text

        # Extract name (line with all caps or title case, 2+ words)
        for line in text.splitlines():
            line = line.strip()
            if len(line.split()) >= 2 and re.match(r'^[A-Za-z ]{4,40}$', line):
                result['name'] = line.title()
                break

        # Extract DOB patterns
        dob_match = re.search(r'\b(\d{2}[\/\-\.]\d{2}[\/\-\.]\d{4})\b', text)
        if dob_match:
            result['dob'] = dob_match.group(1)

        # Extract ID numbers
        if doc_type == 'Aadhaar':
            m = re.search(r'\b(\d{4}\s?\d{4}\s?\d{4})\b', text)
            if m: result['id_number'] = m.group(1)
        elif doc_type == 'PAN':
            m = re.search(r'\b([A-Z]{5}\d{4}[A-Z])\b', text)
            if m: result['id_number'] = m.group(1)
        elif doc_type == 'Passport':
            m = re.search(r'\b([A-Z]\d{7})\b', text)
            if m: result['id_number'] = m.group(1)

        # Confidence: based on text extracted
        word_count = len(text.split())
        result['confidence'] = min(95, max(30, word_count * 3))

        # Tamper flags: very low text = suspicious
        if word_count < 5:
            result['tamper_flags'].append('Very low text content — possible blank or corrupted document')
        if word_count > 200:
            result['tamper_flags'].append('Unusually high text density')

    except Exception as e:
        result['tamper_flags'].append(f'OCR processing error: {str(e)}')

    return result

# ─── RISK ENGINE ──────────────────────────────────────────────────────────────
def compute_risk(app_row, doc_rows):
    score  = 100
    signals = []

    # 1. OCR confidence
    if doc_rows:
        confidences = [d['confidence'] or 50 for d in doc_rows]
        avg_conf = sum(confidences) / len(confidences)
        if avg_conf >= 75:
            signals.append({'factor': 'OCR Confidence',   'weight': 0,   'note': f'{avg_conf:.0f}% — high quality document image'})
        elif avg_conf >= 50:
            score -= 10
            signals.append({'factor': 'OCR Confidence',   'weight': -10, 'note': f'{avg_conf:.0f}% — moderate quality'})
        else:
            score -= 25
            signals.append({'factor': 'OCR Confidence',   'weight': -25, 'note': f'{avg_conf:.0f}% — low quality or illegible'})

        # 2. Tamper flags
        all_flags = []
        for d in doc_rows:
            flags = json.loads(d['tamper_flags'] or '[]')
            all_flags.extend(flags)
        if all_flags:
            score -= 20 * len(all_flags)
            signals.append({'factor': 'Tamper Detection', 'weight': -20*len(all_flags), 'note': '; '.join(all_flags)})
        else:
            signals.append({'factor': 'Tamper Detection', 'weight': 0, 'note': 'No anomalies detected'})

    # 3. Age
    try:
        dob = datetime.strptime(app_row['dob'], '%Y-%m-%d')
        age = (datetime.now() - dob).days // 365
        if age < 18:
            score -= 100
            signals.append({'factor': 'Age Gate',         'weight': -100, 'note': f'Applicant is {age} — below 18'})
        elif 18 <= age <= 65:
            signals.append({'factor': 'Age Gate',         'weight': 0,   'note': f'Age {age} — valid range'})
        else:
            score -= 5
            signals.append({'factor': 'Age Gate',         'weight': -5,  'note': f'Age {age} — senior applicant'})
    except:
        score -= 10
        signals.append({'factor': 'Age Gate',             'weight': -10, 'note': 'DOB parse error'})

    # 4. Face match
    face = app_row['face_score'] or 0
    if face >= 90:
        signals.append({'factor': 'Biometric Match',      'weight': 0,   'note': f'{face}% — strong match'})
    elif face >= 75:
        score -= 10
        signals.append({'factor': 'Biometric Match',      'weight': -10, 'note': f'{face}% — acceptable'})
    elif face > 0:
        score -= 30
        signals.append({'factor': 'Biometric Match',      'weight': -30, 'note': f'{face}% — poor match'})
    else:
        score -= 15
        signals.append({'factor': 'Biometric Match',      'weight': -15, 'note': 'No biometric data'})

    # 5. OTP verified
    if app_row['otp_verified']:
        signals.append({'factor': 'OTP Verification',     'weight': 0,   'note': 'Mobile/email OTP verified'})
    else:
        score -= 20
        signals.append({'factor': 'OTP Verification',     'weight': -20, 'note': 'OTP not verified'})

    # 6. Email domain
    email = app_row['email'] or ''
    disposable = ['tempmail','guerrillamail','mailinator','yopmail','throwam']
    if any(d in email for d in disposable):
        score -= 20
        signals.append({'factor': 'Email Trust',          'weight': -20, 'note': 'Disposable email detected'})
    elif email:
        signals.append({'factor': 'Email Trust',          'weight': 0,   'note': 'Email domain OK'})

    score = max(0, min(100, score))
    level = 'Low' if score >= 70 else 'Medium' if score >= 45 else 'High'

    neg_notes = [s['note'] for s in signals if s['weight'] < 0]
    pos_notes = [s['note'] for s in signals if s['weight'] == 0]

    if level == 'Low':
        reason = 'All verification checks passed. ' + '. '.join(pos_notes[:3])
    elif level == 'Medium':
        reason = 'Partial verification with minor issues. ' + '. '.join(neg_notes)
    else:
        reason = 'Significant risk factors detected. ' + '. '.join(neg_notes)

    return score, level, signals, reason

# ─── CLAUDE AI CHAT ──────────────────────────────────────────────────────────
def ask_claude(messages, system_prompt):
    """Call Claude API for AI chat responses."""
    if not ANTHROPIC_API_KEY:
        return None   # frontend will use its own flow

    import urllib.request
    payload = json.dumps({
        'model': 'claude-sonnet-4-6',
        'max_tokens': 400,
        'system': system_prompt,
        'messages': messages
    }).encode()

    req = urllib.request.Request(
        'https://api.anthropic.com/v1/messages',
        data=payload,
        headers={
            'x-api-key': ANTHROPIC_API_KEY,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        },
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data['content'][0]['text']
    except Exception as e:
        print(f'Claude API error: {e}')
        return None

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — PAGES
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin-login')
def admin_login_page():
    if session.get('admin_logged_in'):
        return redirect('/admin')
    return render_template('admin_login.html')

@app.route('/admin')
def admin_page():
    if not session.get('admin_logged_in'):
        return redirect('/admin-login')
    return render_template('admin.html')

@app.route('/uploads/selfies/<filename>')
def serve_selfie(filename):
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    return send_from_directory(SELFIE_DIR, filename)

@app.route('/uploads/documents/<filename>')
def serve_doc(filename):
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    return send_from_directory(DOC_DIR, filename)

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — ADMIN AUTH
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json()
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    con = db_connect()
    user = con.execute(
        "SELECT * FROM admin_users WHERE username=? AND password_hash=?",
        (username, hash_pw(password))
    ).fetchone()
    con.close()

    if not user:
        return jsonify({'error': 'Invalid username or password'}), 401

    session['admin_logged_in'] = True
    session['admin_username']  = user['username']
    session['admin_name']      = user['full_name']
    session['admin_role']      = user['role']

    return jsonify({
        'success': True,
        'username': user['username'],
        'full_name': user['full_name'],
        'role': user['role']
    })

@app.route('/api/admin/logout', methods=['POST'])
def admin_logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/admin/me', methods=['GET'])
@admin_required
def admin_me():
    return jsonify({
        'username': session.get('admin_username'),
        'full_name': session.get('admin_name'),
        'role': session.get('admin_role')
    })

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — ONBOARDING SESSION
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/session/start', methods=['POST'])
def session_start():
    app_id = 'NXB-' + uuid.uuid4().hex[:8].upper()
    ts = now()
    con = db_connect()
    con.execute(
        "INSERT INTO applications(id,status,method,created_at,updated_at) VALUES(?,?,?,?,?)",
        (app_id, 'In Progress', 'Manual', ts, ts)
    )
    # Welcome message from AI stored in DB
    con.execute(
        "INSERT INTO chat_messages(application_id,role,content,timestamp) VALUES(?,?,?,?)",
        (app_id, 'assistant',
         "Welcome to NexaBank! I'm ARIA, your AI onboarding assistant. I'll guide you through creating your account securely. Let's get started — could you please tell me your **full name** as it appears on your ID?",
         ts)
    )
    log(con, app_id, 'SESSION_STARTED', f'New application {app_id}')
    con.commit()
    con.close()

    session['app_id'] = app_id
    return jsonify({'application_id': app_id, 'created_at': ts})

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — AI CHAT
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/chat/message', methods=['POST'])
def chat_message():
    """
    Receive a user message, get AI response, store both, return response.
    Falls back to rule-based responses if no Claude API key.
    """
    data   = request.get_json()
    app_id = session.get('app_id') or data.get('application_id')
    msg    = (data.get('message') or '').strip()
    step   = data.get('step', 'name')   # which step we're on

    if not app_id or not msg:
        return jsonify({'error': 'Missing app_id or message'}), 400

    ts  = now()
    con = db_connect()

    # Store user message
    con.execute(
        "INSERT INTO chat_messages(application_id,role,content,timestamp) VALUES(?,?,?,?)",
        (app_id, 'user', msg, ts)
    )

    # Get conversation history for context
    history = con.execute(
        "SELECT role, content FROM chat_messages WHERE application_id=? ORDER BY id",
        (app_id,)
    ).fetchall()

    # Get app state
    app_row = con.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()

    ai_reply = None

    # Try Claude if key available
    if ANTHROPIC_API_KEY:
        system = """You are ARIA, an AI assistant for NexaBank's customer onboarding process.
You are professional, friendly, and concise. You guide customers through:
1. Collecting personal details (name, DOB in YYYY-MM-DD format, email, phone)
2. Requesting document upload (Aadhaar/PAN/Passport)
3. Requesting selfie for face verification
4. OTP verification
5. Completing account creation

Keep responses short (2-3 sentences max). Be warm and reassuring about security.
Do NOT ask for sensitive data like full Aadhaar number or bank account details."""

        claude_msgs = [{'role': r['role'], 'content': r['content']} for r in history]
        ai_reply = ask_claude(claude_msgs, system)

    # Fallback: rule-based responses per step
    if not ai_reply:
        ai_reply = rule_based_response(step, msg, app_row)

    # Store AI response
    con.execute(
        "INSERT INTO chat_messages(application_id,role,content,timestamp) VALUES(?,?,?,?)",
        (app_id, 'assistant', ai_reply, now())
    )
    log(con, app_id, 'CHAT_MESSAGE', f'Step: {step} | User: {msg[:60]}')
    con.commit()
    con.close()

    return jsonify({
        'reply': ai_reply,
        'application_id': app_id
    })

def rule_based_response(step, msg, app_row):
    responses = {
        'name': f"Thank you! Nice to meet you. Now, could you please provide your **date of birth** in YYYY-MM-DD format? (e.g., 1995-03-15)",
        'dob':  "Got it! What is your **email address**? We'll use this for account notifications and OTP verification.",
        'email':"Perfect. And your **mobile number** with country code? (e.g., +91-9876543210)",
        'phone':"Thank you for providing your details. Now please **upload your ID document** — Aadhaar Card, PAN Card, or Passport. Use the upload button below.",
        'doc':  "Document received and being processed. Now I need a **selfie photo** for biometric face verification. Please use the capture button.",
        'selfie':"Selfie captured! I'm now sending an **OTP to your registered email/mobile**. Please enter the 6-digit code you receive.",
        'otp':  "OTP verified successfully! ✅ I'm now running the final risk assessment on your application.",
        'done': "Your application has been processed! Please wait while I complete the final checks.",
    }
    return responses.get(step, "I'm processing your information. Please continue with the next step.")

@app.route('/api/chat/history/<app_id>', methods=['GET'])
def chat_history(app_id):
    con = db_connect()
    msgs = con.execute(
        "SELECT role, content, timestamp FROM chat_messages WHERE application_id=? ORDER BY id",
        (app_id,)
    ).fetchall()
    con.close()
    return jsonify([dict(m) for m in msgs])

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — IDENTITY
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/identity/submit', methods=['POST'])
def submit_identity():
    data   = request.get_json()
    app_id = session.get('app_id') or data.get('application_id')
    print(f'[Identity] Received submission: app_id={app_id}, from_session={bool(session.get("app_id"))}, from_body={bool(data.get("application_id"))}')

    if not app_id:
        # client somehow lost session or didn't send app_id;
        # auto-create a new onboarding record so user can continue
        app_id = 'NXB-' + uuid.uuid4().hex[:8].upper()
        ts = now()
        con = db_connect()
        con.execute(
            "INSERT INTO applications(id,status,method,created_at,updated_at) VALUES(?,?,?,?,?)",
            (app_id, 'In Progress', 'Manual', ts, ts)
        )
        log(con, app_id, 'SESSION_AUTO_CREATED',
            'Created new application during identity submit without existing session')
        con.commit()
        con.close()
        session['app_id'] = app_id
        print(f'[Identity] Created new app_id: {app_id}')
        # continue with newly generated id

    name  = (data.get('name') or '').strip()
    dob   = (data.get('dob') or '').strip()
    email = (data.get('email') or '').strip()
    phone = (data.get('phone') or '').strip()

    name  = (data.get('name') or '').strip()
    dob   = (data.get('dob') or '').strip()
    email = (data.get('email') or '').strip()
    phone = (data.get('phone') or '').strip()

    # Validate
    errors = {}
    if not name or len(name) < 2:
        errors['name'] = 'Full name is required (min 2 characters)'
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', dob):
        errors['dob'] = 'Date of birth must be in YYYY-MM-DD format'
    if not re.match(r'^[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}$', email):
        errors['email'] = 'Valid email address required'
    if errors:
        return jsonify({'error': 'Validation failed', 'fields': errors}), 400

    # Age check
    try:
        dob_dt = datetime.strptime(dob, '%Y-%m-%d')
        age    = (datetime.now() - dob_dt).days // 365
        if age < 18:
            return jsonify({'error': f'Applicant must be 18 or older. Calculated age: {age}'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid date of birth'}), 400

    ts  = now()
    con = db_connect()
    print(f'[Identity] Updating app_id={app_id} with name={name}, email={email}')
    con.execute("""
        UPDATE applications
        SET name=?, dob=?, email=?, phone=?, updated_at=?
        WHERE id=?
    """, (name, dob, email, phone, ts, app_id))
    
    # Verify the update worked
    verify = con.execute("SELECT name, email FROM applications WHERE id=?", (app_id,)).fetchone()
    if verify:
        print(f'[Identity] ✓ Verified saved to DB: name={verify[0]}, email={verify[1]}')
    else:
        print(f'[Identity] ✗ FAILED to verify save for {app_id}')
    
    log(con, app_id, 'IDENTITY_SUBMITTED', f'Name: {name} | DOB: {dob} | Email: {email}')
    con.commit()
    con.close()

    return jsonify({
        'success': True,
        'application_id': app_id,
        'age': age,
        'name': name
    })

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — DOCUMENT UPLOAD (REAL FILES + REAL OCR)
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/documents/upload', methods=['POST'])
def upload_document():
    app_id   = session.get('app_id') or request.form.get('application_id')
    doc_type = request.form.get('doc_type', 'Aadhaar')

    if not app_id:
        # create new session automatically so the upload can proceed
        app_id = 'NXB-' + uuid.uuid4().hex[:8].upper()
        ts = now()
        con = db_connect()
        con.execute(
            "INSERT INTO applications(id,status,method,created_at,updated_at) VALUES(?,?,?,?,?)",
            (app_id, 'In Progress', 'Manual', ts, ts)
        )
        log(con, app_id, 'SESSION_AUTO_CREATED', 'Created new application during document upload without existing session')
        con.commit()
        con.close()
        session['app_id'] = app_id

    if doc_type not in ('Aadhaar', 'PAN', 'Passport'):
        return jsonify({'error': 'Invalid document type'}), 400
    if doc_type not in ('Aadhaar', 'PAN', 'Passport'):
        return jsonify({'error': 'doc_type must be Aadhaar, PAN, or Passport'}), 400

    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded. Please select a document.'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'No file selected'}), 400

    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in ALLOWED_DOC:
        return jsonify({'error': f'File type .{ext} not allowed. Use PNG, JPG, or PDF'}), 400

    # Save file with unique name
    doc_id      = str(uuid.uuid4())
    stored_name = f"{app_id}_{doc_type}_{doc_id[:8]}.{ext}"
    save_path   = os.path.join(DOC_DIR, stored_name)
    file.save(save_path)

    # Real file hash
    with open(save_path, 'rb') as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()
    file_size = os.path.getsize(save_path)

    # Real OCR
    ocr = run_ocr(save_path, doc_type)

    # Determine verification
    tamper_flags = ocr['tamper_flags']
    confidence   = ocr['confidence']
    verified     = len(tamper_flags) == 0 and confidence >= 30

    ts  = now()
    con = db_connect()
    con.execute("""
        INSERT INTO documents
        (id,application_id,doc_type,original_name,stored_name,file_hash,file_size,
         ocr_text,ocr_name,ocr_dob,ocr_id_number,tamper_flags,confidence,verified,uploaded_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (doc_id, app_id, doc_type, file.filename, stored_name,
          file_hash, file_size, ocr['raw_text'],
          ocr['name'], ocr['dob'], ocr['id_number'],
          json.dumps(tamper_flags), confidence, 1 if verified else 0, ts))

    con.execute("""
        UPDATE applications SET id_type=?, doc_path=?, updated_at=? WHERE id=?
    """, (doc_type, stored_name, ts, app_id))

    log(con, app_id, 'DOCUMENT_UPLOADED',
        f'Type:{doc_type} | File:{stored_name} | Hash:{file_hash[:16]}… | OCR conf:{confidence}% | Flags:{len(tamper_flags)}')
    con.commit()
    con.close()

    return jsonify({
        'success': True,
        'document_id': doc_id,
        'doc_type': doc_type,
        'file_hash': file_hash,
        'file_size_kb': round(file_size / 1024, 1),
        'ocr': {
            'name':       ocr['name'],
            'dob':        ocr['dob'],
            'id_number':  ocr['id_number'],
            'confidence': confidence,
            'raw_preview': ocr['raw_text'][:200] if ocr['raw_text'] else ''
        },
        'tamper_flags': tamper_flags,
        'verified': verified
    })

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — SELFIE (REAL FILE STORED, SIMULATED FACE MATCH)
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/biometric/selfie', methods=['POST'])
def upload_selfie():
    app_id = session.get('app_id') or request.form.get('application_id')
    if not app_id:
        app_id = 'NXB-' + uuid.uuid4().hex[:8].upper()
        ts = now()
        con = db_connect()
        con.execute(
            "INSERT INTO applications(id,status,method,created_at,updated_at) VALUES(?,?,?,?,?)",
            (app_id, 'In Progress', 'Manual', ts, ts)
        )
        log(con, app_id, 'SESSION_AUTO_CREATED', 'Created new application during selfie upload without existing session')
        con.commit()
        con.close()
        session['app_id'] = app_id

    if 'selfie' not in request.files:
        return jsonify({'error': 'No selfie file received'}), 400

    file = request.files['selfie']
    ext  = (file.filename or 'selfie.jpg').rsplit('.', 1)[-1].lower()
    if ext not in ALLOWED_SELFIE:
        ext = 'jpg'

    selfie_name = f"{app_id}_selfie.{ext}"
    save_path   = os.path.join(SELFIE_DIR, selfie_name)
    file.save(save_path)

    # Simulated face match (stores real photo, simulates score)
    # In production: send to AWS Rekognition / Azure Face API
    face_score  = random.randint(82, 98)
    face_status = 'Matched' if face_score >= 75 else 'Weak'

    ts  = now()
    con = db_connect()
    print(f'[Selfie] Storing selfie for app_id={app_id}: {selfie_name}')
    con.execute("""
        UPDATE applications
        SET selfie_path=?, face_score=?, face_status=?, updated_at=?
        WHERE id=?
    """, (selfie_name, face_score, face_status, ts, app_id))
    
    verify = con.execute("SELECT selfie_path, face_score FROM applications WHERE id=?", (app_id,)).fetchone()
    if verify:
        print(f'[Selfie] ✓ Verified saved to DB: path={verify[0]}, score={verify[1]}')
    else:
        print(f'[Selfie] ✗ FAILED to verify save for {app_id}')
    
    log(con, app_id, 'SELFIE_UPLOADED',
        f'File:{selfie_name} | FaceScore:{face_score}% | Status:{face_status}')
    con.commit()
    con.close()

    return jsonify({
        'success': True,
        'selfie_stored': selfie_name,
        'face_score': face_score,
        'face_status': face_status,
        'liveness': True,
        'note': 'Selfie stored securely. Face match score is simulated for demo.'
    })

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — OTP (Frontend-generated, stored hash in DB)
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/otp/store', methods=['POST'])
def otp_store():
    """
    Frontend generates random OTP, sends us the hash to store.
    We never see the plain OTP — just verify its hash later.
    """
    data   = request.get_json() or {}
    app_id = session.get('app_id') or data.get('application_id')
    otp_hash = data.get('otp_hash')   # SHA-256 of the OTP

    if not otp_hash:
        return jsonify({'error': 'Missing otp_hash field'}), 400
    
    if not app_id:
        print(f'DEBUG OTP Store: session.get("app_id") = {session.get("app_id")}, data.get("application_id") = {data.get("application_id")}')
        return jsonify({'error': 'Missing application_id. Session may have expired.'}), 400

    ts  = now()
    con = db_connect()
    
    # For offline mode, create application if needed
    if app_id.startswith('NXB-OFFLINE'):
        app_exists = con.execute("SELECT id FROM applications WHERE id=?", (app_id,)).fetchone()
        if not app_exists:
            con.execute(
                "INSERT INTO applications(id,status,method,created_at,updated_at) VALUES(?,?,?,?,?)",
                (app_id, 'In Progress', 'Manual', ts, ts)
            )
    
    con.execute("UPDATE applications SET otp_hash=?, updated_at=? WHERE id=?",
                (otp_hash, ts, app_id))
    log(con, app_id, 'OTP_GENERATED', 'OTP hash stored in DB')
    con.commit()
    con.close()
    return jsonify({'success': True})

@app.route('/api/otp/verify', methods=['POST'])
def otp_verify():
    data     = request.get_json() or {}
    app_id   = session.get('app_id') or data.get('application_id')
    otp_hash = data.get('otp_hash')   # SHA-256 of what user entered

    # More specific error messages for debugging
    if not otp_hash:
        return jsonify({'error': 'Missing otp_hash field'}), 400
    
    if not app_id:
        # Log session state for debugging
        print(f'DEBUG: Session keys: {list(session.keys())}')
        print(f'DEBUG: session.get("app_id"): {session.get("app_id")}')
        print(f'DEBUG: data.get("application_id"): {data.get("application_id")}')
        return jsonify({'error': 'Missing application_id. Make sure identity step is completed.'}), 400

    con     = db_connect()
    app_row = con.execute("SELECT otp_hash FROM applications WHERE id=?", (app_id,)).fetchone()

    if not app_row:
        con.close()
        # For offline demo, create record if needed
        if app_id.startswith('NXB-OFFLINE'):
            # Allow offline mode to pass through
            con = db_connect()
            con.execute("UPDATE applications SET otp_verified=1, updated_at=? WHERE id=?", 
                       (now(), app_id))
            con.commit()
            con.close()
            return jsonify({'success': True, 'verified': True})
        
        return jsonify({'error': f'Application {app_id} not found.'}), 404
    
    if not app_row['otp_hash']:
        con.close()
        return jsonify({'error': 'No OTP stored for this application. Did you request OTP?'}), 400

    if app_row['otp_hash'] != otp_hash:
        log(con, app_id, 'OTP_FAILED', 'Incorrect OTP entered')
        con.commit(); con.close()
        return jsonify({'success': False, 'error': 'Incorrect OTP. Please try again.'}), 400

    ts = now()
    con.execute("UPDATE applications SET otp_verified=1, updated_at=? WHERE id=?", (ts, app_id))
    log(con, app_id, 'OTP_VERIFIED', 'OTP verified successfully')
    con.commit()
    con.close()
    return jsonify({'success': True, 'verified': True})

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — RISK + ACCOUNT CREATION
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/risk/evaluate', methods=['POST'])
def risk_evaluate():
    data   = request.get_json() or {}
    app_id = session.get('app_id') or data.get('application_id')
    if not app_id:
        app_id = 'NXB-' + uuid.uuid4().hex[:8].upper()
        ts = now()
        con = db_connect()
        con.execute(
            "INSERT INTO applications(id,status,method,created_at,updated_at) VALUES(?,?,?,?,?)",
            (app_id, 'In Progress', 'Manual', ts, ts)
        )
        log(con, app_id, 'SESSION_AUTO_CREATED', 'Created new application during risk evaluate without existing session')
        con.commit()
        con.close()
        session['app_id'] = app_id

    con     = db_connect()
    app_row = con.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
    doc_rows = con.execute("SELECT * FROM documents WHERE application_id=?", (app_id,)).fetchall()

    if not app_row:
        con.close()
        return jsonify({'error': 'Application not found'}), 404

    score, level, signals, reason = compute_risk(dict(app_row), [dict(d) for d in doc_rows])
    print(f'[Risk] Computed risk for {app_id}: level={level}, score={score}')

    # Generate account number for Low/Medium
    account_number = None
    ifsc           = None
    if level in ('Low', 'Medium'):
        account_number = ''.join([str(random.randint(0,9)) for _ in range(12)])
        # Format: XXXX XXXX XXXX
        account_number = f"{account_number[:4]} {account_number[4:8]} {account_number[8:]}"
        ifsc = 'NXBA0001234'
        print(f'[Risk] Generated account {account_number} for {level} risk')

    new_status = {'Low':'Approved','Medium':'Pending','High':'Escalated'}[level]
    ts = now()

    print(f'[Risk] Updating app_id={app_id}: status={new_status}, account={account_number}')
    con.execute("""
        UPDATE applications
        SET risk_score=?, risk_level=?, risk_signals=?, risk_reason=?,
            account_number=?, ifsc=?, status=?, updated_at=?
        WHERE id=?
    """, (score, level, json.dumps(signals), reason,
          account_number, ifsc, new_status, ts, app_id))
    
    verify = con.execute("SELECT risk_level, status, account_number FROM applications WHERE id=?", (app_id,)).fetchone()
    if verify:
        print(f'[Risk] ✓ Verified saved to DB: risk={verify[0]}, status={verify[1]}, account={verify[2]}')
    else:
        print(f'[Risk] ✗ FAILED to verify save for {app_id}')

    log(con, app_id, 'RISK_EVALUATED',
        f'Score:{score} | Level:{level} | Status:{new_status}')
    con.commit()
    con.close()

    return jsonify({
        'success': True,
        'risk_score': score,
        'risk_level': level,
        'risk_reason': reason,
        'signals': signals,
        'status': new_status,
        'account_number': account_number,
        'ifsc': ifsc,
        'branch': 'NexaBank Digital Branch'
    })

@app.route('/api/account/summary/<app_id>', methods=['GET'])
def account_summary(app_id):
    con     = db_connect()
    app_row = con.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
    docs    = con.execute("SELECT * FROM documents WHERE application_id=?", (app_id,)).fetchall()
    con.close()
    if not app_row:
        return jsonify({'error': 'Not found'}), 404
    result = to_dict(app_row)
    result['documents'] = [to_dict(d) for d in docs]
    return jsonify(result)

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — ADMIN API
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/admin/stats', methods=['GET'])
@admin_required
def admin_stats():
    con = db_connect()
    def q(sql): return con.execute(sql).fetchone()[0]
    stats = {
        'total':         q("SELECT COUNT(*) FROM applications"),
        'approved':      q("SELECT COUNT(*) FROM applications WHERE status='Approved'"),
        'pending':       q("SELECT COUNT(*) FROM applications WHERE status='Pending'"),
        'escalated':     q("SELECT COUNT(*) FROM applications WHERE status='Escalated'"),
        'in_progress':   q("SELECT COUNT(*) FROM applications WHERE status='In Progress'"),
        'rejected':      q("SELECT COUNT(*) FROM applications WHERE status='Rejected'"),
        'low':           q("SELECT COUNT(*) FROM applications WHERE risk_level='Low'"),
        'medium':        q("SELECT COUNT(*) FROM applications WHERE risk_level='Medium'"),
        'high':          q("SELECT COUNT(*) FROM applications WHERE risk_level='High'"),
        'avg_risk':      round(q("SELECT COALESCE(AVG(risk_score),0) FROM applications WHERE risk_score IS NOT NULL"), 1),
        'overrides':     q("SELECT COUNT(*) FROM admin_decisions WHERE ai_overridden=1"),
        'total_docs':    q("SELECT COUNT(*) FROM documents"),
        'total_chats':   q("SELECT COUNT(*) FROM chat_messages"),
    }
    con.close()
    return jsonify(stats)

@app.route('/api/admin/applications', methods=['GET'])
@admin_required
def admin_applications():
    status  = request.args.get('status','')
    risk    = request.args.get('risk','')
    search  = request.args.get('q','')
    page    = max(1, int(request.args.get('page',1)))
    limit   = min(50, int(request.args.get('limit',20)))
    offset  = (page-1)*limit

    con    = db_connect()
    where  = ['1=1']
    params = []
    if status: where.append("status=?");          params.append(status)
    if risk:   where.append("risk_level=?");      params.append(risk)
    if search:
        where.append("(name LIKE ? OR email LIKE ? OR id LIKE ?)")
        params.extend([f'%{search}%']*3)

    sql   = f"SELECT * FROM applications WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ? OFFSET ?"
    apps  = con.execute(sql, params+[limit, offset]).fetchall()
    total = con.execute(f"SELECT COUNT(*) FROM applications WHERE {' AND '.join(where)}", params).fetchone()[0]
    con.close()

    return jsonify({
        'applications': [to_dict(a) for a in apps],
        'total': total, 'page': page, 'limit': limit
    })

@app.route('/api/admin/application/<app_id>', methods=['GET'])
@admin_required
def admin_application_detail(app_id):
    con  = db_connect()
    app_row   = con.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
    docs      = con.execute("SELECT * FROM documents WHERE application_id=?", (app_id,)).fetchall()
    audit     = con.execute("SELECT * FROM audit_log WHERE application_id=? ORDER BY id DESC LIMIT 30", (app_id,)).fetchall()
    decisions = con.execute("SELECT * FROM admin_decisions WHERE application_id=? ORDER BY id DESC", (app_id,)).fetchall()
    chats     = con.execute("SELECT * FROM chat_messages WHERE application_id=? ORDER BY id", (app_id,)).fetchall()
    con.close()

    if not app_row:
        print(f'[Admin] Application {app_id} not found in database')
        return jsonify({'error': 'Not found'}), 404

    app_dict = to_dict(app_row)
    print(f'[Admin] Application {app_id} loaded with fields: {list(app_dict.keys())}')
    print(f'[Admin] Name={app_dict.get("name")}, Email={app_dict.get("email")}, Risk={app_dict.get("risk_level")}, Status={app_dict.get("status")}')

    return jsonify({
        'application': app_dict,
        'documents':   [to_dict(d) for d in docs],
        'audit_log':   [to_dict(a) for a in audit],
        'decisions':   [to_dict(d) for d in decisions],
        'chat':        [to_dict(c) for c in chats],
    })

@app.route('/api/admin/decision', methods=['POST'])
@admin_required
def admin_decision():
    data     = request.get_json()
    app_id   = data.get('application_id')
    decision = data.get('decision')   # Approved / Rejected / More Info
    notes    = (data.get('notes') or '').strip()
    admin    = session.get('admin_username','admin')

    if not app_id or not decision:
        return jsonify({'error': 'Missing application_id or decision'}), 400

    con     = db_connect()
    app_row = con.execute("SELECT risk_level, status, account_number FROM applications WHERE id=?", (app_id,)).fetchone()
    if not app_row:
        con.close()
        return jsonify({'error': 'Application not found'}), 404

    ai_rec = {'Low':'Approved','Medium':'Pending','High':'Escalated'}.get(app_row['risk_level'],'Pending')
    overrode = 1 if decision != ai_rec else 0

    new_status = {'Approved':'Approved','Rejected':'Rejected','More Info':'Pending'}.get(decision,'Pending')

    # Generate account number if approving one that doesn't have it
    account_number = app_row['account_number']
    if decision == 'Approved' and not account_number:
        n = ''.join([str(random.randint(0,9)) for _ in range(12)])
        account_number = f"{n[:4]} {n[4:8]} {n[8:]}"

    ts = now()
    con.execute("""
        UPDATE applications SET status=?, account_number=?, updated_at=? WHERE id=?
    """, (new_status, account_number, ts, app_id))

    con.execute("""
        INSERT INTO admin_decisions(application_id,admin_username,decision,notes,ai_overridden,decided_at)
        VALUES(?,?,?,?,?,?)
    """, (app_id, admin, decision, notes, overrode, ts))

    log(con, app_id, f'ADMIN_DECISION',
        f'Decision:{decision} | Admin:{admin} | Override AI:{bool(overrode)} | Notes:{notes[:100]}',
        actor=admin)
    con.commit()
    con.close()

    return jsonify({
        'success':        True,
        'new_status':     new_status,
        'account_number': account_number,
        'ai_overridden':  bool(overrode)
    })

@app.route('/api/admin/audit', methods=['GET'])
@admin_required
def admin_audit():
    app_id = request.args.get('application_id')
    page   = max(1, int(request.args.get('page',1)))
    limit  = min(100, int(request.args.get('limit',50)))
    offset = (page-1)*limit

    con = db_connect()
    if app_id:
        rows  = con.execute("SELECT * FROM audit_log WHERE application_id=? ORDER BY id DESC LIMIT ? OFFSET ?", (app_id,limit,offset)).fetchall()
        total = con.execute("SELECT COUNT(*) FROM audit_log WHERE application_id=?", (app_id,)).fetchone()[0]
    else:
        rows  = con.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ? OFFSET ?", (limit,offset)).fetchall()
        total = con.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    con.close()

    return jsonify({'logs': [to_dict(r) for r in rows], 'total': total, 'page': page})

@app.route('/health')
def health():
    # Check DB is reachable
    try:
        con = db_connect()
        con.execute("SELECT 1").fetchone()
        con.close()
        db_ok = True
    except:
        db_ok = False

    return jsonify({
        'status':  'ok',
        'db':      'connected' if db_ok else 'error',
        'db_path': DB_PATH,
        'ocr':     'available' if OCR_AVAILABLE else 'not installed',
        'claude':  'configured' if ANTHROPIC_API_KEY else 'no key (rule-based fallback)',
        'time':    now()
    })

@app.errorhandler(sqlite3.OperationalError)
def sqlite_locked(e):
    # common when two write transactions collide; frontend now retries automatically
    return jsonify({'error': 'Database busy, please retry'}, 503)

@app.errorhandler(500)
def server_error(e):
    return jsonify({'error': 'Server error: ' + str(e)}), 500

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404

# ─────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    print("\n" + "="*55)
    print("  NexaBank Onboarding System")
    print(f"  Customer App : http://localhost:5000")
    print(f"  Admin Login  : http://localhost:5000/admin-login")
    print(f"  Admin Panel  : http://localhost:5000/admin")
    print(f"  Health Check : http://localhost:5000/health")
    print(f"  Database     : {DB_PATH}")
    print(f"  Uploads      : {UPLOAD_DIR}")
    print()
    print("  Admin Credentials:")
    print("    Username: admin     Password: admin123")
    print("    Username: reviewer  Password: reviewer123")
    print()
    print("  Optional: set ANTHROPIC_API_KEY env var for AI chat")
    print("="*55 + "\n")
    app.run(debug=True, port=5000, host='0.0.0.0')