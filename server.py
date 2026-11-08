from __future__ import annotations

import base64
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent
LOCAL_DATA = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
DATA_DIR = Path(os.environ.get("KENGASH_DATA_DIR", str(LOCAL_DATA / "YoshlarKengashi")))
UPLOAD_DIR = DATA_DIR / "uploads"
VERIFICATION_DIR = DATA_DIR / "verification-private"
DB_PATH = DATA_DIR / "yoshlar.sqlite3"
HOST = "127.0.0.1"
PORT = int(os.environ.get("KENGASH_PORT", "8000"))
MAX_BODY_BYTES = 12 * 1024 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_MEMBERS = int(os.environ.get("KENGASH_MAX_MEMBERS", "20"))
IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
SESSION_COOKIE = "som_session"
SESSION_TTL = timedelta(hours=12)

SEED_MEMBERS = [
    ("Muhammadaziz", "Olimbayev", "Yoshlar yetakchisi", "Kengash faoliyatini muvofiqlashtirish, rahbariyat va talabalar o‘rtasida aloqa, loyihalar va yig‘ilishlar nazorati.", 90),
    ("Jasmina", "Yangiyeva", "Intellektual loyihalar koordinatori", "Zakovat, olimpiada, debat va intellektual musobaqalar; iqtidorli talabalarni aniqlash.", 92),
    ("Aliya", "Shaydullina", "Besh tashabbus loyihalari koordinatori", "Madaniyat, san’at, sport, kitobxonlik va IT tadbirlari hamda tanlovlari.", 80),
    ("Mirfayz", "Elmurodov", "Harbiy-vatanparvarlik loyihalari koordinatori", "Vatanparvarlik tadbirlari, ekskursiyalar va “Mard o‘g‘lonlar” loyihalari.", 78),
    ("Shoxrux", "Sharipov", "Tadbirkorlik va innovatsion loyihalar koordinatori", "Startap, innovatsion tashabbuslar, biznes trening va tadbirkorlar bilan uchrashuvlar.", 84),
    ("Shaxzodabonu", "Maxamatsoliyeva", "“Yoshlar daftari” va metsenatlik dasturlari koordinatori", "Ijtimoiy ko‘makka muhtoj talabalar va homiylik dasturlarini muvofiqlashtirish.", 76),
    ("Malika", "Roziyeva", "Talaba qizlar koordinatori", "Talaba qizlar faolligi, huquqlari, kasbiy rivojlanishi va tashabbuslari.", 86),
    ("Fayozbek", "Jonboyev", "Media va axborot yo‘nalishi koordinatori", "Kengash sahifalari, foto-video, maqola, e’lon va jamoatchilik bilan aloqa.", 88),
    ("Sanjarbek", "Alijonov", "Soliqlar va buxgalteriya hisobi fakulteti koordinatori", "Fakultet muammolari, dekanat bilan hamkorlik va talabalarni loyihalarga jalb qilish.", 82),
    ("Timurxon", "Ablayarov", "Akademik guruhlar koordinatori", "Guruh sardorlari bilan ishlash, o‘quv jarayoni muammolarini aniqlash.", 75),
    ("Mohinur", "Abdukarimova", "Fakultet talaba qizlar koordinatori", "Fakultetdagi talaba qizlarning faolligi, tashabbuslari va muammolari.", 83),
]
SEED_REPORTS = [
    {
        "member": "Jasmina Yangiyeva",
        "week": "2026-W45",
        "event": "Zakovat turniri",
        "category": "Intellektual loyihalar",
        "description": "36 nafar talaba qatnashdi. Foto va ishtirokchilar ro‘yxati ilova qilindi.",
        "score": 92,
        "status": "Tasdiqlangan",
        "proof": True,
        "images": [
            "hisobotlar/zakovat/photo_2026-11-08_08-46-31.jpg",
            "hisobotlar/zakovat/photo_2026-11-08_08-46-34.jpg",
            "hisobotlar/zakovat/photo_2026-11-08_08-46-35.jpg",
            "hisobotlar/zakovat/photo_2026-11-08_08-46-43.jpg",
            "hisobotlar/zakovat/photo_2026-11-08_08-46-45.jpg",
            "hisobotlar/zakovat/photo_2026-11-08_08-46-46%20(2).jpg",
            "hisobotlar/zakovat/photo_2026-11-08_08-46-47.jpg",
            "hisobotlar/zakovat/photo_2026-11-08_08-46-49.jpg",
        ],
    },
    {
        "member": "Fayozbek Jonboyev",
        "week": "2026-W45",
        "event": "Islom sivilizatsiyasi markaziga sayohat",
        "category": "Besh tashabbus",
        "description": "Talabalar uchun madaniy-ma’rifiy sayohat tashkil etildi.",
        "score": 88,
        "status": "Tekshiruvda",
        "proof": True,
        "images": [
            "hisobotlar/sivilizatsiya/photo_2026-11-08_08-55-50.jpg",
            "hisobotlar/sivilizatsiya/photo_2026-11-08_08-56-03.jpg",
            "hisobotlar/sivilizatsiya/photo_2026-11-08_08-56-08.jpg",
            "hisobotlar/sivilizatsiya/photo_2026-11-08_08-56-12.jpg",
            "hisobotlar/sivilizatsiya/photo_2026-11-08_08-56-14.jpg",
            "hisobotlar/sivilizatsiya/photo_2026-11-08_08-56-17.jpg",
        ],
    },
    {
        "member": "Shoxrux Sharipov",
        "week": "2026-W45",
        "event": "Startap g‘oyalari uchrashuvi",
        "category": "Innovatsion loyihalar",
        "description": "18 nafar ishtirokchi bilan startap g‘oyalari muhokama qilindi.",
        "score": 84,
        "status": "Tuzatish kerak",
        "proof": False,
        "images": [],
    },
]


def connect_db() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def database():
    connection = connect_db()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def name_key(first_name: str, last_name: str) -> str:
    return " ".join(f"{first_name} {last_name}".casefold().split())


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=1 << 14, r=8, p=1, dklen=64)
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_hex, digest_hex = encoded.split("$")
        if algorithm != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
            n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(digest_hex)),
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def append_audit_log(db: sqlite3.Connection, actor_user_id: int | None, action: str,
                     entity_type: str, entity_id: str | int | None,
                     before: dict | None = None, after: dict | None = None) -> None:
    previous = db.execute("SELECT entry_hash FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
    previous_hash = previous["entry_hash"] if previous else ""
    created_at = now_utc().isoformat()
    before_json = json.dumps(before, ensure_ascii=False, sort_keys=True) if before is not None else None
    after_json = json.dumps(after, ensure_ascii=False, sort_keys=True) if after is not None else None
    canonical = json.dumps(
        [actor_user_id, action, entity_type, str(entity_id) if entity_id is not None else None,
         before_json, after_json, created_at],
        ensure_ascii=False, separators=(",", ":"),
    )
    entry_hash = hashlib.sha256((previous_hash + canonical).encode("utf-8")).hexdigest()
    db.execute(
        "INSERT INTO audit_logs (actor_user_id,action,entity_type,entity_id,before_json,after_json,previous_hash,entry_hash,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (actor_user_id, action, entity_type, str(entity_id) if entity_id is not None else None,
         before_json, after_json, previous_hash or None, entry_hash, created_at),
    )


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    VERIFICATION_DIR.mkdir(parents=True, exist_ok=True)
    with database() as db:
        db.executescript((ROOT / "schema.sql").read_text(encoding="utf-8"))
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                role TEXT NOT NULL,
                duty TEXT NOT NULL,
                kpi INTEGER NOT NULL DEFAULT 0 CHECK (kpi BETWEEN 0 AND 100),
                photo TEXT,
                name_key TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_name TEXT NOT NULL,
                week TEXT NOT NULL,
                event TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
                status TEXT NOT NULL CHECK (status IN ('Tekshiruvda', 'Tasdiqlangan', 'Tuzatish kerak')),
                proof INTEGER NOT NULL DEFAULT 0,
                images TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );
            """
        )
        member_columns = {row["name"] for row in db.execute("PRAGMA table_info(members)")}
        if "photo" not in member_columns:
            db.execute("ALTER TABLE members ADD COLUMN photo TEXT")
        report_columns = {row["name"] for row in db.execute("PRAGMA table_info(reports)")}
        report_migrations = {
            "club_id": "INTEGER REFERENCES clubs(id)",
            "plan_id": "INTEGER REFERENCES club_plans(id)",
            "submitted_by": "INTEGER REFERENCES users(id)",
            "period_type": "TEXT NOT NULL DEFAULT 'weekly' CHECK (period_type IN ('weekly', 'monthly'))",
            "title": "TEXT",
        }
        for column, definition in report_migrations.items():
            if column not in report_columns:
                db.execute(f"ALTER TABLE reports ADD COLUMN {column} {definition}")
        db.execute("CREATE INDEX IF NOT EXISTS idx_reports_club_status ON reports(club_id,status,created_at)")
        db.execute(
            """CREATE VIEW IF NOT EXISTS club_rankings AS
               SELECT c.id AS club_id, c.name AS club_name,
                      COUNT(r.id) AS approved_reports,
                      ROUND(AVG(r.score), 2) AS average_score,
                      (SELECT COUNT(*) FROM club_memberships cm
                       WHERE cm.club_id=c.id AND cm.status='active') AS active_members
               FROM clubs c
               LEFT JOIN reports r ON r.club_id=c.id AND r.status='Tasdiqlangan'
               GROUP BY c.id, c.name"""
        )
        now = datetime.now(timezone.utc).isoformat()
        if db.execute("SELECT COUNT(*) FROM members").fetchone()[0] == 0:
            for first, last, role, duty, kpi in SEED_MEMBERS:
                db.execute(
                    "INSERT INTO members (first_name,last_name,role,duty,kpi,name_key,created_at) VALUES (?,?,?,?,?,?,?)",
                    (first, last, role, duty, kpi, name_key(first, last), now),
                )
        if db.execute("SELECT COUNT(*) FROM reports").fetchone()[0] == 0:
            for report in SEED_REPORTS:
                db.execute(
                    "INSERT INTO reports (member_name,week,event,category,description,score,status,proof,images,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        report["member"], report["week"], report["event"], report["category"],
                        report["description"], report["score"], report["status"], int(report["proof"]),
                        json.dumps(report["images"], ensure_ascii=False), now,
                    ),
                )
        admin_email = os.environ.get("KENGASH_BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
        admin_password = os.environ.get("KENGASH_BOOTSTRAP_ADMIN_PASSWORD", "")
        if bool(admin_email) != bool(admin_password):
            raise RuntimeError("Admin bootstrap uchun email va parol ikkalasi ham berilishi kerak.")
        if admin_email and (not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", admin_email) or len(admin_password) < 12):
            raise RuntimeError("Admin bootstrap uchun to‘g‘ri email va kamida 12 belgili parol kerak.")
        if admin_email and not db.execute("SELECT 1 FROM user_roles WHERE role_key='admin' LIMIT 1").fetchone():
            created_at = now_utc().isoformat()
            cursor = db.execute(
                "INSERT INTO users (email,password_hash,display_name,status,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                (admin_email, password_hash(admin_password), "SOM Admin", "verified", created_at, created_at),
            )
            db.execute(
                "INSERT INTO user_roles (user_id,role_key,granted_at) VALUES (?,'admin',?)",
                (cursor.lastrowid, created_at),
            )
            append_audit_log(db, cursor.lastrowid, "admin.bootstrap", "user", cursor.lastrowid,
                             after={"role": "admin", "status": "verified"})


def state_payload() -> dict:
    with database() as db:
        members = db.execute("SELECT first_name,last_name,role,duty,kpi,photo FROM members ORDER BY id").fetchall()
        reports = db.execute("SELECT * FROM reports WHERE status='Tasdiqlangan' ORDER BY id DESC").fetchall()
        summary = {
            "active_clubs": db.execute("SELECT COUNT(*) FROM clubs WHERE status='active'").fetchone()[0],
            "verified_students": db.execute("SELECT COUNT(*) FROM users WHERE status='verified'").fetchone()[0],
            "approved_reports": db.execute("SELECT COUNT(*) FROM reports WHERE status='Tasdiqlangan'").fetchone()[0],
            "average_kpi": round(db.execute("SELECT COALESCE(AVG(kpi),0) FROM members WHERE kpi > 0").fetchone()[0]),
        }
        top_clubs = db.execute(
            """SELECT ranking.club_id,ranking.club_name,ranking.approved_reports,
                      ranking.average_score,ranking.active_members
               FROM club_rankings ranking JOIN clubs club ON club.id=ranking.club_id
               WHERE club.status='active' AND ranking.approved_reports >= 3
               ORDER BY ranking.average_score DESC, ranking.approved_reports DESC, ranking.club_name ASC
               LIMIT 3"""
        ).fetchall()
        history = db.execute(
            """SELECT event,category,description,week FROM reports
               WHERE status='Tasdiqlangan' ORDER BY created_at DESC,id DESC LIMIT 5"""
        ).fetchall()
    return {
        "members": [[row["first_name"], row["last_name"], row["role"], row["duty"], row["kpi"], row["photo"]] for row in members],
        "reports": [
            {
                "id": row["id"], "n": row["member_name"], "w": row["week"], "event": row["event"],
                "category": row["category"], "description": row["description"], "t": row["description"],
                "s": row["score"], "status": row["status"], "proof": bool(row["proof"]),
                "images": json.loads(row["images"]),
            }
            for row in reports
        ],
        "summary": summary,
        "top_clubs": [dict(row) for row in top_clubs],
        "work_history": [dict(row) for row in history],
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def guess_type(self, path: str) -> str:
        content_type = super().guess_type(path)
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            return f"{content_type}; charset=utf-8"
        return content_type

    def send_json(self, status: int, payload: dict, headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def current_user(self) -> dict | None:
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            token = cookie[SESSION_COOKIE].value
        except (KeyError, AttributeError):
            return None
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with database() as db:
            session = db.execute(
                "SELECT user_id,csrf_hash FROM auth_sessions WHERE token_hash=? AND revoked_at IS NULL AND expires_at>?",
                (token_hash, now_utc().isoformat()),
            ).fetchone()
            if not session:
                return None
            user = db.execute("SELECT id,email,display_name,status FROM users WHERE id=?", (session["user_id"],)).fetchone()
            roles = db.execute("SELECT role_key FROM user_roles WHERE user_id=? ORDER BY role_key", (session["user_id"],)).fetchall()
        if not user or user["status"] in {"rejected", "suspended"}:
            return None
        return {**dict(user), "roles": [row["role_key"] for row in roles], "csrf_hash": session["csrf_hash"]}

    def require_user(self, roles: set[str] | None = None, csrf: bool = False) -> dict | None:
        user = self.current_user()
        if not user:
            self.send_json(401, {"error": "Tizimga kiring."})
            return None
        if roles and not roles.intersection(user["roles"]):
            self.send_json(403, {"error": "Bu amal uchun ruxsatingiz yo‘q."})
            return None
        if csrf:
            supplied = self.headers.get("X-CSRF-Token", "")
            supplied_hash = hashlib.sha256(supplied.encode("utf-8")).hexdigest() if supplied else ""
            if not supplied or not (hmac.compare_digest(supplied_hash, user["csrf_hash"]) or hmac.compare_digest(supplied, user["csrf_hash"])):
                self.send_json(403, {"error": "CSRF tekshiruvi muvaffaqiyatsiz."})
                return None
        return user

    def send_private_image(self, path: Path, private_root: Path = VERIFICATION_DIR) -> None:
        if not path.is_file() or path.parent.resolve() != private_root.resolve():
            self.send_error(404)
            return
        content = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_BODY_BYTES:
            raise ValueError("So‘rov hajmi noto‘g‘ri yoki ruxsat etilganidan katta.")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON obyekt yuborilishi kerak.")
        return payload

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/auth/me":
            user = self.require_user()
            if user:
                self.send_json(200, {
                    **{key: value for key, value in user.items() if key != "csrf_hash"},
                    "csrf_token": user["csrf_hash"],
                })
            return
        if parsed.path == "/api/me/settings":
            user = self.require_user()
            if not user:
                return
            with database() as db:
                preferences = db.execute("SELECT locale,email_notifications FROM user_preferences WHERE user_id=?", (user["id"],)).fetchone()
                profile = db.execute("SELECT profile_photo_path FROM users WHERE id=?", (user["id"],)).fetchone()
            self.send_json(200, {
                "display_name": user["display_name"],
                "locale": preferences["locale"] if preferences else "uz",
                "email_notifications": bool(preferences["email_notifications"]) if preferences else True,
                "profile_photo": profile["profile_photo_path"],
            })
            return
        if parsed.path == "/api/dean/verifications":
            user = self.require_user({"dean", "admin"})
            if not user:
                return
            with database() as db:
                pending = db.execute(
                    """SELECT verification.id,users.display_name,verification.student_number,
                              verification.faculty,verification.study_group,verification.status,
                              verification.created_at,verification.review_note
                       FROM student_verifications verification JOIN users ON users.id=verification.user_id
                       WHERE verification.status='pending' ORDER BY verification.created_at"""
                ).fetchall()
            self.send_json(200, {"items": [dict(row) for row in pending]})
            return
        if parsed.path == "/api/clubs":
            with database() as db:
                clubs = db.execute(
                    """SELECT club.id,club.slug,club.name,club.description,club.category,club.cover_photo_path,
                              ranking.active_members,ranking.approved_reports,ranking.average_score
                       FROM clubs club JOIN club_rankings ranking ON ranking.club_id=club.id
                       WHERE club.status='active' ORDER BY club.name"""
                ).fetchall()
            self.send_json(200, {"items": [dict(row) for row in clubs]})
            return
        club_plans = re.fullmatch(r"/api/clubs/(\d+)/plans", parsed.path)
        if club_plans:
            with database() as db:
                plans = db.execute(
                    "SELECT id,period_type,period_start,period_end,title,objectives,status FROM club_plans WHERE club_id=? AND status='approved' ORDER BY period_start DESC",
                    (int(club_plans.group(1)),),
                ).fetchall()
            self.send_json(200, {"items": [dict(row) for row in plans]})
            return
        if parsed.path == "/api/elections":
            with database() as db:
                elections = db.execute(
                    """SELECT election.id,election.club_id,club.name AS club_name,election.position_title,
                              election.starts_at,election.ends_at,election.status
                       FROM elections election JOIN clubs club ON club.id=election.club_id
                       WHERE election.status IN ('open','closed','published') ORDER BY election.starts_at DESC"""
                ).fetchall()
            self.send_json(200, {"items": [dict(row) for row in elections]})
            return
        election_candidates = re.fullmatch(r"/api/elections/(\d+)/candidates", parsed.path)
        if election_candidates:
            with database() as db:
                candidates = db.execute(
                    """SELECT candidate.id,candidate.user_id,users.display_name,candidate.statement
                       FROM election_candidates candidate JOIN users ON users.id=candidate.user_id
                       WHERE candidate.election_id=? AND candidate.status='approved'
                       ORDER BY users.display_name""",
                    (int(election_candidates.group(1)),),
                ).fetchall()
            self.send_json(200, {"items": [dict(row) for row in candidates]})
            return
        published_results = re.fullmatch(r"/api/elections/(\d+)/results", parsed.path)
        if published_results:
            with database() as db:
                election = db.execute("SELECT status FROM elections WHERE id=?", (int(published_results.group(1)),)).fetchone()
                if not election or election["status"] != "published":
                    self.send_json(404, {"error": "Ovoz berish natijasi hali e’lon qilinmagan."})
                    return
                results = db.execute(
                    """SELECT candidate.id AS candidate_id,users.display_name,candidate.statement,tally.vote_count
                       FROM election_candidates candidate JOIN users ON users.id=candidate.user_id
                       LEFT JOIN election_tallies tally ON tally.election_id=candidate.election_id AND tally.candidate_id=candidate.id
                       WHERE candidate.election_id=? AND candidate.status='approved'
                       ORDER BY COALESCE(tally.vote_count,0) DESC,users.display_name""",
                    (int(published_results.group(1)),),
                ).fetchall()
            self.send_json(200, {"items": [dict(row) for row in results]})
            return
        verification_photo = re.fullmatch(r"/api/dean/verifications/(\d+)/photo", parsed.path)
        if verification_photo:
            user = self.require_user({"dean", "admin"})
            if not user:
                return
            with database() as db:
                row = db.execute("SELECT verification_photo_path FROM student_verifications WHERE id=?", (int(verification_photo.group(1)),)).fetchone()
            if not row:
                self.send_error(404)
                return
            self.send_private_image(VERIFICATION_DIR / Path(row["verification_photo_path"]).name)
            return
        if parsed.path == "/api/state":
            self.send_json(200, state_payload())
            return
        if parsed.path == "/api/dean/reports":
            user = self.require_user({"dean", "admin"})
            if not user:
                return
            with database() as db:
                reports = db.execute(
                    "SELECT id,member_name,week,event,category,description,score,status,proof,images,created_at,club_id,plan_id FROM reports WHERE status IN ('Tekshiruvda','Tuzatish kerak') ORDER BY created_at"
                ).fetchall()
            items = []
            for row in reports:
                item = dict(row)
                images = json.loads(item["images"])
                item["images"] = [f"/api/dean/reports/{item['id']}/images/{index}" for index in range(len(images))]
                items.append(item)
            self.send_json(200, {"items": items})
            return
        report_image = re.fullmatch(r"/api/dean/reports/(\d+)/images/(\d+)", parsed.path)
        if report_image:
            user = self.require_user({"dean", "admin"})
            if not user:
                return
            with database() as db:
                row = db.execute("SELECT images FROM reports WHERE id=? AND status IN ('Tekshiruvda','Tuzatish kerak')", (int(report_image.group(1)),)).fetchone()
            if not row:
                self.send_error(404)
                return
            images = json.loads(row["images"])
            index = int(report_image.group(2))
            if not 0 <= index < len(images):
                self.send_error(404)
                return
            filename = Path(unquote(images[index].removeprefix("/api/uploads/"))).name
            self.send_private_image(UPLOAD_DIR / filename, UPLOAD_DIR)
            return
        if parsed.path == "/api/admin/users":
            user = self.require_user({"admin"})
            if not user:
                return
            with database() as db:
                users = db.execute(
                    """SELECT users.id,users.email,users.display_name,users.status,users.created_at,
                              GROUP_CONCAT(user_roles.role_key, ',') AS roles
                       FROM users LEFT JOIN user_roles ON user_roles.user_id=users.id
                       GROUP BY users.id ORDER BY users.created_at DESC"""
                ).fetchall()
            self.send_json(200, {"items": [{**dict(row), "roles": row["roles"].split(",") if row["roles"] else []} for row in users]})
            return
        club_memberships = re.fullmatch(r"/api/clubs/(\d+)/memberships", parsed.path)
        if club_memberships:
            user = self.require_user({"coordinator", "admin"})
            if not user:
                return
            club_id = int(club_memberships.group(1))
            with database() as db:
                if not self.can_manage_club(db, user, club_id):
                    self.send_json(403, {"error": "Bu klub a’zoliklarini ko‘rish vakolati yo‘q."})
                    return
                rows = db.execute(
                    """SELECT membership.user_id,membership.status,membership.applied_at,users.display_name,users.email
                       FROM club_memberships membership JOIN users ON users.id=membership.user_id
                       WHERE membership.club_id=? ORDER BY membership.applied_at""",
                    (club_id,),
                ).fetchall()
            self.send_json(200, {"items": [dict(row) for row in rows]})
            return
        if parsed.path == "/api/my/reports":
            user = self.require_user({"coordinator", "admin"})
            if not user:
                return
            with database() as db:
                reports = db.execute(
                    """SELECT DISTINCT reports.* FROM reports
                       LEFT JOIN club_memberships membership ON membership.club_id=reports.club_id AND membership.user_id=? AND membership.status='active'
                       WHERE reports.submitted_by=? OR membership.user_id=?
                       ORDER BY reports.created_at DESC""",
                    (user["id"], user["id"], user["id"]),
                ).fetchall()
            self.send_json(200, {"items": [{**dict(row), "images": json.loads(row["images"])} for row in reports]})
            return
        report_versions = re.fullmatch(r"/api/reports/(\d+)/versions", parsed.path)
        if report_versions:
            user = self.require_user({"dean", "coordinator", "admin"})
            if not user:
                return
            with database() as db:
                versions = db.execute(
                    "SELECT version_number,snapshot_json,changed_by,change_note,created_at FROM report_versions WHERE report_id=? ORDER BY version_number DESC",
                    (int(report_versions.group(1)),),
                ).fetchall()
            self.send_json(200, {"items": [{**dict(row), "snapshot": json.loads(row["snapshot_json"])} for row in versions]})
            return
        if parsed.path.startswith("/api/uploads/"):
            filename = Path(unquote(parsed.path.removeprefix("/api/uploads/"))).name
            target = UPLOAD_DIR / filename
            if not target.is_file() or not self.is_public_upload(f"/api/uploads/{filename}"):
                self.send_error(404)
                return
            content = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(content)
            return
        private_files = {"/server.py", "/schema.sql", "/test_server.py", "/README.md", "/ARCHITECTURE.md", "/errors.md", "/.gitignore"}
        if parsed.path in private_files or any(part.startswith(".") for part in parsed.path.split("/")):
            self.send_error(404)
            return
        super().do_GET()

    def is_public_upload(self, image_url: str) -> bool:
        with database() as db:
            if db.execute("SELECT 1 FROM members WHERE photo=? LIMIT 1", (image_url,)).fetchone():
                return True
            if db.execute("SELECT 1 FROM users WHERE profile_photo_path=? LIMIT 1", (image_url,)).fetchone():
                return True
            approved = db.execute("SELECT images FROM reports WHERE status='Tasdiqlangan'").fetchall()
        return any(image_url in json.loads(row["images"]) for row in approved)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            payload = self.read_json()
            if parsed.path == "/api/auth/register":
                self.register_student(payload)
            elif parsed.path == "/api/auth/login":
                self.login(payload)
            elif parsed.path == "/api/auth/logout":
                self.logout()
            elif parsed.path == "/api/me/settings":
                self.update_settings(payload)
            elif parsed.path == "/api/me/password":
                self.change_password(payload)
            elif re.fullmatch(r"/api/dean/verifications/\d+/review", parsed.path):
                self.review_verification(int(parsed.path.split("/")[4]), payload)
            elif parsed.path == "/api/clubs":
                user = self.require_user({"admin"}, csrf=True)
                if user:
                    self.create_club(payload, user)
            elif re.fullmatch(r"/api/admin/users/\d+/roles", parsed.path):
                user = self.require_user({"admin"}, csrf=True)
                if user:
                    self.set_user_roles(int(parsed.path.split("/")[4]), payload, user)
            elif re.fullmatch(r"/api/clubs/\d+/join", parsed.path):
                self.apply_to_club(int(parsed.path.split("/")[3]))
            elif re.fullmatch(r"/api/clubs/\d+/memberships/\d+/review", parsed.path):
                user = self.require_user({"coordinator", "admin"}, csrf=True)
                if user:
                    parts = parsed.path.split("/")
                    self.review_membership(int(parts[3]), int(parts[5]), payload, user)
            elif re.fullmatch(r"/api/clubs/\d+/plans", parsed.path):
                user = self.require_user({"coordinator", "admin"}, csrf=True)
                if user:
                    self.create_plan(int(parsed.path.split("/")[3]), payload, user)
            elif re.fullmatch(r"/api/plans/\d+/update", parsed.path):
                user = self.require_user({"coordinator", "admin"}, csrf=True)
                if user:
                    self.update_plan(int(parsed.path.split("/")[3]), payload, user)
            elif re.fullmatch(r"/api/plans/\d+/submit", parsed.path):
                user = self.require_user({"coordinator", "admin"}, csrf=True)
                if user:
                    self.submit_plan(int(parsed.path.split("/")[3]), user)
            elif re.fullmatch(r"/api/plans/\d+/review", parsed.path):
                user = self.require_user({"dean", "admin"}, csrf=True)
                if user:
                    self.review_plan(int(parsed.path.split("/")[3]), payload, user)
            elif re.fullmatch(r"/api/plans/\d+/tasks", parsed.path):
                user = self.require_user({"coordinator", "admin"}, csrf=True)
                if user:
                    self.create_task(int(parsed.path.split("/")[3]), payload, user)
            elif re.fullmatch(r"/api/clubs/\d+/events", parsed.path):
                user = self.require_user({"coordinator", "admin"}, csrf=True)
                if user:
                    self.create_event(int(parsed.path.split("/")[3]), payload, user)
            elif parsed.path == "/api/elections":
                user = self.require_user({"dean", "admin"}, csrf=True)
                if user:
                    self.create_election(payload, user)
            elif re.fullmatch(r"/api/elections/\d+/candidates", parsed.path):
                user = self.require_user({"student"}, csrf=True)
                if user:
                    self.submit_candidate(int(parsed.path.split("/")[3]), payload, user)
            elif re.fullmatch(r"/api/elections/\d+/candidates/\d+/review", parsed.path):
                user = self.require_user({"dean", "admin"}, csrf=True)
                if user:
                    parts = parsed.path.split("/")
                    self.review_candidate(int(parts[3]), int(parts[5]), payload, user)
            elif re.fullmatch(r"/api/elections/\d+/open", parsed.path):
                user = self.require_user({"dean", "admin"}, csrf=True)
                if user:
                    self.open_election(int(parsed.path.split("/")[3]), user)
            elif re.fullmatch(r"/api/elections/\d+/vote", parsed.path):
                user = self.require_user({"student"}, csrf=True)
                if user:
                    self.cast_vote(int(parsed.path.split("/")[3]), payload, user)
            elif re.fullmatch(r"/api/elections/\d+/close", parsed.path):
                user = self.require_user({"dean", "admin"}, csrf=True)
                if user:
                    self.close_election(int(parsed.path.split("/")[3]), user)
            elif re.fullmatch(r"/api/elections/\d+/publish", parsed.path):
                user = self.require_user({"dean", "admin"}, csrf=True)
                if user:
                    self.publish_election(int(parsed.path.split("/")[3]), user)
            elif parsed.path == "/api/members":
                if not self.require_user({"admin"}, csrf=True):
                    return
                self.create_member(payload)
            elif parsed.path == "/api/reports":
                user = self.require_user({"coordinator", "admin"}, csrf=True)
                if not user:
                    return
                self.create_report(payload, user)
            elif re.fullmatch(r"/api/reports/\d+/approve", parsed.path):
                user = self.require_user({"dean", "admin"}, csrf=True)
                if not user:
                    return
                self.review_report(int(parsed.path.split("/")[3]), {**payload, "decision": "approved"}, user)
            elif re.fullmatch(r"/api/reports/\d+/review", parsed.path):
                user = self.require_user({"dean", "admin"}, csrf=True)
                if user:
                    self.review_report(int(parsed.path.split("/")[3]), payload, user)
            elif re.fullmatch(r"/api/reports/\d+/update", parsed.path):
                user = self.require_user({"coordinator", "admin"}, csrf=True)
                if user:
                    self.update_report(int(parsed.path.split("/")[3]), payload, user)
            else:
                self.send_json(404, {"error": "API manzili topilmadi."})
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            self.send_json(400, {"error": str(error) or "So‘rov formati noto‘g‘ri."})
        except sqlite3.IntegrityError:
            self.send_json(409, {"error": "Email, talabalik raqami yoki boshqa noyob qiymat avval ishlatilgan."})

    def save_verification_photo(self, data_url: str) -> str:
        match = re.fullmatch(r"data:(image/(?:jpeg|png|webp|gif));base64,([A-Za-z0-9+/=]+)", data_url)
        if not match:
            raise ValueError("Tasdiqlash uchun JPEG, PNG, WEBP yoki GIF rasm yuklang.")
        content_type, encoded = match.groups()
        content = base64.b64decode(encoded, validate=True)
        if not content or len(content) > MAX_IMAGE_BYTES:
            raise ValueError("Tasdiqlash rasmi 5 MB dan kichik bo‘lishi kerak.")
        signatures = {
            "image/jpeg": content.startswith(b"\xff\xd8\xff"),
            "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/webp": content.startswith(b"RIFF") and content[8:12] == b"WEBP",
            "image/gif": content.startswith((b"GIF87a", b"GIF89a")),
        }
        if not signatures[content_type]:
            raise ValueError("Rasm fayli formati MIME turiga mos kelmadi.")
        filename = f"{uuid.uuid4().hex}{IMAGE_TYPES[content_type]}"
        (VERIFICATION_DIR / filename).write_bytes(content)
        return filename

    def register_student(self, payload: dict) -> None:
        email = str(payload.get("email", "")).strip().lower()
        password = str(payload.get("password", ""))
        display_name = str(payload.get("display_name", "")).strip()
        student_number = str(payload.get("student_number", "")).strip()
        faculty = str(payload.get("faculty", "")).strip()
        study_group = str(payload.get("study_group", "")).strip()
        photo = payload.get("verification_photo", "")
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise ValueError("To‘g‘ri email manzil kiriting.")
        if len(password) < 12 or len(password) > 128:
            raise ValueError("Parol kamida 12 ta belgidan iborat bo‘lishi kerak.")
        if not all((display_name, student_number, faculty, study_group)):
            raise ValueError("F.I.Sh., talabalik raqami, fakultet va guruh majburiy.")
        if payload.get("photo_policy_ack") is not True:
            raise ValueError("Talabalik rasmi bo‘yicha ko‘rsatmalarni tasdiqlang.")
        photo_filename = self.save_verification_photo(str(photo))
        created_at = now_utc().isoformat()
        try:
            with database() as db:
                cursor = db.execute(
                    "INSERT INTO users (email,password_hash,display_name,status,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                    (email, password_hash(password), display_name, "pending_verification", created_at, created_at),
                )
                verification = db.execute(
                    """INSERT INTO student_verifications
                       (user_id,student_number,faculty,study_group,verification_photo_path,photo_policy_ack_at,status,created_at)
                       VALUES (?,?,?,?,?,?,'pending',?)""",
                    (cursor.lastrowid, student_number, faculty, study_group, photo_filename, created_at, created_at),
                )
                append_audit_log(db, cursor.lastrowid, "student.verification_submitted", "student_verification",
                                 verification.lastrowid, after={"status": "pending"})
        except Exception:
            (VERIFICATION_DIR / photo_filename).unlink(missing_ok=True)
            raise
        self.send_json(201, {"status": "pending_verification", "message": "Ariza dekanat ko‘rib chiqishiga yuborildi."})

    def login(self, payload: dict) -> None:
        email = str(payload.get("email", "")).strip().lower()
        password = str(payload.get("password", ""))
        with database() as db:
            user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if not user or user["status"] in {"rejected", "suspended"} or not verify_password(password, user["password_hash"]):
                self.send_json(401, {"error": "Email yoki parol noto‘g‘ri."})
                return
            token = secrets.token_urlsafe(32)
            csrf_token = secrets.token_urlsafe(32)
            expires_at = (now_utc() + SESSION_TTL).isoformat()
            created_at = now_utc().isoformat()
            db.execute(
                "INSERT INTO auth_sessions (token_hash,csrf_hash,user_id,created_at,expires_at) VALUES (?,?,?,?,?)",
                (hashlib.sha256(token.encode("utf-8")).hexdigest(), hashlib.sha256(csrf_token.encode("utf-8")).hexdigest(), user["id"], created_at, expires_at),
            )
            db.execute("UPDATE users SET last_login_at=?,updated_at=? WHERE id=?", (created_at, created_at, user["id"]))
            append_audit_log(db, user["id"], "auth.login", "user", user["id"], after={"status": user["status"]})
            roles = db.execute("SELECT role_key FROM user_roles WHERE user_id=? ORDER BY role_key", (user["id"],)).fetchall()
        cookie = f"{SESSION_COOKIE}={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age={int(SESSION_TTL.total_seconds())}"
        self.send_json(200, {
            "user": {"id": user["id"], "email": email, "display_name": user["display_name"],
                     "status": user["status"], "roles": [row["role_key"] for row in roles]},
            "csrf_token": csrf_token,
        }, {"Set-Cookie": cookie})

    def logout(self) -> None:
        user = self.require_user(csrf=True)
        if not user:
            return
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        token = cookie[SESSION_COOKIE].value
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with database() as db:
            db.execute("UPDATE auth_sessions SET revoked_at=? WHERE token_hash=?", (now_utc().isoformat(), token_hash))
            append_audit_log(db, user["id"], "auth.logout", "user", user["id"])
        self.send_json(200, {"ok": True}, {"Set-Cookie": f"{SESSION_COOKIE}=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"})

    def update_settings(self, payload: dict) -> None:
        user = self.require_user(csrf=True)
        if not user:
            return
        display_name = str(payload.get("display_name", user["display_name"])).strip()
        locale = str(payload.get("locale", "uz"))
        notifications = payload.get("email_notifications", True)
        if not display_name or locale not in {"uz", "ru"} or not isinstance(notifications, bool):
            raise ValueError("Profil sozlamalari noto‘g‘ri.")
        photo_path = None
        if payload.get("profile_photo"):
            photo_path = self.save_images([payload["profile_photo"]])[0]
        updated_at = now_utc().isoformat()
        with database() as db:
            before = dict(db.execute("SELECT display_name,profile_photo_path FROM users WHERE id=?", (user["id"],)).fetchone())
            db.execute("UPDATE users SET display_name=?,profile_photo_path=COALESCE(?,profile_photo_path),updated_at=? WHERE id=?", (display_name, photo_path, updated_at, user["id"]))
            db.execute(
                "INSERT INTO user_preferences (user_id,locale,email_notifications,updated_at) VALUES (?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET locale=excluded.locale,email_notifications=excluded.email_notifications,updated_at=excluded.updated_at",
                (user["id"], locale, int(notifications), updated_at),
            )
            append_audit_log(db, user["id"], "profile.settings_updated", "user", user["id"], before=before,
                             after={"display_name": display_name, "locale": locale, "email_notifications": notifications})
        self.send_json(200, {"ok": True})

    def change_password(self, payload: dict) -> None:
        user = self.require_user(csrf=True)
        if not user:
            return
        current_password = str(payload.get("current_password", ""))
        new_password = str(payload.get("new_password", ""))
        if len(new_password) < 12 or len(new_password) > 128:
            raise ValueError("Yangi parol kamida 12 ta belgidan iborat bo‘lishi kerak.")
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        token_hash = hashlib.sha256(cookie[SESSION_COOKIE].value.encode("utf-8")).hexdigest()
        updated_at = now_utc().isoformat()
        with database() as db:
            stored = db.execute("SELECT password_hash FROM users WHERE id=?", (user["id"],)).fetchone()
            if not stored or not verify_password(current_password, stored["password_hash"]):
                self.send_json(403, {"error": "Joriy parol noto‘g‘ri."})
                return
            db.execute("UPDATE users SET password_hash=?,updated_at=? WHERE id=?", (password_hash(new_password), updated_at, user["id"]))
            db.execute("UPDATE auth_sessions SET revoked_at=? WHERE user_id=? AND token_hash<>? AND revoked_at IS NULL", (updated_at, user["id"], token_hash))
            append_audit_log(db, user["id"], "auth.password_changed", "user", user["id"])
        self.send_json(200, {"ok": True})

    def review_verification(self, verification_id: int, payload: dict) -> None:
        reviewer = self.require_user({"dean", "admin"}, csrf=True)
        if not reviewer:
            return
        decision = payload.get("decision")
        note = str(payload.get("note", "")).strip()
        if decision not in {"approved", "rejected"}:
            raise ValueError("Qaror approved yoki rejected bo‘lishi kerak.")
        with database() as db:
            verification = db.execute("SELECT * FROM student_verifications WHERE id=?", (verification_id,)).fetchone()
            if not verification:
                self.send_json(404, {"error": "Verifikatsiya arizasi topilmadi."})
                return
            if verification["status"] != "pending":
                self.send_json(409, {"error": "Bu ariza avval ko‘rib chiqilgan."})
                return
            reviewed_at = now_utc().isoformat()
            user_status = "verified" if decision == "approved" else "rejected"
            db.execute(
                "UPDATE student_verifications SET status=?,reviewed_by=?,review_note=?,reviewed_at=? WHERE id=?",
                (decision, reviewer["id"], note, reviewed_at, verification_id),
            )
            db.execute("UPDATE users SET status=?,updated_at=? WHERE id=?", (user_status, reviewed_at, verification["user_id"]))
            if decision == "approved":
                db.execute(
                    "INSERT OR IGNORE INTO user_roles (user_id,role_key,granted_by,granted_at) VALUES (?,'student',?,?)",
                    (verification["user_id"], reviewer["id"], reviewed_at),
                )
            append_audit_log(db, reviewer["id"], f"student.verification_{decision}", "student_verification",
                             verification_id, before={"status": "pending"}, after={"status": decision, "note": note})
        self.send_json(200, {"ok": True, "status": decision})

    def can_manage_club(self, db: sqlite3.Connection, user: dict, club_id: int) -> bool:
        if "admin" in user["roles"]:
            return True
        if "coordinator" not in user["roles"]:
            return False
        membership = db.execute(
            "SELECT 1 FROM club_memberships WHERE club_id=? AND user_id=? AND membership_role='coordinator' AND status='active'",
            (club_id, user["id"]),
        ).fetchone()
        return membership is not None

    def create_club(self, payload: dict, user: dict) -> None:
        slug = str(payload.get("slug", "")).strip().lower()
        name = str(payload.get("name", "")).strip()
        category = str(payload.get("category", "")).strip()
        description = str(payload.get("description", "")).strip()
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug) or not name or not category:
            raise ValueError("Klub slug, nomi va yo‘nalishi majburiy; slug lotin harflari, son va tire bilan yoziladi.")
        with database() as db:
            now = now_utc().isoformat()
            cursor = db.execute(
                "INSERT INTO clubs (slug,name,description,category,status,created_by,created_at,updated_at) VALUES (?,?,?,?, 'active',?,?,?)",
                (slug, name, description, category, user["id"], now, now),
            )
            append_audit_log(db, user["id"], "club.created", "club", cursor.lastrowid,
                             after={"slug": slug, "name": name, "category": category})
        self.send_json(201, {"ok": True, "id": cursor.lastrowid})

    def set_user_roles(self, target_user_id: int, payload: dict, actor: dict) -> None:
        requested = payload.get("roles")
        allowed_roles = {"student", "coordinator", "dean", "admin"}
        if not isinstance(requested, list) or not requested or not set(requested).issubset(allowed_roles):
            raise ValueError("Kamida bitta haqiqiy rol tanlang.")
        roles = sorted(set(requested))
        with database() as db:
            target = db.execute("SELECT id,status FROM users WHERE id=?", (target_user_id,)).fetchone()
            if not target:
                self.send_json(404, {"error": "Foydalanuvchi topilmadi."})
                return
            if "student" in roles and target["status"] != "verified":
                self.send_json(409, {"error": "Student roli faqat tasdiqlangan foydalanuvchiga beriladi."})
                return
            old_roles = [row[0] for row in db.execute("SELECT role_key FROM user_roles WHERE user_id=? ORDER BY role_key", (target_user_id,))]
            if "admin" in old_roles and "admin" not in roles:
                admin_count = db.execute("SELECT COUNT(*) FROM user_roles WHERE role_key='admin'").fetchone()[0]
                if admin_count <= 1:
                    self.send_json(409, {"error": "Oxirgi admin rolini olib bo‘lmaydi."})
                    return
            db.execute("DELETE FROM user_roles WHERE user_id=?", (target_user_id,))
            granted_at = now_utc().isoformat()
            db.executemany(
                "INSERT INTO user_roles (user_id,role_key,granted_by,granted_at) VALUES (?,?,?,?)",
                [(target_user_id, role, actor["id"], granted_at) for role in roles],
            )
            append_audit_log(db, actor["id"], "user.roles_updated", "user", target_user_id,
                             before={"roles": old_roles}, after={"roles": roles})
        self.send_json(200, {"ok": True, "roles": roles})

    def apply_to_club(self, club_id: int) -> None:
        student = self.require_user({"student"}, csrf=True)
        if not student:
            return
        if student["status"] != "verified":
            self.send_json(403, {"error": "Faqat verifikatsiyadan o‘tgan SOM talabalari klubga ariza bera oladi."})
            return
        with database() as db:
            if not db.execute("SELECT 1 FROM clubs WHERE id=? AND status='active'", (club_id,)).fetchone():
                self.send_json(404, {"error": "Faol klub topilmadi."})
                return
            old = db.execute("SELECT status FROM club_memberships WHERE club_id=? AND user_id=?", (club_id, student["id"])).fetchone()
            if old and old["status"] in {"pending", "active"}:
                self.send_json(409, {"error": "Klubga ariza avval yuborilgan yoki a’zolik faol."})
                return
            now = now_utc().isoformat()
            db.execute(
                """INSERT INTO club_memberships (club_id,user_id,membership_role,status,applied_at)
                   VALUES (?,?,'member','pending',?)
                   ON CONFLICT(club_id,user_id) DO UPDATE SET membership_role='member',status='pending',applied_at=excluded.applied_at,decided_by=NULL,decided_at=NULL""",
                (club_id, student["id"], now),
            )
            append_audit_log(db, student["id"], "club.membership_applied", "club", club_id,
                             after={"status": "pending"})
        self.send_json(201, {"ok": True, "status": "pending"})

    def review_membership(self, club_id: int, target_user_id: int, payload: dict, user: dict) -> None:
        decision = payload.get("decision")
        if decision not in {"approved", "rejected"}:
            raise ValueError("Klub arizasi qarori approved yoki rejected bo‘lishi kerak.")
        with database() as db:
            if not self.can_manage_club(db, user, club_id):
                self.send_json(403, {"error": "Bu klub a’zolik arizalarini ko‘rib chiqish vakolati yo‘q."})
                return
            membership = db.execute("SELECT status FROM club_memberships WHERE club_id=? AND user_id=?", (club_id, target_user_id)).fetchone()
            if not membership:
                self.send_json(404, {"error": "A’zolik arizasi topilmadi."})
                return
            if membership["status"] != "pending":
                self.send_json(409, {"error": "A’zolik arizasi avval ko‘rib chiqilgan."})
                return
            status = "active" if decision == "approved" else "rejected"
            now = now_utc().isoformat()
            db.execute("UPDATE club_memberships SET status=?,decided_by=?,decided_at=? WHERE club_id=? AND user_id=?", (status, user["id"], now, club_id, target_user_id))
            append_audit_log(db, user["id"], f"club.membership_{decision}", "club_membership", f"{club_id}:{target_user_id}",
                             before={"status": "pending"}, after={"status": status})
        self.send_json(200, {"ok": True, "status": status})

    def plan_snapshot(self, db: sqlite3.Connection, plan_id: int) -> dict:
        row = db.execute("SELECT * FROM club_plans WHERE id=?", (plan_id,)).fetchone()
        return dict(row) if row else {}

    def create_plan(self, club_id: int, payload: dict, user: dict) -> None:
        period_type = str(payload.get("period_type", "weekly"))
        start = str(payload.get("period_start", ""))
        end = str(payload.get("period_end", ""))
        title = str(payload.get("title", "")).strip()
        objectives = str(payload.get("objectives", "")).strip()
        if period_type not in {"weekly", "monthly"} or not title:
            raise ValueError("Reja turi va sarlavhasi majburiy.")
        try:
            valid_dates = datetime.fromisoformat(start) <= datetime.fromisoformat(end)
        except ValueError:
            valid_dates = False
        if not valid_dates:
            raise ValueError("Reja sanalari ISO formatda va to‘g‘ri ketma-ketlikda bo‘lishi kerak.")
        with database() as db:
            if not self.can_manage_club(db, user, club_id):
                self.send_json(403, {"error": "Bu klubda faol koordinator vakolati yo‘q."})
                return
            now = now_utc().isoformat()
            cursor = db.execute(
                "INSERT INTO club_plans (club_id,created_by,period_type,period_start,period_end,title,objectives,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,'draft',?,?)",
                (club_id, user["id"], period_type, start, end, title, objectives, now, now),
            )
            plan_id = cursor.lastrowid
            snapshot = self.plan_snapshot(db, plan_id)
            db.execute(
                "INSERT INTO plan_versions (plan_id,version_number,snapshot_json,changed_by,change_note,created_at) VALUES (?,1,?,?,?,?)",
                (plan_id, json.dumps(snapshot, ensure_ascii=False, sort_keys=True), user["id"], "Boshlang‘ich reja", now),
            )
            append_audit_log(db, user["id"], "plan.created", "club_plan", plan_id, after=snapshot)
        self.send_json(201, {"ok": True, "id": plan_id})

    def update_plan(self, plan_id: int, payload: dict, user: dict) -> None:
        with database() as db:
            before = self.plan_snapshot(db, plan_id)
            if not before:
                self.send_json(404, {"error": "Reja topilmadi."})
                return
            if not self.can_manage_club(db, user, before["club_id"]):
                self.send_json(403, {"error": "Bu rejani o‘zgartirish vakolati yo‘q."})
                return
            if before["status"] not in {"draft", "changes_requested"}:
                self.send_json(409, {"error": "Faqat draft yoki tuzatish so‘ralgan rejani o‘zgartirish mumkin."})
                return
            updated = {
                "period_type": str(payload.get("period_type", before["period_type"])),
                "period_start": str(payload.get("period_start", before["period_start"])),
                "period_end": str(payload.get("period_end", before["period_end"])),
                "title": str(payload.get("title", before["title"])).strip(),
                "objectives": str(payload.get("objectives", before["objectives"])).strip(),
            }
            if updated["period_type"] not in {"weekly", "monthly"} or not updated["title"]:
                raise ValueError("Reja turi yoki sarlavhasi noto‘g‘ri.")
            try:
                if datetime.fromisoformat(updated["period_end"]) < datetime.fromisoformat(updated["period_start"]):
                    raise ValueError("Tugash sanasi boshlanish sanasidan oldin bo‘la olmaydi.")
            except ValueError as error:
                raise ValueError("Reja sanalari noto‘g‘ri.") from error
            now = now_utc().isoformat()
            version = db.execute("SELECT COALESCE(MAX(version_number),0)+1 FROM plan_versions WHERE plan_id=?", (plan_id,)).fetchone()[0]
            db.execute(
                "INSERT INTO plan_versions (plan_id,version_number,snapshot_json,changed_by,change_note,created_at) VALUES (?,?,?,?,?,?)",
                (plan_id, version, json.dumps(before, ensure_ascii=False, sort_keys=True), user["id"], str(payload.get("change_note", "")), now),
            )
            db.execute(
                "UPDATE club_plans SET period_type=?,period_start=?,period_end=?,title=?,objectives=?,updated_at=? WHERE id=?",
                (*updated.values(), now, plan_id),
            )
            after = self.plan_snapshot(db, plan_id)
            append_audit_log(db, user["id"], "plan.updated", "club_plan", plan_id, before=before, after=after)
        self.send_json(200, {"ok": True, "version": version})

    def submit_plan(self, plan_id: int, user: dict) -> None:
        with database() as db:
            before = self.plan_snapshot(db, plan_id)
            if not before:
                self.send_json(404, {"error": "Reja topilmadi."})
                return
            if not self.can_manage_club(db, user, before["club_id"]):
                self.send_json(403, {"error": "Bu rejani yuborish vakolati yo‘q."})
                return
            if before["status"] not in {"draft", "changes_requested"}:
                self.send_json(409, {"error": "Rejani hozir yuborib bo‘lmaydi."})
                return
            now = now_utc().isoformat()
            db.execute("UPDATE club_plans SET status='submitted',updated_at=? WHERE id=?", (now, plan_id))
            append_audit_log(db, user["id"], "plan.submitted", "club_plan", plan_id, before={"status": before["status"]}, after={"status": "submitted"})
        self.send_json(200, {"ok": True, "status": "submitted"})

    def review_plan(self, plan_id: int, payload: dict, user: dict) -> None:
        decision = payload.get("decision")
        if decision not in {"approved", "rejected", "changes_requested"}:
            raise ValueError("Reja qarori noto‘g‘ri.")
        with database() as db:
            before = self.plan_snapshot(db, plan_id)
            if not before:
                self.send_json(404, {"error": "Reja topilmadi."})
                return
            if before["status"] != "submitted":
                self.send_json(409, {"error": "Faqat yuborilgan reja ko‘rib chiqiladi."})
                return
            status = "approved" if decision == "approved" else "rejected" if decision == "rejected" else "changes_requested"
            now = now_utc().isoformat()
            db.execute("UPDATE club_plans SET status=?,reviewed_by=?,reviewed_at=?,review_note=?,updated_at=? WHERE id=?", (status, user["id"], now, str(payload.get("note", "")), now, plan_id))
            append_audit_log(db, user["id"], f"plan.{decision}", "club_plan", plan_id, before={"status": "submitted"}, after={"status": status, "note": str(payload.get("note", ""))})
        self.send_json(200, {"ok": True, "status": status})

    def create_task(self, plan_id: int, payload: dict, user: dict) -> None:
        title = str(payload.get("title", "")).strip()
        if not title:
            raise ValueError("Vazifa nomi majburiy.")
        with database() as db:
            plan = db.execute("SELECT club_id FROM club_plans WHERE id=?", (plan_id,)).fetchone()
            if not plan:
                self.send_json(404, {"error": "Reja topilmadi."})
                return
            if not self.can_manage_club(db, user, plan["club_id"]):
                self.send_json(403, {"error": "Vazifa yaratish vakolati yo‘q."})
                return
            assigned_to = payload.get("assigned_to")
            if assigned_to and not db.execute("SELECT 1 FROM club_memberships WHERE club_id=? AND user_id=? AND status='active'", (plan["club_id"], assigned_to)).fetchone():
                raise ValueError("Vazifa faqat klubning faol a’zosiga beriladi.")
            now = now_utc().isoformat()
            cursor = db.execute(
                "INSERT INTO plan_tasks (plan_id,title,description,assigned_to,due_at,created_by,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (plan_id, title, str(payload.get("description", "")), assigned_to, payload.get("due_at"), user["id"], now, now),
            )
            append_audit_log(db, user["id"], "plan.task_created", "plan_task", cursor.lastrowid, after={"plan_id": plan_id, "title": title, "assigned_to": assigned_to})
        self.send_json(201, {"ok": True, "id": cursor.lastrowid})

    def create_event(self, club_id: int, payload: dict, user: dict) -> None:
        title = str(payload.get("title", "")).strip()
        starts_at = str(payload.get("starts_at", "")).strip()
        ends_at = str(payload.get("ends_at", "")).strip()
        if not title:
            raise ValueError("Tadbir nomi majburiy.")
        try:
            if datetime.fromisoformat(ends_at) <= datetime.fromisoformat(starts_at):
                raise ValueError("Tadbir tugash vaqti boshlanishdan keyin bo‘lishi kerak.")
        except ValueError as error:
            raise ValueError("Tadbir sanalari ISO formatda bo‘lishi kerak.") from error
        with database() as db:
            if not self.can_manage_club(db, user, club_id):
                self.send_json(403, {"error": "Bu klub taqvimini boshqarish vakolati yo‘q."})
                return
            now = now_utc().isoformat()
            cursor = db.execute(
                "INSERT INTO club_events (club_id,plan_id,title,description,starts_at,ends_at,location,created_by,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (club_id, payload.get("plan_id"), title, str(payload.get("description", "")), starts_at, ends_at, str(payload.get("location", "")), user["id"], now, now),
            )
            append_audit_log(db, user["id"], "club.event_created", "club_event", cursor.lastrowid, after={"club_id": club_id, "title": title})
        self.send_json(201, {"ok": True, "id": cursor.lastrowid})

    def create_election(self, payload: dict, user: dict) -> None:
        try:
            club_id = int(payload.get("club_id"))
            starts_at = datetime.fromisoformat(str(payload.get("starts_at", "")))
            ends_at = datetime.fromisoformat(str(payload.get("ends_at", "")))
        except (TypeError, ValueError):
            raise ValueError("Klub va ISO formatdagi saylov sanalari majburiy.") from None
        if starts_at.tzinfo is None or ends_at.tzinfo is None or ends_at <= starts_at:
            raise ValueError("Saylov sanalari timezone bilan va to‘g‘ri ketma-ketlikda berilishi kerak.")
        position = str(payload.get("position_title", "")).strip()
        if not position:
            raise ValueError("Saylov lavozimi majburiy.")
        with database() as db:
            if not db.execute("SELECT 1 FROM clubs WHERE id=? AND status='active'", (club_id,)).fetchone():
                self.send_json(404, {"error": "Faol klub topilmadi."})
                return
            now = now_utc().isoformat()
            cursor = db.execute(
                "INSERT INTO elections (club_id,position_title,starts_at,ends_at,status,created_by,created_at) VALUES (?,?,?,?,'candidate_review',?,?)",
                (club_id, position, starts_at.isoformat(), ends_at.isoformat(), user["id"], now),
            )
            append_audit_log(db, user["id"], "election.created", "election", cursor.lastrowid,
                             after={"club_id": club_id, "position_title": position, "status": "candidate_review"})
        self.send_json(201, {"ok": True, "id": cursor.lastrowid})

    def submit_candidate(self, election_id: int, payload: dict, user: dict) -> None:
        statement = str(payload.get("statement", "")).strip()
        if not statement:
            raise ValueError("Nomzod dasturi majburiy.")
        with database() as db:
            election = db.execute("SELECT club_id,status,starts_at FROM elections WHERE id=?", (election_id,)).fetchone()
            if not election or election["status"] != "candidate_review" or now_utc() >= datetime.fromisoformat(election["starts_at"]):
                self.send_json(409, {"error": "Bu saylovga nomzodlik muddati yopiq."})
                return
            membership = db.execute(
                "SELECT 1 FROM club_memberships WHERE club_id=? AND user_id=? AND status='active'",
                (election["club_id"], user["id"]),
            ).fetchone()
            if user["status"] != "verified" or not membership:
                self.send_json(403, {"error": "Faqat verifikatsiyadan o‘tgan klub a’zosi nomzod bo‘la oladi."})
                return
            now = now_utc().isoformat()
            cursor = db.execute(
                "INSERT INTO election_candidates (election_id,user_id,statement,status,created_at) VALUES (?,?,?,'pending',?)",
                (election_id, user["id"], statement, now),
            )
            append_audit_log(db, user["id"], "election.candidate_submitted", "election_candidate", cursor.lastrowid,
                             after={"election_id": election_id, "status": "pending"})
        self.send_json(201, {"ok": True, "status": "pending"})

    def review_candidate(self, election_id: int, candidate_id: int, payload: dict, user: dict) -> None:
        decision = payload.get("decision")
        if decision not in {"approved", "rejected"}:
            raise ValueError("Nomzod qarori approved yoki rejected bo‘lishi kerak.")
        with database() as db:
            candidate = db.execute(
                "SELECT status FROM election_candidates WHERE id=? AND election_id=?",
                (candidate_id, election_id),
            ).fetchone()
            if not candidate:
                self.send_json(404, {"error": "Nomzod topilmadi."})
                return
            if candidate["status"] != "pending":
                self.send_json(409, {"error": "Nomzod avval ko‘rib chiqilgan."})
                return
            now = now_utc().isoformat()
            db.execute(
                "UPDATE election_candidates SET status=?,reviewed_by=?,reviewed_at=?,review_note=? WHERE id=?",
                (decision, user["id"], now, str(payload.get("note", "")), candidate_id),
            )
            append_audit_log(db, user["id"], f"election.candidate_{decision}", "election_candidate", candidate_id,
                             before={"status": "pending"}, after={"status": decision, "election_id": election_id})
        self.send_json(200, {"ok": True, "status": decision})

    def open_election(self, election_id: int, user: dict) -> None:
        with database() as db:
            election = db.execute("SELECT status,starts_at,ends_at FROM elections WHERE id=?", (election_id,)).fetchone()
            if not election:
                self.send_json(404, {"error": "Saylov topilmadi."})
                return
            now = now_utc()
            if election["status"] != "candidate_review" or datetime.fromisoformat(election["starts_at"]) > now or datetime.fromisoformat(election["ends_at"]) <= now:
                self.send_json(409, {"error": "Saylov muddati yoki nomzodlar holati ochishga mos emas."})
                return
            if not db.execute("SELECT 1 FROM election_candidates WHERE election_id=? AND status='approved' LIMIT 1", (election_id,)).fetchone():
                self.send_json(409, {"error": "Saylovni ochishdan oldin kamida bitta nomzodni tasdiqlang."})
                return
            db.execute("UPDATE elections SET status='open',approved_by=? WHERE id=?", (user["id"], election_id))
            append_audit_log(db, user["id"], "election.opened", "election", election_id,
                             before={"status": "candidate_review"}, after={"status": "open"})
        self.send_json(200, {"ok": True, "status": "open"})

    def cast_vote(self, election_id: int, payload: dict, user: dict) -> None:
        try:
            candidate_id = int(payload.get("candidate_id"))
        except (TypeError, ValueError):
            raise ValueError("Nomzod tanlashingiz kerak.") from None
        now = now_utc()
        with database() as db:
            election = db.execute("SELECT status,starts_at,ends_at FROM elections WHERE id=?", (election_id,)).fetchone()
            candidate = db.execute(
                "SELECT 1 FROM election_candidates WHERE id=? AND election_id=? AND status='approved'",
                (candidate_id, election_id),
            ).fetchone()
            if not election or election["status"] != "open" or now < datetime.fromisoformat(election["starts_at"]) or now >= datetime.fromisoformat(election["ends_at"]):
                self.send_json(409, {"error": "Saylov hozir ovoz berish uchun ochiq emas."})
                return
            if user["status"] != "verified" or not candidate:
                self.send_json(403, {"error": "Tasdiqlangan talaba va saylovdagi tasdiqlangan nomzod talab qilinadi."})
                return
            try:
                db.execute("INSERT INTO election_voters (election_id,user_id) VALUES (?,?)", (election_id, user["id"]))
            except sqlite3.IntegrityError:
                self.send_json(409, {"error": "Bu saylovda ovoz berilgani qayd etilgan."})
                return
            old_count = db.execute("SELECT COALESCE(vote_count,0) FROM election_tallies WHERE election_id=? AND candidate_id=?", (election_id, candidate_id)).fetchone()
            count = old_count[0] if old_count else 0
            db.execute(
                "INSERT INTO election_tallies (election_id,candidate_id,vote_count,updated_at) VALUES (?,?,1,?) ON CONFLICT(election_id,candidate_id) DO UPDATE SET vote_count=election_tallies.vote_count+1,updated_at=excluded.updated_at",
                (election_id, candidate_id, now.isoformat()),
            )
            total = db.execute("SELECT SUM(vote_count) FROM election_tallies WHERE election_id=?", (election_id,)).fetchone()[0]
            append_audit_log(db, None, "election.aggregate_tally_updated", "election", election_id,
                             before={"total_votes": total - 1}, after={"total_votes": total})
        self.send_json(201, {"ok": True, "message": "Ovozingiz maxfiy tarzda qayd etildi."})

    def close_election(self, election_id: int, user: dict) -> None:
        with database() as db:
            election = db.execute("SELECT status,ends_at FROM elections WHERE id=?", (election_id,)).fetchone()
            if not election:
                self.send_json(404, {"error": "Saylov topilmadi."})
                return
            if election["status"] != "open" or now_utc() < datetime.fromisoformat(election["ends_at"]):
                self.send_json(409, {"error": "Saylov faqat ovoz berish muddati tugagach yopiladi."})
                return
            db.execute("UPDATE elections SET status='closed' WHERE id=?", (election_id,))
            append_audit_log(db, user["id"], "election.closed", "election", election_id,
                             before={"status": "open"}, after={"status": "closed"})
        self.send_json(200, {"ok": True, "status": "closed"})

    def publish_election(self, election_id: int, user: dict) -> None:
        with database() as db:
            election = db.execute("SELECT status FROM elections WHERE id=?", (election_id,)).fetchone()
            if not election:
                self.send_json(404, {"error": "Saylov topilmadi."})
                return
            if election["status"] != "closed":
                self.send_json(409, {"error": "Faqat yopilgan saylov natijasi e’lon qilinadi."})
                return
            db.execute("UPDATE elections SET status='published' WHERE id=?", (election_id,))
            append_audit_log(db, user["id"], "election.results_published", "election", election_id,
                             before={"status": "closed"}, after={"status": "published"})
        self.send_json(200, {"ok": True, "status": "published"})

    def create_member(self, payload: dict) -> None:
        first = str(payload.get("first", "")).strip()
        last = str(payload.get("last", "")).strip()
        role = str(payload.get("role", "")).strip()
        duty = str(payload.get("duty", "Vazifalar belgilanadi.")).strip()
        photo = payload.get("photo")
        if not first or not last or not role:
            raise ValueError("Ism, familiya va lavozim majburiy.")
        with database() as db:
            if db.execute("SELECT COUNT(*) FROM members").fetchone()[0] >= MAX_MEMBERS:
                self.send_json(409, {"error": f"A’zolar soni belgilangan limitga ({MAX_MEMBERS}) yetdi."})
                return
            if db.execute("SELECT 1 FROM members WHERE name_key=?", (name_key(first, last),)).fetchone():
                self.send_json(409, {"error": "Bu ism-familiya bilan a’zo avval qo‘shilgan."})
                return
            if photo:
                photo = self.save_images([photo])[0]
            db.execute(
                "INSERT INTO members (first_name,last_name,role,duty,kpi,photo,name_key,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (first, last, role, duty, 0, photo, name_key(first, last), datetime.now(timezone.utc).isoformat()),
            )
        self.send_json(201, {"ok": True})
    def remove_member(self, member_id: int) -> None:
        with database() as db:
            cursor = db.execute("DELETE FROM members WHERE id=?", (member_id,))
            if cursor.rowcount == 0:
                self.send_json(404, {"error": "A’zo topilmadi."})
                return
        self.send_json(200, {"ok": True})
    def save_images(self, images: list) -> list[str]:
        if not isinstance(images, list):
            raise ValueError("Rasmlar ro‘yxat shaklida yuborilishi kerak.")
        saved = []
        total_bytes = 0
        for image in images:
            if not isinstance(image, str) or not image.startswith("data:"):
                raise ValueError("Rasm formati noto‘g‘ri.")
            match = re.fullmatch(r"data:(image/(?:jpeg|png|webp|gif));base64,([A-Za-z0-9+/=]+)", image)
            if not match:
                raise ValueError("Faqat JPEG, PNG, WEBP yoki GIF rasmlar qabul qilinadi.")
            content_type, encoded = match.groups()
            content = base64.b64decode(encoded, validate=True)
            total_bytes += len(content)
            if len(content) > MAX_IMAGE_BYTES or total_bytes > MAX_BODY_BYTES:
                raise ValueError("Rasm fayllari hajmi ruxsat etilganidan katta.")
            filename = f"{uuid.uuid4().hex}{IMAGE_TYPES[content_type]}"
            (UPLOAD_DIR / filename).write_bytes(content)
            saved.append(f"/api/uploads/{filename}")
        return saved

    def create_report(self, payload: dict, user: dict) -> None:
        member = str(payload.get("member", "")).strip()
        week = str(payload.get("week", "")).strip()
        event = str(payload.get("event", "")).strip()
        category = str(payload.get("category", "")).strip()
        description = str(payload.get("description", "")).strip()
        if not all((member, week, event, category, description)):
            raise ValueError("Koordinator, hafta, tadbir, yo‘nalish va tavsif majburiy.")
        try:
            score = max(0, min(100, int(payload.get("score", 0))))
        except (TypeError, ValueError):
            raise ValueError("Hisobot balli noto‘g‘ri.") from None
        images = self.save_images(payload.get("images", []))
        proof = bool(payload.get("proof") or images)
        club_id = payload.get("club_id")
        plan_id = payload.get("plan_id")
        with database() as db:
            if "admin" not in user["roles"]:
                try:
                    club_id = int(club_id)
                except (TypeError, ValueError):
                    raise ValueError("Hisobotni klubga biriktirish majburiy.") from None
                if not self.can_manage_club(db, user, club_id):
                    self.send_json(403, {"error": "Bu klub uchun hisobot topshirish vakolati yo‘q."})
                    return
            if plan_id:
                plan = db.execute("SELECT club_id,status FROM club_plans WHERE id=?", (plan_id,)).fetchone()
                if not plan or (club_id and plan["club_id"] != int(club_id)):
                    raise ValueError("Tanlangan reja hisobot klubiga tegishli emas.")
            created_at = now_utc().isoformat()
            db.execute(
                "INSERT INTO reports (member_name,week,event,category,description,score,status,proof,images,created_at,club_id,plan_id,submitted_by,period_type,title) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (member, week, event, category, description, score, "Tekshiruvda", int(proof), json.dumps(images), created_at, club_id, plan_id, user["id"], str(payload.get("period_type", "weekly")), str(payload.get("title", event))),
            )
            report_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            snapshot = dict(db.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone())
            db.execute("INSERT INTO report_versions (report_id,version_number,snapshot_json,changed_by,change_note,created_at) VALUES (?,1,?,?,?,?)", (report_id, json.dumps(snapshot, ensure_ascii=False, sort_keys=True), user["id"], "Boshlang‘ich hisobot", created_at))
            append_audit_log(db, user["id"], "report.submitted", "report", report_id, after={"club_id": club_id, "plan_id": plan_id, "status": "Tekshiruvda"})
        self.send_json(201, {"ok": True, "id": report_id})

    def update_report(self, report_id: int, payload: dict, user: dict) -> None:
        with database() as db:
            row = db.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
            if not row:
                self.send_json(404, {"error": "Hisobot topilmadi."})
                return
            if row["club_id"] is not None and not self.can_manage_club(db, user, row["club_id"]):
                self.send_json(403, {"error": "Bu hisobotni o‘zgartirish vakolati yo‘q."})
                return
            if row["status"] != "Tuzatish kerak" and "admin" not in user["roles"]:
                self.send_json(409, {"error": "Faqat tuzatish so‘ralgan hisobotni qayta yuborish mumkin."})
                return
            before = dict(row)
            updates = {
                "event": str(payload.get("event", row["event"])).strip(),
                "category": str(payload.get("category", row["category"])).strip(),
                "description": str(payload.get("description", row["description"])).strip(),
                "title": str(payload.get("title", row["title"] or row["event"])).strip(),
            }
            if not all(updates.values()):
                raise ValueError("Hisobot sarlavhasi, yo‘nalishi va tavsifi bo‘sh bo‘lishi mumkin emas.")
            images = self.save_images(payload["images"]) if "images" in payload else json.loads(row["images"])
            now = now_utc().isoformat()
            version = db.execute("SELECT COALESCE(MAX(version_number),0)+1 FROM report_versions WHERE report_id=?", (report_id,)).fetchone()[0]
            db.execute("INSERT INTO report_versions (report_id,version_number,snapshot_json,changed_by,change_note,created_at) VALUES (?,?,?,?,?,?)", (report_id, version, json.dumps(before, ensure_ascii=False, sort_keys=True), user["id"], str(payload.get("change_note", "")), now))
            db.execute("UPDATE reports SET event=?,category=?,description=?,title=?,images=?,proof=?,status='Tekshiruvda',created_at=? WHERE id=?", (updates["event"], updates["category"], updates["description"], updates["title"], json.dumps(images), int(bool(images)), now, report_id))
            append_audit_log(db, user["id"], "report.updated", "report", report_id, before=before, after={**updates, "status": "Tekshiruvda"})
        self.send_json(200, {"ok": True, "version": version})

    def review_report(self, report_id: int, payload: dict, user: dict) -> None:
        decision = payload.get("decision")
        if decision not in {"approved", "rejected", "changes_requested"}:
            raise ValueError("Hisobot qarori noto‘g‘ri.")
        score = payload.get("score")
        if score is not None:
            try:
                score = max(0, min(100, int(score)))
            except (TypeError, ValueError):
                raise ValueError("Hisobot bahosi 0–100 oralig‘ida bo‘lishi kerak.") from None
        status = "Tasdiqlangan" if decision == "approved" else "Tuzatish kerak"
        feedback = str(payload.get("feedback", "")).strip()
        with database() as db:
            row = db.execute("SELECT status FROM reports WHERE id=?", (report_id,)).fetchone()
            if not row:
                self.send_json(404, {"error": "Hisobot topilmadi."})
                return
            if row["status"] == "Tasdiqlangan":
                self.send_json(409, {"error": "Tasdiqlangan hisobot qayta ko‘rib chiqilmaydi."})
                return
            reviewed_at = now_utc().isoformat()
            db.execute("INSERT INTO report_reviews (report_id,reviewer_id,decision,score,feedback,created_at) VALUES (?,?,?,?,?,?)", (report_id, user["id"], decision, score, feedback, reviewed_at))
            db.execute("UPDATE reports SET status=?,score=COALESCE(?,score) WHERE id=?", (status, score, report_id))
            append_audit_log(db, user["id"], f"report.{decision}", "report", report_id, before={"status": row["status"]}, after={"status": status, "score": score, "feedback": feedback})
        self.send_json(200, {"ok": True, "status": status})

    def approve_report(self, report_id: int) -> None:
        with database() as db:
            cursor = db.execute("UPDATE reports SET status='Tasdiqlangan' WHERE id=?", (report_id,))
            if cursor.rowcount == 0:
                self.send_json(404, {"error": "Hisobot topilmadi."})
                return
        self.send_json(200, {"ok": True})
    def rejecte_report(self, report_id: int) -> None:
        with database() as db:
            cursor = db.execute("UPDATE reports SET status='Tuzatish kerak' WHERE id=?", (report_id,))
            if cursor.rowcount == 0:
                self.send_json(404, {"error": "Hisobot topilmadi."})
                return
        self.send_json(200, {"ok": True})

    def log_message(self, format: str, *args) -> None:
        print(f"{self.log_date_time_string()} {format % args}")


def main() -> None:
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Yoshlar kengashi backend: http://{HOST}:{PORT}/main.html")
    print(f"SQLite bazasi: {DB_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer to‘xtatildi.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
