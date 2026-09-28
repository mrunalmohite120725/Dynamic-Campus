"""
app.py — Dynamic Campus Flask Backend
Run: python app.py
"""
import os
import sys
from datetime import datetime, time as dtime, timedelta
from functools import wraps

from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit, join_room
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity, get_jwt
)
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import Config
from db import get_connection

# AI/ML Imports
try:
    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity
    from sklearn.preprocessing import MultiLabelBinarizer
except ImportError:
    np = None
    cosine_similarity = None
    MultiLabelBinarizer = None

# ── App setup ────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="frontend", static_url_path="")
app.config["SECRET_KEY"]          = Config.SECRET_KEY
app.config["JWT_SECRET_KEY"]      = Config.JWT_SECRET_KEY
app.config["UPLOAD_FOLDER"]       = Config.UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"]  = 16 * 1024 * 1024   # 16 MB
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(days=7)

CORS(app, origins="*")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
jwt      = JWTManager(app)

os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)

# ── Helpers ──────────────────────────────────────────────────────────────────

def now_time() -> str:
    """Current time as HH:MM string (for SQL TIME comparisons)."""
    return datetime.now().strftime("%H:%M")

def today() -> str:
    """Current weekday name capitalised, e.g. 'Monday'."""
    return datetime.now().strftime("%A")

def require_role(*roles):
    """Decorator: JWT required + role check."""
    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapper(*args, **kwargs):
            claims = get_jwt()
            if claims.get("role") not in roles:
                return jsonify({"error": "Forbidden"}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator

def db_query(sql, params=(), one=False):
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(sql, params)
    result = cursor.fetchone() if one else cursor.fetchall()
    cursor.close()
    conn.close()
    return result

def db_execute(sql, params=()):
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    last_id = cursor.lastrowid
    conn.commit()
    cursor.close()
    conn.close()
    return last_id

def cleanup_extra_lectures():
    """Delete one-time extra lectures from the extra_lectures table that have already passed."""
    try:
        from datetime import datetime
        now_dt = datetime.now()
        today_str = now_dt.strftime('%Y-%m-%d')
        now_t = now_dt.strftime('%H:%M:%S')
        
        # 1. Delete past dates
        db_execute("DELETE FROM extra_lectures WHERE date IS NOT NULL AND date < %s", (today_str,))
        
        # 2. Delete finished lectures from today
        db_execute("DELETE FROM extra_lectures WHERE date IS NOT NULL AND date = %s AND end_time <= %s", (today_str, now_t))
    except Exception as e:
        print(f"Cleanup error: {e}")

# ── Serve Frontend ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("frontend", "index.html")

@app.route("/<path:path>")
def static_files(path):
    return send_from_directory("frontend", path)

# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API — No authentication required
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/classes")
def get_classes():
    """Return all classes for the homepage dropdown."""
    rows = db_query("SELECT cid, class_name, class_room_no, sem FROM classes ORDER BY sem, class_name")
    return jsonify(rows)

@app.route("/api/batches")
def get_batches():
    """Return distinct batches for a given cid."""
    cid = request.args.get("cid", type=int)
    if not cid:
        return jsonify([])
    rows = db_query(
        "SELECT DISTINCT batch FROM timetable WHERE cid=%s AND batch IS NOT NULL ORDER BY batch",
        (cid,)
    )
    return jsonify([r["batch"] for r in rows])

@app.route("/api/timetable/student")
def student_timetable():
    """Full weekly timetable for a given class + optional batch (public)."""
    cleanup_extra_lectures()
    cid   = request.args.get("cid", type=int)
    batch = request.args.get("batch", "")
    if not cid:
        return jsonify({"error": "cid required"}), 400

    # We UNION the regular timetable with the approved/temporary extra lectures
    # We add a virtual 'is_extra' column to distinguish them
    
    if batch:
        sql = """
            SELECT t.day, t.start_time, t.end_time, t.batch, t.room, 0 as is_extra,
                   s.sname, tr.tname
            FROM timetable t
            JOIN subjects  s  ON t.sid = s.sid
            LEFT JOIN teachers tr ON t.tid = tr.tid
            WHERE t.cid = %s AND (t.batch IS NULL OR t.batch = %s)
            
            UNION ALL
            
            SELECT e.day, e.start_time, e.end_time, e.batch, e.room, 1 as is_extra,
                   s.sname, tr.tname
            FROM extra_lectures e
            JOIN subjects  s  ON e.sid = s.sid
            LEFT JOIN teachers tr ON e.tid = tr.tid
            WHERE e.cid = %s AND (e.batch IS NULL OR e.batch = %s) AND e.status = 'approved'
            
            ORDER BY FIELD(day,'Monday','Tuesday','Wednesday','Thursday','Friday'),
                     start_time
        """
        rows = db_query(sql, (cid, batch, cid, batch))
    else:
        sql = """
            SELECT t.day, t.start_time, t.end_time, t.batch, t.room, 0 as is_extra,
                   s.sname, tr.tname
            FROM timetable t
            JOIN subjects  s  ON t.sid = s.sid
            LEFT JOIN teachers tr ON t.tid = tr.tid
            WHERE t.cid = %s
            
            UNION ALL
            
            SELECT e.day, e.start_time, e.end_time, e.batch, e.room, 1 as is_extra,
                   s.sname, tr.tname
            FROM extra_lectures e
            JOIN subjects  s  ON e.sid = s.sid
            LEFT JOIN teachers tr ON e.tid = tr.tid
            WHERE e.cid = %s AND e.status = 'approved'
            
            ORDER BY FIELD(day,'Monday','Tuesday','Wednesday','Thursday','Friday'),
                     start_time
        """
        rows = db_query(sql, (cid, cid))

    # Convert timedelta (MySQL TIME) to string
    for r in rows:
        for key in ("start_time", "end_time"):
            if hasattr(r[key], "seconds"):
                total = int(r[key].total_seconds())
                r[key] = f"{total//3600:02d}:{(total%3600)//60:02d}"
            else:
                r[key] = str(r[key])
    return jsonify(rows)

@app.route("/api/timetable/now")
def current_lecture():
    """Currently running lecture for a class+batch."""
    cleanup_extra_lectures()
    cid   = request.args.get("cid", type=int)
    batch = request.args.get("batch", "")
    day   = today()
    now   = now_time()

    sql = """
        SELECT start_time, end_time, batch, room, is_extra, sname, tname
        FROM (
            SELECT t.start_time, t.end_time, t.batch, t.room, 0 as is_extra,
                   s.sname, tr.tname
            FROM timetable t
            JOIN subjects  s  ON t.sid = s.sid
            LEFT JOIN teachers tr ON t.tid = tr.tid
            WHERE t.cid=%s AND t.day=%s
            
            UNION ALL
            
            SELECT e.start_time, e.end_time, e.batch, e.room, 1 as is_extra,
                   s.sname, tr.tname
            FROM extra_lectures e
            JOIN subjects  s  ON e.sid = s.sid
            LEFT JOIN teachers tr ON e.tid = tr.tid
            WHERE e.cid=%s AND e.day=%s AND e.status = 'approved'
        ) AS combined
        WHERE start_time <= %s AND end_time > %s
          AND (batch IS NULL OR batch = %s)
        LIMIT 1
    """
    row = db_query(sql, (cid, day, cid, day, now, now, batch), one=True)
    if row:
        for key in ("start_time", "end_time"):
            if hasattr(row[key], "seconds"):
                total = int(row[key].total_seconds())
                row[key] = f"{total//3600:02d}:{(total%3600)//60:02d}"
            else:
                row[key] = str(row[key])
    return jsonify(row or {})

@app.route("/api/timetable/next")
def next_lecture():
    """Next upcoming lecture for a class+batch today."""
    cid   = request.args.get("cid", type=int)
    batch = request.args.get("batch", "")
    day   = today()
    now   = now_time()

    sql = """
        SELECT start_time, end_time, batch, room, is_extra, sname, tname
        FROM (
            SELECT t.start_time, t.end_time, t.batch, t.room, 0 as is_extra,
                   s.sname, tr.tname
            FROM timetable t
            JOIN subjects  s  ON t.sid = s.sid
            LEFT JOIN teachers tr ON t.tid = tr.tid
            WHERE t.cid=%s AND t.day=%s
            
            UNION ALL
            
            SELECT e.start_time, e.end_time, e.batch, e.room, 1 as is_extra,
                   s.sname, tr.tname
            FROM extra_lectures e
            JOIN subjects  s  ON e.sid = s.sid
            LEFT JOIN teachers tr ON e.tid = tr.tid
            WHERE e.cid=%s AND e.day=%s AND e.status = 'approved'
        ) AS combined
        WHERE start_time > %s
          AND (batch IS NULL OR batch = %s)
        ORDER BY start_time LIMIT 1
    """
    row = db_query(sql, (cid, day, cid, day, now, batch), one=True)
    if row:
        for key in ("start_time", "end_time"):
            if hasattr(row[key], "seconds"):
                total = int(row[key].total_seconds())
                row[key] = f"{total//3600:02d}:{(total%3600)//60:02d}"
            else:
                row[key] = str(row[key])
    return jsonify(row or {})

@app.route("/api/classrooms")
def classrooms_status():
    """Real-time occupancy of all classrooms."""
    day = today()
    now = now_time()

    # All distinct rooms in timetable
    all_rooms = db_query(
        "SELECT DISTINCT room FROM timetable WHERE room IS NOT NULL ORDER BY room"
    )

    # Currently active lectures per room
    active = db_query("""
        SELECT room, sname, tname, class_name, start_time, end_time
        FROM (
            SELECT t.room, s.sname, tr.tname,
                   CONCAT(cl.class_name, ' ', cl.class_room_no) AS class_name,
                   t.start_time, t.end_time
            FROM timetable t
            JOIN subjects  s  ON t.sid = s.sid
            JOIN classes   cl ON t.cid = cl.cid
            LEFT JOIN teachers tr ON t.tid = tr.tid
            WHERE t.day=%s
            
            UNION ALL
            
            SELECT e.room, s.sname, tr.tname,
                   CONCAT(cl.class_name, ' ', cl.class_room_no) AS class_name,
                   e.start_time, e.end_time
            FROM extra_lectures e
            JOIN subjects  s  ON e.sid = s.sid
            JOIN classes   cl ON e.cid = cl.cid
            LEFT JOIN teachers tr ON e.tid = tr.tid
            WHERE e.day=%s AND e.status = 'approved'
        ) AS combined
        WHERE start_time <= %s AND end_time > %s
          AND room IS NOT NULL
    """, (day, day, now, now))

    active_map = {}
    for a in active:
        for key in ("start_time", "end_time"):
            if hasattr(a[key], "seconds"):
                total = int(a[key].total_seconds())
                a[key] = f"{total//3600:02d}:{(total%3600)//60:02d}"
            else:
                a[key] = str(a[key])
        active_map[a["room"]] = a

    result = []
    for r in all_rooms:
        room = r["room"]
        if room in active_map:
            info = active_map[room]
            result.append({
                "room":       room,
                "status":     "occupied",
                "subject":    info["sname"],
                "teacher":    info["tname"],
                "class":      info["class_name"],
                "start_time": info["start_time"],
                "end_time":   info["end_time"],
            })
        else:
            result.append({"room": room, "status": "free"})

    return jsonify(result)

@app.route("/api/classrooms/free")
def free_classrooms():
    """Return a list of rooms that are free during the specified time slot."""
    day = request.args.get("day")
    start_time = request.args.get("start_time")
    end_time = request.args.get("end_time")

    if not all([day, start_time, end_time]):
        return jsonify({"error": "Missing parameters"}), 400

    # 1. Get all distinct rooms
    all_rooms_res = db_query("SELECT DISTINCT room FROM timetable WHERE room IS NOT NULL AND room != '' ORDER BY room")
    all_rooms = [r["room"] for r in all_rooms_res]

    # 2. Get rooms occupied during the overlap
    # Overlap condition: existing_start < requested_end AND existing_end > requested_start
    occupied_res = db_query("""
        SELECT DISTINCT room FROM timetable 
        WHERE day = %s 
          AND start_time < %s 
          AND end_time > %s
          AND room IS NOT NULL AND room != ''
    """, (day, end_time, start_time))
    
    occupied_rooms = set(r["room"] for r in occupied_res)

    # 3. Free rooms = all - occupied
    free_rooms = [r for r in all_rooms if r not in occupied_rooms]
    return jsonify({"free_rooms": free_rooms})

# ═══════════════════════════════════════════════════════════════════════════════
# AUTH — Teacher + Admin login
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/login", methods=["POST"])
def login():
    data     = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    user = db_query("SELECT * FROM users WHERE username=%s", (username,), one=True)
    if not user or not check_password_hash(user["password"], password):
        return jsonify({"error": "Invalid credentials"}), 401

    # Verify teacher status
    if user["role"] == "teacher" and user["tid"]:
        teacher = db_query("SELECT status FROM teachers WHERE tid=%s", (user["tid"],), one=True)
        if teacher:
            status = teacher.get("status", "pending")
            if status == "pending":
                return jsonify({"error": "Your account is pending admin approval."}), 403
            elif status == "rejected":
                return jsonify({"error": "Your account verification has been rejected by the administrator."}), 403

    student_id = user.get("student_id")
    # flask-jwt-extended v4+ requires string identity; extra data goes in additional_claims
    token = create_access_token(
        identity=str(user["uid"]),
        additional_claims={"role": user["role"], "tid": user["tid"], "student_id": student_id, "username": user["username"]}
    )
    return jsonify({"token": token, "role": user["role"], "uid": user["uid"],
                    "tid": user["tid"], "student_id": student_id, "username": user["username"]})

@app.route("/api/me")
@jwt_required()
def me():
    claims = get_jwt()
    return jsonify({"uid": get_jwt_identity(), "role": claims.get("role"),
                    "tid": claims.get("tid"), "student_id": claims.get("student_id"), "username": claims.get("username")})

# ── Teacher self-registration (public) ────────────────────────────────────────

@app.route("/api/register", methods=["POST"])
def register_teacher():
    """Public endpoint: teachers create their own account."""
    data     = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    tid      = data.get("tid")  # optional link to teacher record
    
    # Optional profile details
    tname = data.get("tname", "").strip()
    department = data.get("department", "").strip()
    cabin_no = data.get("cabin_no", "").strip()
    email = data.get("email", "").strip()
    phone = data.get("phone", "").strip()

    if not username or not password:
        return jsonify({"error": "username and password required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    existing = db_query("SELECT uid FROM users WHERE username=%s", (username,), one=True)
    if existing:
        return jsonify({"error": "Username already taken. Choose another."}), 409

    hashed = generate_password_hash(password)
    try:
        if tid:
            # Link to existing profile and set status to pending for approval
            db_execute(
                "UPDATE teachers SET status='pending', department=%s, cabin_no=%s, email=%s, phone=%s WHERE tid=%s",
                (department or None, cabin_no or None, email or None, phone or None, tid)
            )
        else:
            if not tname:
                return jsonify({"error": "Teacher name required to create a new profile."}), 400
            # Create a new teacher profile
            tid = db_execute(
                "INSERT INTO teachers (tname, department, cabin_no, email, phone, status) VALUES (%s, %s, %s, %s, %s, 'pending')",
                (tname, department or None, cabin_no or None, email or None, phone or None)
            )
            
        uid = db_execute(
            "INSERT INTO users (username, password, role, tid) VALUES (%s,%s,'teacher',%s)",
            (username, hashed, tid)
        )
        return jsonify({"success": True, "uid": uid, "tid": tid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ═══════════════════════════════════════════════════════════════════════════════
# TEACHER API (JWT protected)
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/timetable/teacher")
@require_role("teacher", "admin")
def teacher_timetable():
    cleanup_extra_lectures()
    claims = get_jwt()
    tid = request.args.get("tid", type=int) or claims.get("tid")
    if not tid:
        return jsonify({"error": "tid required"}), 400

    sql = """
        SELECT day, start_time, end_time, batch, room, is_extra, sname, class_name, sid, cid
        FROM (
            SELECT t.day, t.start_time, t.end_time, t.batch, t.room, 0 as is_extra,
                   s.sname, CONCAT(cl.class_name, ' ', cl.class_room_no) AS class_name,
                   t.sid, t.cid
            FROM timetable t
            JOIN subjects s ON t.sid = s.sid
            JOIN classes cl ON t.cid = cl.cid
            WHERE t.tid = %s
            
            UNION ALL
            
            SELECT e.day, e.start_time, e.end_time, e.batch, e.room, 1 as is_extra,
                   s.sname, CONCAT(cl.class_name, ' ', cl.class_room_no) AS class_name,
                   e.sid, e.cid
            FROM extra_lectures e
            JOIN subjects s ON e.sid = s.sid
            JOIN classes cl ON e.cid = cl.cid
            WHERE e.tid = %s AND e.status = 'approved'
        ) AS combined
        ORDER BY FIELD(day,'Monday','Tuesday','Wednesday','Thursday','Friday'),
                 start_time
    """
    rows = db_query(sql, (tid, tid))
    for r in rows:
        for key in ("start_time", "end_time"):
            if hasattr(r[key], "seconds"):
                total = int(r[key].total_seconds())
                r[key] = f"{total//3600:02d}:{(total%3600)//60:02d}"
            else:
                r[key] = str(r[key])
    return jsonify(rows)

@app.route("/api/timetable/teacher/now")
@require_role("teacher", "admin")
def teacher_now():
    claims = get_jwt()
    tid = request.args.get("tid", type=int) or claims.get("tid")
    day = today()
    now = now_time()

    sql = """
        SELECT start_time, end_time, batch, room, is_extra, sname, class_name
        FROM (
            SELECT t.start_time, t.end_time, t.batch, t.room, 0 as is_extra,
                   s.sname, CONCAT(cl.class_name, ' ', cl.class_room_no) AS class_name
            FROM timetable t
            JOIN subjects s ON t.sid = s.sid
            JOIN classes cl ON t.cid = cl.cid
            WHERE t.tid=%s AND t.day=%s
            
            UNION ALL
            
            SELECT e.start_time, e.end_time, e.batch, e.room, 1 as is_extra,
                   s.sname, CONCAT(cl.class_name, ' ', cl.class_room_no) AS class_name
            FROM extra_lectures e
            JOIN subjects s ON e.sid = s.sid
            JOIN classes cl ON e.cid = cl.cid
            WHERE e.tid=%s AND e.day=%s AND e.status='approved'
        ) AS combined
        WHERE start_time <= %s AND end_time > %s
        LIMIT 1
    """
    row = db_query(sql, (tid, day, tid, day, now, now), one=True)
    if row:
        for key in ("start_time", "end_time"):
            if hasattr(row[key], "seconds"):
                total = int(row[key].total_seconds())
                row[key] = f"{total//3600:02d}:{(total%3600)//60:02d}"
            else:
                row[key] = str(row[key])
    return jsonify(row or {})

@app.route("/api/timetable/teacher/next")
@require_role("teacher", "admin")
def teacher_next():
    claims = get_jwt()
    tid = request.args.get("tid", type=int) or claims.get("tid")
    day = today()
    now = now_time()

    sql = """
        SELECT start_time, end_time, batch, room, sname, class_name
        FROM (
            SELECT t.start_time, t.end_time, t.batch, t.room,
                   s.sname, CONCAT(cl.class_name, ' ', cl.class_room_no) AS class_name
            FROM timetable t
            JOIN subjects s ON t.sid = s.sid
            JOIN classes cl ON t.cid = cl.cid
            WHERE t.tid=%s AND t.day=%s
            
            UNION ALL
            
            SELECT e.start_time, e.end_time, e.batch, e.room,
                   s.sname, CONCAT(cl.class_name, ' ', cl.class_room_no) AS class_name
            FROM extra_lectures e
            JOIN subjects s ON e.sid = s.sid
            JOIN classes cl ON e.cid = cl.cid
            WHERE e.tid=%s AND e.day=%s AND e.status='approved'
        ) AS combined
        WHERE start_time > %s
        ORDER BY start_time LIMIT 1
    """
    row = db_query(sql, (tid, day, tid, day, now), one=True)
    if row:
        for key in ("start_time", "end_time"):
            if hasattr(row[key], "seconds"):
                total = int(row[key].total_seconds())
                row[key] = f"{total//3600:02d}:{(total%3600)//60:02d}"
            else:
                row[key] = str(row[key])
    return jsonify(row or {})

# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN API (JWT protected)
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/upload", methods=["POST"])
@require_role("admin")
def upload_pdf():
    """Upload timetable PDF → run full pipeline → return result."""
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400

    f    = request.files["file"]
    cid  = request.form.get("cid",  1,        type=int)
    sem  = request.form.get("sem",  5,        type=int)
    year = request.form.get("year", "2025-26")

    filename = secure_filename(f.filename)
    pdf_path = os.path.join(Config.UPLOAD_FOLDER, filename)
    f.save(pdf_path)

    try:
        from parsers.nanonets_docstrange import extract_json
        extract_json(pdf_path, Config.JSON_OUTPUT)

        from parsers.json_to_db import parse_and_store
        parse_and_store(json_path=Config.JSON_OUTPUT, cid=cid, sem=sem, academic_year=year)

        # Broadcast update to all connected clients
        socketio.emit("timetable_updated", {"cid": cid, "sem": sem})
        return jsonify({"success": True, "message": "Timetable uploaded and processed."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/users", methods=["POST"])
@require_role("admin")
def create_user():
    """Admin creates another admin account only (teachers self-register)."""
    data     = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        return jsonify({"error": "username and password required"}), 400

    existing = db_query("SELECT uid FROM users WHERE username=%s", (username,), one=True)
    if existing:
        return jsonify({"error": "Username already taken."}), 409

    hashed = generate_password_hash(password)
    try:
        uid = db_execute(
            "INSERT INTO users (username, password, role, tid) VALUES (%s,%s,'admin',NULL)",
            (username, hashed)
        )
        return jsonify({"success": True, "uid": uid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/subjects")
def get_subjects():
    """Public: all subjects in the database."""
    rows = db_query("SELECT sid, sname FROM subjects ORDER BY sname")
    return jsonify(rows)

@app.route("/api/teachers")
def get_teachers():
    rows = db_query("SELECT tid, tname FROM teachers ORDER BY tname")
    return jsonify(rows)

@app.route("/api/teacher-status")
def public_teacher_status():
    """Public endpoint to check if a specific teacher is currently in a lecture."""
    tid = request.args.get("tid", type=int)
    if not tid:
        return jsonify({"error": "tid required"}), 400

    day = today()
    now = now_time()

    sql = """
        SELECT start_time, end_time, room, sname, class_name
        FROM (
            SELECT t.start_time, t.end_time, t.room, s.sname,
                   CONCAT(cl.class_name, ' ', cl.class_room_no) AS class_name
            FROM timetable t
            JOIN subjects s ON t.sid = s.sid
            JOIN classes cl ON t.cid = cl.cid
            WHERE t.tid = %s AND t.day = %s
            
            UNION ALL
            
            SELECT e.start_time, e.end_time, e.room, s.sname,
                   CONCAT(cl.class_name, ' ', cl.class_room_no) AS class_name
            FROM extra_lectures e
            JOIN subjects s ON e.sid = s.sid
            JOIN classes cl ON e.cid = cl.cid
            WHERE e.tid = %s AND e.day = %s AND e.status = 'approved'
        ) AS combined
        WHERE start_time <= %s AND end_time > %s
        LIMIT 1
    """
    current_lec = db_query(sql, (tid, day, tid, day, now, now), one=True)
    
    if current_lec:
        for key in ("start_time", "end_time"):
            if hasattr(current_lec[key], "seconds"):
                total = int(current_lec[key].total_seconds())
                current_lec[key] = f"{total//3600:02d}:{(total%3600)//60:02d}"
            else:
                current_lec[key] = str(current_lec[key])

    return jsonify({"current": current_lec})

@app.route("/api/notifications", methods=["POST"])
@require_role("teacher", "admin")
def broadcast_notification():
    data    = request.get_json()
    message = data.get("message", "")
    target_cid = data.get("target_cid")
    target_batch = data.get("target_batch") or None
    ntype   = data.get("type", "info")

    nid = db_execute(
        "INSERT INTO notifications (message, target_cid, target_batch, type) VALUES (%s,%s,%s,%s)",
        (message, target_cid, target_batch, ntype)
    )
    socketio.emit("new_notification", {"nid": nid, "message": message, "type": ntype, "target_cid": target_cid, "target_batch": target_batch})
    return jsonify({"success": True, "nid": nid})

@app.route("/api/extra-lectures")
@require_role("admin")
def get_extra_lectures():
    rows = db_query("""
        SELECT el.eid, el.day, el.start_time, el.end_time, el.room, el.status, el.reason,
               s.sname, t.tname,
               CONCAT(cl.class_name,' ',cl.class_room_no) AS class_name
        FROM extra_lectures el
        JOIN subjects  s  ON el.sid = s.sid
        JOIN teachers  t  ON el.tid = t.tid
        JOIN classes   cl ON el.cid = cl.cid
        ORDER BY el.requested_at DESC
    """)
    for r in rows:
        for key in ("start_time","end_time"):
            if hasattr(r[key],"seconds"):
                total = int(r[key].total_seconds())
                r[key] = f"{total//3600:02d}:{(total%3600)//60:02d}"
            else:
                r[key] = str(r[key])
    return jsonify(rows)

@app.route("/api/extra-lecture/<int:eid>/approve", methods=["PUT"])
@require_role("admin")
def approve_extra(eid):
    db_execute("UPDATE extra_lectures SET status='approved', decided_at=NOW() WHERE eid=%s", (eid,))
    socketio.emit("new_notification", {"message": "An extra lecture has been approved.", "type": "extra"})
    return jsonify({"success": True})

@app.route("/api/extra-lecture/<int:eid>/reject", methods=["PUT"])
@require_role("admin")
def reject_extra(eid):
    db_execute("UPDATE extra_lectures SET status='rejected', decided_at=NOW() WHERE eid=%s", (eid,))
    return jsonify({"success": True})

@app.route("/api/extra-lecture/check", methods=["GET"])
@require_role("teacher", "admin")
def check_extra_conflict():
    cid   = request.args.get("cid")
    batch = request.args.get("batch") or None
    day   = request.args.get("day")
    start = request.args.get("start_time")
    end   = request.args.get("end_time")

    if not all([cid, day, start, end]):
        return jsonify({"error": "Missing parameters"}), 400

    # 1. Check for conflicts
    if batch:
        conflict_query = """
            SELECT sid, batch FROM timetable 
            WHERE cid=%s AND day=%s AND start_time < %s AND end_time > %s
              AND (batch IS NULL OR batch=%s)
            UNION
            SELECT sid, batch FROM extra_lectures
            WHERE cid=%s AND day=%s AND start_time < %s AND end_time > %s AND status='approved'
              AND (batch IS NULL OR batch=%s)
            LIMIT 1
        """
        conflict = db_query(conflict_query, (cid, day, end, start, batch, cid, day, end, start, batch), one=True)
    else:
        conflict_query = """
            SELECT sid, batch FROM timetable 
            WHERE cid=%s AND day=%s AND start_time < %s AND end_time > %s
            UNION
            SELECT sid, batch FROM extra_lectures
            WHERE cid=%s AND day=%s AND start_time < %s AND end_time > %s AND status='approved'
            LIMIT 1
        """
        conflict = db_query(conflict_query, (cid, day, end, start, cid, day, end, start), one=True)

    if conflict:
        return jsonify({
            "class_busy": True,
            "message": "Class has lecture scheduled",
            "free_rooms": []
        })

    # 2. If no conflict, get free rooms
    all_rooms_res = db_query("SELECT DISTINCT room FROM timetable WHERE room IS NOT NULL AND room != '' ORDER BY room")
    all_rooms = [r["room"] for r in all_rooms_res]

    occupied_res = db_query("""
        SELECT DISTINCT room FROM timetable 
        WHERE day = %s AND start_time < %s AND end_time > %s
          AND room IS NOT NULL AND room != ''
    """, (day, end, start))
    occupied_rooms = set(r["room"] for r in occupied_res)

    free_rooms = [r for r in all_rooms if r not in occupied_rooms]

    return jsonify({
        "class_busy": False,
        "message": "Class is free",
        "free_rooms": free_rooms
    })

@app.route("/api/extra-lecture/request", methods=["POST"])
@require_role("teacher", "admin")
def request_extra():
    claims = get_jwt()
    data   = request.get_json() or {}
    
    # If Admin is assigning, use the provided tid; otherwise use the logged-in teacher's tid
    tid = data.get("tid") if claims.get("role") == "admin" else claims.get("tid")
    
    sid    = data.get("sid")
    cid    = data.get("cid")
    day    = data.get("day")
    st     = data.get("start_time")
    et     = data.get("end_time")
    room   = data.get("room","")
    reason = data.get("reason","")
    batch  = data.get("batch") or None
    
    # Admin-led assignments are auto-approved
    status = data.get("status", "pending") if claims.get("role") == "admin" else "pending"

    if not all([tid, sid, cid, day, st, et]):
        return jsonify({"error": "Missing required fields"}), 400

    # Insert into extra_lectures
    eid = db_execute(
        "INSERT INTO extra_lectures (tid, sid, cid, batch, day, start_time, end_time, room, reason, status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (tid, sid, cid, batch, day, st, et, room, reason, status)
    )
    return jsonify({"success": True, "eid": eid})

@app.route("/api/notifications")
def get_notifications():
    cid = request.args.get("cid", type=int)
    batch = request.args.get("batch") or None
    
    if cid:
        if batch:
            rows = db_query(
                "SELECT * FROM notifications WHERE target_cid IS NULL OR (target_cid=%s AND (target_batch IS NULL OR target_batch=%s)) ORDER BY created_at DESC LIMIT 20",
                (cid, batch)
            )
        else:
            rows = db_query(
                "SELECT * FROM notifications WHERE target_cid IS NULL OR (target_cid=%s AND target_batch IS NULL) ORDER BY created_at DESC LIMIT 20",
                (cid,)
            )
    else:
        # If 'admin=1' is passed, show both public and admin-only alerts
        if request.args.get("admin") == "1":
            rows = db_query("SELECT * FROM notifications WHERE target_cid IS NULL OR target_cid = -1 ORDER BY created_at DESC LIMIT 30")
        else:
            # Public view (Home page) only sees target_cid IS NULL
            rows = db_query("SELECT * FROM notifications WHERE target_cid IS NULL ORDER BY created_at DESC LIMIT 20")
        
    for r in rows:
        r["created_at"] = str(r["created_at"])
    return jsonify(rows)

# ═══════════════════════════════════════════════════════════════════════════════
# AI ENGINE — Smart Substitute Suggester
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/ai/substitute-suggestions")
@jwt_required()
def ai_substitute_suggestions():
    """
    AI Engine: Finds the best substitute teacher for a given slot using
    Content-Based Filtering (Cosine Similarity).
    """
    if not cosine_similarity or not MultiLabelBinarizer:
        return jsonify({"error": "AI libraries (scikit-learn/numpy) not installed"}), 500

    target_sid  = request.args.get("sid", type=int)
    day         = request.args.get("day")
    start_time  = request.args.get("start_time")
    end_time    = request.args.get("end_time")

    if not all([target_sid, day, start_time, end_time]):
        return jsonify({"error": "Missing parameters (sid, day, start_time, end_time)"}), 400

    # 1. Get all teachers
    all_teachers = db_query("SELECT tid, tname FROM teachers")
    if not all_teachers:
        return jsonify([])

    # 2. Identify BUSY teachers at this slot (Master Timetable + Extra Lectures)
    busy_timetable = db_query("""
        SELECT DISTINCT tid FROM timetable 
        WHERE day = %s AND start_time < %s AND end_time > %s AND tid IS NOT NULL
    """, (day, end_time, start_time))
    
    busy_extra = db_query("""
        SELECT DISTINCT tid FROM extra_lectures 
        WHERE day = %s AND start_time < %s AND end_time > %s AND status = 'approved' AND tid IS NOT NULL
    """, (day, end_time, start_time))

    busy_tids = set(r["tid"] for r in busy_timetable) | set(r["tid"] for r in busy_extra)

    # 3. Filter for AVAILABLE teachers
    available_teachers = [t for t in all_teachers if t["tid"] not in busy_tids]
    if not available_teachers:
        return jsonify([])

    # 4. AI RANKING — Content-Based Filtering
    # a) Get teacher-subject mapping from history
    history = db_query("SELECT tid, sid FROM timetable WHERE tid IS NOT NULL")
    teacher_subjects = {}
    for h in history:
        tid = h["tid"]
        sid = h["sid"]
        if tid not in teacher_subjects:
            teacher_subjects[tid] = set()
        teacher_subjects[tid].add(str(sid))

    # b) Prepare Data for Scikit-Learn
    all_available_tids = [t["tid"] for t in available_teachers]
    # List of lists of subjects for each available teacher
    train_data = []
    for tid in all_available_tids:
        train_data.append(list(teacher_subjects.get(tid, set())))

    # c) Vectorize
    mlb = MultiLabelBinarizer()
    # Get all possible subject IDs in the system to define the vector space
    all_sids_rows = db_query("SELECT sid FROM subjects")
    all_sids = [str(s["sid"]) for s in all_sids_rows]
    mlb.fit([all_sids]) 

    teacher_vectors = mlb.transform(train_data)
    
    # d) Target Slot Vector (One-Hot for the required subject)
    target_vector = mlb.transform([[str(target_sid)]])

    # e) Compute Similarity
    similarities = cosine_similarity(target_vector, teacher_vectors)[0]

    # 5. Assemble Results
    suggestions = []
    for i, score in enumerate(similarities):
        teacher = available_teachers[i]
        suggestions.append({
            "tid": teacher["tid"],
            "tname": teacher["tname"],
            "score": round(float(score), 4),
            "reason": "Subject Expert" if score > 0 else "Available"
        })

    # Sort by score (AI best match first), then by name
    suggestions.sort(key=lambda x: x["score"], reverse=True)

    return jsonify(suggestions[:5]) # Top 5

# ── AI Chatbot Engine (NLU) ──────────────────────────────────────────────────

@app.route("/api/teacher/mark-absent", methods=["POST"])
@jwt_required()
def mark_absent():
    """
    Teacher reports an absence for a specific slot.
    This sends a high-priority notification to the Admin.
    """
    claims = get_jwt()
    data = request.get_json()
    tid = claims.get("tid")
    tname = claims.get("username")
    
    day = data.get("day")
    start = data.get("start_time")
    end = data.get("end_time")
    subject = data.get("sname")
    sid = data.get("sid")
    cid = data.get("cid")
    classname = data.get("class_name")

    message = f"🚨 ABSENCE ALERT: {tname} is absent for {subject} ({classname}) today at {start}-{end}."
    
    # Store notification in DB (Admin-only targets have target_cid = -1 internally here for demo)
    import json
    metadata = json.dumps({
        "sid": sid, "day": day, "start": start, "end": end, "sname": subject, "cid": cid
    })
    nid = db_execute(
        "INSERT INTO notifications (message, type, target_cid, metadata) VALUES (%s, 'cancel', -1, %s)",
        (message, metadata)
    )
    
    # Also broadcast via SocketIO
    socketio.emit("absence_reported", {
        "nid": nid,
        "message": message,
        "tid": tid,
        "sid": sid,
        "day": day,
        "start": start,
        "end": end,
        "cid": cid
    }, room="admin")

    return jsonify({"success": True, "message": "Absence reported to Admin."})

def parse_time_str(t) -> str:
    """Helper to convert TIME objects to HH:MM format."""
    if not t:
        return ""
    if hasattr(t, "seconds"):
        total = int(t.total_seconds())
        return f"{total//3600:02d}:{(total%3600)//60:02d}"
    return str(t)[:5]

# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN TEACHER VERIFICATION & CRUD
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/admin/pending-teachers", methods=["GET"])
@require_role("admin")
def get_pending_teachers():
    rows = db_query("SELECT tid, tname, department, cabin_no, email, phone, status FROM teachers WHERE status='pending' ORDER BY tname")
    return jsonify(rows)

@app.route("/api/admin/verify-teacher/<int:tid>", methods=["PUT"])
@require_role("admin")
def verify_teacher(tid):
    data = request.get_json() or {}
    status = data.get("status")
    if status not in ("approved", "rejected"):
        return jsonify({"error": "Invalid status (must be approved or rejected)"}), 400
    db_execute("UPDATE teachers SET status=%s WHERE tid=%s", (status, tid))
    return jsonify({"success": True})

@app.route("/api/admin/teachers", methods=["GET"])
@require_role("admin")
def admin_get_teachers():
    rows = db_query("SELECT tid, tname, department, cabin_no, email, phone, status FROM teachers ORDER BY tname")
    return jsonify(rows)

@app.route("/api/admin/teachers", methods=["POST"])
@require_role("admin")
def admin_create_teacher():
    data = request.get_json() or {}
    tname = data.get("tname", "").strip()
    department = data.get("department", "").strip()
    cabin_no = data.get("cabin_no", "").strip()
    email = data.get("email", "").strip()
    phone = data.get("phone", "").strip()
    status = data.get("status", "approved")
    
    if not tname:
        return jsonify({"error": "Teacher name required"}), 400
    
    try:
        tid = db_execute(
            "INSERT INTO teachers (tname, department, cabin_no, email, phone, status) VALUES (%s, %s, %s, %s, %s, %s)",
            (tname, department or None, cabin_no or None, email or None, phone or None, status)
        )
        return jsonify({"success": True, "tid": tid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/teachers/<int:tid>", methods=["PUT"])
@require_role("admin")
def admin_update_teacher(tid):
    data = request.get_json() or {}
    tname = data.get("tname", "").strip()
    department = data.get("department", "").strip()
    cabin_no = data.get("cabin_no", "").strip()
    email = data.get("email", "").strip()
    phone = data.get("phone", "").strip()
    status = data.get("status")

    if not tname:
        return jsonify({"error": "Teacher name required"}), 400

    try:
        if status:
            db_execute(
                "UPDATE teachers SET tname=%s, department=%s, cabin_no=%s, email=%s, phone=%s, status=%s WHERE tid=%s",
                (tname, department or None, cabin_no or None, email or None, phone or None, status, tid)
            )
        else:
            db_execute(
                "UPDATE teachers SET tname=%s, department=%s, cabin_no=%s, email=%s, phone=%s WHERE tid=%s",
                (tname, department or None, cabin_no or None, email or None, phone or None, tid)
            )
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/teachers/<int:tid>", methods=["DELETE"])
@require_role("admin")
def admin_delete_teacher(tid):
    try:
        db_execute("DELETE FROM teachers WHERE tid=%s", (tid,))
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ═══════════════════════════════════════════════════════════════════════════════
# FACULTY SEARCH, INFO, & FREE SLOTS CALCULATION
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/faculty", methods=["GET"])
def get_faculty_list():
    rows = db_query("SELECT tid, tname, department, cabin_no, email, phone FROM teachers WHERE status='approved' ORDER BY department, tname")
    return jsonify(rows)

@app.route("/api/faculty/search", methods=["GET"])
def search_faculty():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    rows = db_query(
        "SELECT tid, tname, department, cabin_no FROM teachers WHERE status='approved' AND (tname LIKE %s OR department LIKE %s) LIMIT 10",
        (f"%{q}%", f"%{q}%")
    )
    return jsonify(rows)

@app.route("/api/faculty/<int:tid>/info", methods=["GET"])
def get_faculty_info(tid):
    teacher = db_query("SELECT tid, tname, department, cabin_no, email, phone, status FROM teachers WHERE tid=%s", (tid,), one=True)
    if not teacher or teacher["status"] != "approved":
        return jsonify({"error": "Faculty not found"}), 404

    day = today()
    now = now_time()
    
    # Active classroom check
    sql = """
        SELECT start_time, end_time, room, sname, class_name
        FROM (
            SELECT t.start_time, t.end_time, t.room, s.sname,
                   CONCAT(cl.class_name, ' ', cl.class_room_no) AS class_name
            FROM timetable t
            JOIN subjects s ON t.sid = s.sid
            JOIN classes cl ON t.cid = cl.cid
            WHERE t.tid = %s AND t.day = %s
            
            UNION ALL
            
            SELECT e.start_time, e.end_time, e.room, s.sname,
                   CONCAT(cl.class_name, ' ', cl.class_room_no) AS class_name
            FROM extra_lectures e
            JOIN subjects s ON e.sid = s.sid
            JOIN classes cl ON e.cid = cl.cid
            WHERE e.tid = %s AND e.day = %s AND e.status = 'approved'
        ) AS combined
        WHERE start_time <= %s AND end_time > %s
        LIMIT 1
    """
    current_lec = db_query(sql, (tid, day, tid, day, now, now), one=True)
    if current_lec:
        for key in ("start_time", "end_time"):
            current_lec[key] = parse_time_str(current_lec[key])

    # Check active status override
    override_now = db_query("""
        SELECT status, reason FROM teacher_schedule
        WHERE tid=%s AND (day=%s OR date=CURDATE()) AND start_time <= %s AND end_time > %s
        LIMIT 1
    """, (tid, day, now, now), one=True)

    status_str = "Available"
    details_str = "Faculty is currently free."
    current_room = None

    if override_now:
        if override_now["status"] == "on leave":
            status_str = "On Leave"
            details_str = f"On leave: {override_now['reason'] or 'No reason provided'}"
        elif override_now["status"] == "busy":
            status_str = "Busy"
            details_str = f"Busy: {override_now['reason'] or 'No reason provided'}"
        elif override_now["status"] == "available":
            status_str = "Available"
            details_str = "Faculty is available (marked manually)."
    elif current_lec:
        status_str = "In Lecture"
        details_str = f"Teaching {current_lec['sname']} to {current_lec['class_name']}"
        current_room = current_lec["room"]

    # Weekly schedule
    schedule_rows = db_query("""
        SELECT t.day, t.start_time, t.end_time, t.room, s.sname, cl.class_name, 0 as is_extra
        FROM timetable t
        JOIN subjects s ON t.sid = s.sid
        JOIN classes cl ON t.cid = cl.cid
        WHERE t.tid = %s
        
        UNION ALL
        
        SELECT e.day, e.start_time, e.end_time, e.room, s.sname, cl.class_name, 1 as is_extra
        FROM extra_lectures e
        JOIN subjects s ON e.sid = s.sid
        JOIN classes cl ON e.cid = cl.cid
        WHERE e.tid = %s AND e.status = 'approved'
        
        ORDER BY FIELD(day,'Monday','Tuesday','Wednesday','Thursday','Friday'), start_time
    """, (tid, tid))

    weekly_schedule = []
    for s in schedule_rows:
        weekly_schedule.append({
            "day": s["day"],
            "start_time": parse_time_str(s["start_time"]),
            "end_time": parse_time_str(s["end_time"]),
            "room": s["room"],
            "subject": s["sname"],
            "class": s["class_name"],
            "is_extra": bool(s["is_extra"])
        })

    # Calculated Free Slots
    STANDARD_SLOTS = [
        ("08:45", "09:45"),
        ("09:45", "10:45"),
        ("11:00", "12:00"),
        ("12:00", "13:00"),
        ("13:45", "14:45"),
        ("14:45", "15:45"),
        ("15:45", "16:45")
    ]
    DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    
    occupied_slots = db_query("""
        SELECT day, start_time, end_time FROM timetable WHERE tid=%s
        UNION ALL
        SELECT day, start_time, end_time FROM extra_lectures WHERE tid=%s AND status='approved'
    """, (tid, tid))

    occupied_list = []
    for o in occupied_slots:
        o_day = o["day"]
        sh, sm = parse_time_str(o["start_time"]).split(":")
        eh, em = parse_time_str(o["end_time"]).split(":")
        occupied_list.append({
            "day": o_day,
            "start": int(sh)*60 + int(sm),
            "end": int(eh)*60 + int(em)
        })

    overrides = db_query("SELECT day, date, start_time, end_time, status FROM teacher_schedule WHERE tid=%s", (tid,))
    override_list = []
    for ov in overrides:
        sh, sm = parse_time_str(ov["start_time"]).split(":")
        eh, em = parse_time_str(ov["end_time"]).split(":")
        override_list.append({
            "day": ov["day"],
            "date": str(ov["date"]) if ov["date"] else None,
            "start": int(sh)*60 + int(sm),
            "end": int(eh)*60 + int(em),
            "status": ov["status"]
        })

    free_slots = {day: [] for day in DAYS}
    for d in DAYS:
        for s_start, s_end in STANDARD_SLOTS:
            sh, sm = s_start.split(":")
            eh, em = s_end.split(":")
            slot_start_min = int(sh)*60 + int(sm)
            slot_end_min = int(eh)*60 + int(em)
            
            is_busy = False
            for occ in occupied_list:
                if occ["day"] == d:
                    if occ["start"] < slot_end_min and occ["end"] > slot_start_min:
                        is_busy = True
                        break
            
            for ov in override_list:
                if ov["day"] == d:
                    if ov["start"] < slot_end_min and ov["end"] > slot_start_min:
                        if ov["status"] in ('busy', 'on leave'):
                            is_busy = True
                        elif ov["status"] == 'available':
                            is_busy = False
                        break

            if not is_busy:
                free_slots[d].append(f"{s_start}–{s_end}")

    return jsonify({
        "teacher": {
            "tid": teacher["tid"],
            "tname": teacher["tname"],
            "department": teacher["department"] or "—",
            "cabin_no": teacher["cabin_no"] or "—",
            "email": teacher["email"] or "—",
            "phone": teacher["phone"] or "—",
            "status": status_str,
            "details": details_str,
            "current_room": current_room
        },
        "weekly_schedule": weekly_schedule,
        "free_slots": free_slots
    })

# ═══════════════════════════════════════════════════════════════════════════════
# TEACHER SCHEDULE OVERRIDES & TIMETABLE CRUD
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/teacher/schedule-overrides", methods=["GET"])
@require_role("teacher")
def get_schedule_overrides():
    claims = get_jwt()
    tid = claims.get("tid")
    if not tid:
        return jsonify({"error": "No teacher profile linked."}), 404
    rows = db_query("SELECT id, day, date, start_time, end_time, status, reason FROM teacher_schedule WHERE tid=%s", (tid,))
    for r in rows:
        r["date"] = str(r["date"]) if r["date"] else None
        for key in ("start_time", "end_time"):
            r[key] = parse_time_str(r[key])
    return jsonify(rows)

@app.route("/api/teacher/schedule-overrides", methods=["POST"])
@require_role("teacher")
def add_schedule_override():
    claims = get_jwt()
    tid = claims.get("tid")
    if not tid:
        return jsonify({"error": "No teacher profile linked."}), 404

    data = request.get_json() or {}
    day = data.get("day") or None
    date_str = data.get("date") or None
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    status = data.get("status")
    reason = data.get("reason", "")

    if not all([start_time, end_time, status]):
        return jsonify({"error": "Missing start_time, end_time, or status"}), 400

    if status not in ('busy', 'available', 'on leave'):
        return jsonify({"error": "Invalid status value"}), 400

    db_execute(
        "INSERT INTO teacher_schedule (tid, day, date, start_time, end_time, status, reason) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (tid, day, date_str, start_time, end_time, status, reason)
    )
    return jsonify({"success": True})

@app.route("/api/teacher/schedule-overrides/<int:id>", methods=["DELETE"])
@require_role("teacher")
def delete_schedule_override(id):
    claims = get_jwt()
    tid = claims.get("tid")
    if not tid:
        return jsonify({"error": "No teacher profile linked."}), 404
    
    row = db_query("SELECT id FROM teacher_schedule WHERE id=%s AND tid=%s", (id, tid), one=True)
    if not row:
        return jsonify({"error": "Override not found"}), 404
    db_execute("DELETE FROM teacher_schedule WHERE id=%s", (id,))
    return jsonify({"success": True})

@app.route("/api/timetable/slots", methods=["GET"])
@require_role("teacher")
def get_my_timetable_slots():
    claims = get_jwt()
    tid = claims.get("tid")
    if not tid:
        return jsonify({"error": "No teacher profile linked."}), 404
    rows = db_query("""
        SELECT t.id, t.cid, t.sid, t.day, t.start_time, t.end_time, t.batch, t.room, t.sem, t.academic_year,
               s.sname, c.class_name, c.class_room_no
        FROM timetable t
        JOIN subjects s ON t.sid = s.sid
        JOIN classes c ON t.cid = c.cid
        WHERE t.tid = %s
        ORDER BY FIELD(t.day,'Monday','Tuesday','Wednesday','Thursday','Friday'), t.start_time
    """, (tid,))
    for r in rows:
        for key in ("start_time", "end_time"):
            r[key] = parse_time_str(r[key])
    return jsonify(rows)

@app.route("/api/timetable/slots", methods=["POST"])
@require_role("teacher")
def create_timetable_slot():
    claims = get_jwt()
    tid = claims.get("tid")
    if not tid:
        return jsonify({"error": "No teacher profile linked."}), 404
    
    data = request.get_json() or {}
    cid = data.get("cid")
    sid = data.get("sid")
    day = data.get("day")
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    batch = data.get("batch") or None
    room = data.get("room")
    sem = data.get("sem")
    academic_year = data.get("academic_year", "2025-26")

    if not all([cid, sid, day, start_time, end_time, room]):
        return jsonify({"error": "Missing required fields"}), 400

    new_id = db_execute("""
        INSERT INTO timetable (cid, sid, tid, day, start_time, end_time, batch, room, sem, academic_year)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (cid, sid, tid, day, start_time, end_time, batch, room, sem, academic_year))

    return jsonify({"success": True, "id": new_id})

@app.route("/api/timetable/slots/<int:id>", methods=["PUT"])
@require_role("teacher")
def update_timetable_slot(id):
    claims = get_jwt()
    tid = claims.get("tid")
    if not tid:
        return jsonify({"error": "No teacher profile linked."}), 404
    
    slot = db_query("SELECT id FROM timetable WHERE id=%s AND tid=%s", (id, tid), one=True)
    if not slot:
        return jsonify({"error": "Slot not found or unauthorized"}), 404

    data = request.get_json() or {}
    cid = data.get("cid")
    sid = data.get("sid")
    day = data.get("day")
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    batch = data.get("batch") or None
    room = data.get("room")
    sem = data.get("sem")
    academic_year = data.get("academic_year", "2025-26")

    if not all([cid, sid, day, start_time, end_time, room]):
        return jsonify({"error": "Missing required fields"}), 400

    db_execute("""
        UPDATE timetable 
        SET cid=%s, sid=%s, day=%s, start_time=%s, end_time=%s, batch=%s, room=%s, sem=%s, academic_year=%s
        WHERE id=%s AND tid=%s
    """, (cid, sid, day, start_time, end_time, batch, room, sem, academic_year, id, tid))

    return jsonify({"success": True})

@app.route("/api/timetable/slots/<int:id>", methods=["DELETE"])
@require_role("teacher")
def delete_timetable_slot(id):
    claims = get_jwt()
    tid = claims.get("tid")
    if not tid:
        return jsonify({"error": "No teacher profile linked."}), 404
    
    slot = db_query("SELECT id FROM timetable WHERE id=%s AND tid=%s", (id, tid), one=True)
    if not slot:
        return jsonify({"error": "Slot not found or unauthorized"}), 404

    db_execute("DELETE FROM timetable WHERE id=%s AND tid=%s", (id, tid))
    return jsonify({"success": True})


@app.route("/api/appointments/teacher", methods=["GET"])
@require_role("teacher")
def get_teacher_appointments():
    claims = get_jwt()
    tid = claims.get("tid")
    if not tid:
        return jsonify({"error": "No teacher profile linked."}), 404
    rows = db_query("""
        SELECT a.aid, a.student_id, a.date, a.start_time, a.end_time, a.status, a.message, a.teacher_reply, a.created_at,
               s.sname, s.enrollment_no, s.department, s.semester, s.email, s.phone
          FROM appointments a
          JOIN students s ON a.student_id = s.student_id
          WHERE a.tid = %s
          ORDER BY a.date DESC, a.start_time DESC
    """, (tid,))
    for r in rows:
        r["date"] = str(r["date"])
        r["created_at"] = str(r["created_at"])
        for key in ("start_time", "end_time"):
            r[key] = parse_time_str(r[key])
    return jsonify(rows)

@app.route("/api/appointments/teacher/<int:aid>", methods=["PUT"])
@require_role("teacher")
def respond_to_appointment(aid):
    claims = get_jwt()
    tid = claims.get("tid")
    if not tid:
        return jsonify({"error": "No teacher profile linked."}), 404
    
    appt = db_query("SELECT aid FROM appointments WHERE aid=%s AND tid=%s", (aid, tid), one=True)
    if not appt:
        return jsonify({"error": "Appointment not found or unauthorized"}), 404

    data = request.get_json() or {}
    status = data.get("status")
    teacher_reply = data.get("teacher_reply")
    start_time = data.get("start_time")
    end_time = data.get("end_time")

    fields = []
    params = []

    if status in ('accepted', 'declined', 'pending'):
        fields.append("status = %s")
        params.append(status)
    if teacher_reply is not None:
        fields.append("teacher_reply = %s")
        params.append(teacher_reply)
    if start_time:
        fields.append("start_time = %s")
        params.append(start_time)
    if end_time:
        fields.append("end_time = %s")
        params.append(end_time)

    if not fields:
        return jsonify({"error": "No updates provided"}), 400

    params.append(aid)
    params.append(tid)

    sql = f"UPDATE appointments SET {', '.join(fields)} WHERE aid = %s AND tid = %s"
    db_execute(sql, tuple(params))
    return jsonify({"success": True})

# ═══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET EVENTS
# ═══════════════════════════════════════════════════════════════════════════════

@socketio.on("connect")
def on_connect():
    emit("connected", {"msg": "Dynamic Campus real-time connected"})

@socketio.on("subscribe")
def on_subscribe(data):
    """Client subscribes to a room e.g. {'room': 'classrooms'} or {'room': 'sem_5'}"""
    room = data.get("room", "general")
    join_room(room)
    emit("subscribed", {"room": room})

# ═══════════════════════════════════════════════════════════════════════════════
# RUN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=Config.FLASK_PORT,
                 debug=Config.DEBUG, allow_unsafe_werkzeug=True)
