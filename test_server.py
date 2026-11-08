import base64
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import server


class BackendApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        server.DATA_DIR = Path(self.temp_dir.name)
        server.UPLOAD_DIR = server.DATA_DIR / "uploads"
        server.DB_PATH = server.DATA_DIR / "test.sqlite3"
        server.init_db()
        self.httpd = ThreadingHTTPServer((server.HOST, 0), server.Handler)
        self.base_url = f"http://{server.HOST}:{self.httpd.server_port}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join()
        self.temp_dir.cleanup()

    def request(self, path, payload=None, headers=None, include_headers=False):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers={"Content-Type": "application/json", **(headers or {})},
            method="POST" if data is not None else "GET",
        )
        try:
            with urllib.request.urlopen(request) as response:
                result = (response.status, json.loads(response.read().decode("utf-8")))
                return (*result, dict(response.headers)) if include_headers else result
        except urllib.error.HTTPError as error:
            result = (error.code, json.loads(error.read().decode("utf-8")))
            return (*result, dict(error.headers)) if include_headers else result

    def auth_headers(self, role, email=None):
        created_at = server.now_utc().isoformat()
        email = email or f"{role}@example.test"
        with server.database() as db:
            user_id = db.execute(
                "INSERT INTO users (email,password_hash,display_name,status,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                (email, server.password_hash("Test-Password-123!"), role.title(), "verified", created_at, created_at),
            ).lastrowid
            db.execute("INSERT INTO user_roles (user_id,role_key,granted_at) VALUES (?,?,?)", (user_id, role, created_at))
            token = server.secrets.token_urlsafe(32)
            csrf = server.secrets.token_urlsafe(32)
            db.execute(
                "INSERT INTO auth_sessions (token_hash,csrf_hash,user_id,created_at,expires_at) VALUES (?,?,?,?,?)",
                (server.hashlib.sha256(token.encode()).hexdigest(), server.hashlib.sha256(csrf.encode()).hexdigest(), user_id, created_at, (server.now_utc() + server.SESSION_TTL).isoformat()),
            )
        return {"Cookie": f"{server.SESSION_COOKIE}={token}", "X-CSRF-Token": csrf}

    def test_seed_and_duplicate_member_rejection(self):
        status, state = self.request("/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(len(state["members"]), 11)
        self.assertEqual(len(state["reports"]), 1)
        self.assertEqual(state["summary"]["active_clubs"], 0)
        self.assertEqual(state["top_clubs"], [])
        self.assertEqual([item["event"] for item in state["work_history"]], ["Zakovat turniri"])

        status, result = self.request("/api/members", {
            "first": "Jasmina", "last": "Yangiyeva", "role": "Test", "duty": "Test"
        })
        self.assertEqual(status, 401)
        status, result = self.request("/api/members", {
            "first": "Jasmina", "last": "Yangiyeva", "role": "Test", "duty": "Test"
        }, headers=self.auth_headers("admin"))
        self.assertEqual(status, 409)
        self.assertIn("avval qo‘shilgan", result["error"])

    def test_domain_schema_and_audit_immutability(self):
        with server.database() as db:
            tables = {row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({"users", "user_roles", "clubs", "club_plans", "plan_versions", "plan_tasks", "club_events", "report_versions", "report_reviews", "student_verifications", "elections", "election_candidates", "election_voters", "election_ballots", "audit_logs"}.issubset(tables))
            ballot_columns = {row["name"] for row in db.execute("PRAGMA table_info(election_ballots)")}
            self.assertNotIn("user_id", ballot_columns)
            self.assertIsNotNone(db.execute("SELECT name FROM sqlite_master WHERE type='view' AND name='club_rankings'").fetchone())
            db.execute("INSERT INTO audit_logs (action,entity_type,entry_hash,created_at) VALUES ('test','test','hash','test')")
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE audit_logs SET action='changed' WHERE action='test'")
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("DELETE FROM audit_logs WHERE action='test'")

    def test_student_verification_requires_dean_and_grants_student_role(self):
        image_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        photo = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")
        status, result = self.request("/api/auth/register", {
            "email": "student@example.test",
            "password": "Correct-Horse-9!",
            "display_name": "Test Student",
            "student_number": "SOM-1001",
            "faculty": "Test faculty",
            "study_group": "T-01",
            "verification_photo": photo,
            "photo_policy_ack": True,
        })
        self.assertEqual(status, 201)
        self.assertEqual(result["status"], "pending_verification")
        self.assertEqual(self.request("/api/dean/verifications")[0], 401)

        student_login, student_session, student_headers = self.request(
            "/api/auth/login", {"email": "student@example.test", "password": "Correct-Horse-9!"}, include_headers=True
        )
        self.assertEqual(student_login, 200)
        student_cookie = student_headers["Set-Cookie"].split(";", 1)[0]
        student_request_headers = {"Cookie": student_cookie}
        self.assertEqual(student_session["user"]["status"], "pending_verification")
        self.assertEqual(student_session["user"]["roles"], [])
        self.assertEqual(
            self.request("/api/dean/verifications", headers=student_request_headers)[0], 403
        )

        with server.database() as db:
            created_at = server.now_utc().isoformat()
            dean_id = db.execute(
                "INSERT INTO users (email,password_hash,display_name,status,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                ("dean@example.test", server.password_hash("Dean-Password-9!"), "Test Dean", "verified", created_at, created_at),
            ).lastrowid
            db.execute("INSERT INTO user_roles (user_id,role_key,granted_at) VALUES (?,'dean',?)", (dean_id, created_at))
        dean_status, dean_session, dean_headers = self.request(
            "/api/auth/login", {"email": "dean@example.test", "password": "Dean-Password-9!"}, include_headers=True
        )
        self.assertEqual(dean_status, 200)
        dean_cookie = dean_headers["Set-Cookie"].split(";", 1)[0]
        dean_request_headers = {
            "Cookie": dean_cookie,
            "X-CSRF-Token": dean_session["csrf_token"],
        }
        queue_status, queue = self.request("/api/dean/verifications", headers={"Cookie": dean_cookie})
        self.assertEqual(queue_status, 200)
        verification_id = queue["items"][0]["id"]
        photo_request = urllib.request.Request(
            f"{self.base_url}/api/dean/verifications/{verification_id}/photo",
            headers={"Cookie": dean_cookie},
        )
        with urllib.request.urlopen(photo_request) as response:
            self.assertEqual(response.read(), image_bytes)

        denied_status, _ = self.request(
            f"/api/dean/verifications/{verification_id}/review",
            {"decision": "approved"},
            headers=student_request_headers,
        )
        self.assertEqual(denied_status, 403)
        review_status, _ = self.request(
            f"/api/dean/verifications/{verification_id}/review",
            {"decision": "approved", "note": "Tasdiqlandi"},
            headers=dean_request_headers,
        )
        self.assertEqual(review_status, 200)
        _, student_after_review = self.request("/api/auth/me", headers=student_request_headers)
        self.assertEqual(student_after_review["status"], "verified")
        self.assertEqual(student_after_review["roles"], ["student"])
        admin_headers = self.auth_headers("admin")
        role_status, _ = self.request(
            f"/api/admin/users/{student_after_review['id']}/roles",
            {"roles": ["student", "coordinator"]},
            headers=admin_headers,
        )
        self.assertEqual(role_status, 200)
        _, student_after_role_grant = self.request("/api/auth/me", headers=student_request_headers)
        self.assertEqual(student_after_role_grant["roles"], ["coordinator", "student"])
        with server.database() as db:
            admin_id = db.execute("SELECT id FROM users WHERE email='admin@example.test'").fetchone()[0]
        self.assertEqual(self.request(f"/api/admin/users/{admin_id}/roles", {"roles": ["dean"]}, headers=admin_headers)[0], 409)

        self.assertEqual(self.request(
            "/api/auth/logout", {}, headers={**student_request_headers, "X-CSRF-Token": student_session["csrf_token"]}
        )[0], 200)
        self.assertEqual(self.request("/api/auth/me", headers=student_request_headers)[0], 401)

    def test_profile_settings_and_password_rotation(self):
        headers = self.auth_headers("student")
        settings_status, settings = self.request("/api/me/settings", headers={"Cookie": headers["Cookie"]})
        self.assertEqual(settings_status, 200)
        self.assertEqual(settings["locale"], "uz")
        update_status, _ = self.request("/api/me/settings", {
            "display_name": "Updated Student", "locale": "ru", "email_notifications": False
        }, headers=headers)
        self.assertEqual(update_status, 200)
        _, updated = self.request("/api/me/settings", headers={"Cookie": headers["Cookie"]})
        self.assertEqual((updated["display_name"], updated["locale"], updated["email_notifications"]), ("Updated Student", "ru", False))

        change_status, _ = self.request("/api/me/password", {
            "current_password": "Test-Password-123!", "new_password": "Another-Password-456!"
        }, headers=headers)
        self.assertEqual(change_status, 200)
        self.assertEqual(self.request("/api/auth/me", headers={"Cookie": headers["Cookie"]})[0], 200)
        self.assertEqual(self.request("/api/auth/login", {
            "email": "student@example.test", "password": "Test-Password-123!"
        })[0], 401)
        self.assertEqual(self.request("/api/auth/login", {
            "email": "student@example.test", "password": "Another-Password-456!"
        })[0], 200)

    def test_club_membership_plan_versions_and_review(self):
        admin_headers = self.auth_headers("admin")
        status, club = self.request("/api/clubs", {
            "slug": "intellektual", "name": "Intellektual klub", "category": "Intellektual"
        }, headers=admin_headers)
        self.assertEqual(status, 201)
        club_id = club["id"]

        student_headers = self.auth_headers("student")
        self.assertEqual(self.request(f"/api/clubs/{club_id}/join", {}, headers=student_headers)[0], 201)
        with server.database() as db:
            student_id = db.execute("SELECT id FROM users WHERE email='student@example.test'").fetchone()[0]

        coordinator_headers = self.auth_headers("coordinator")
        with server.database() as db:
            coordinator_id = db.execute("SELECT id FROM users WHERE email='coordinator@example.test'").fetchone()[0]
            db.execute(
                "INSERT INTO club_memberships (club_id,user_id,membership_role,status,applied_at) VALUES (?,?,'coordinator','active',?)",
                (club_id, coordinator_id, server.now_utc().isoformat()),
            )
        membership_status, membership_result = self.request(
            f"/api/clubs/{club_id}/memberships/{student_id}/review",
            {"decision": "approved"},
            headers=coordinator_headers,
        )
        self.assertEqual(membership_status, 200)
        self.assertEqual(membership_result["status"], "active")
        status, plan = self.request(f"/api/clubs/{club_id}/plans", {
            "period_type": "weekly", "period_start": "2026-11-09", "period_end": "2026-11-15",
            "title": "Haftalik reja", "objectives": "Boshlang‘ich maqsadlar",
        }, headers=coordinator_headers)
        self.assertEqual(status, 201)
        plan_id = plan["id"]
        status, updated = self.request(f"/api/plans/{plan_id}/update", {
            "title": "Yangilangan reja", "objectives": "Yangilangan maqsadlar", "change_note": "Tuzatish"
        }, headers=coordinator_headers)
        self.assertEqual(status, 200)
        self.assertEqual(updated["version"], 2)
        self.assertEqual(self.request(f"/api/plans/{plan_id}/tasks", {"title": "Tadbir tashkil etish", "assigned_to": student_id}, headers=coordinator_headers)[0], 201)
        self.assertEqual(self.request(f"/api/clubs/{club_id}/events", {
            "title": "Klub uchrashuvi", "starts_at": "2026-11-12T10:00:00", "ends_at": "2026-11-12T11:00:00"
        }, headers=coordinator_headers)[0], 201)
        self.assertEqual(self.request(f"/api/plans/{plan_id}/submit", {}, headers=coordinator_headers)[0], 200)
        dean_headers = self.auth_headers("dean")
        self.assertEqual(self.request(f"/api/plans/{plan_id}/review", {"decision": "approved"}, headers=dean_headers)[0], 200)
        with server.database() as db:
            plan_status = db.execute("SELECT status FROM club_plans WHERE id=?", (plan_id,)).fetchone()[0]
            versions = db.execute("SELECT COUNT(*) FROM plan_versions WHERE plan_id=?", (plan_id,)).fetchone()[0]
            audit_count = db.execute("SELECT COUNT(*) FROM audit_logs WHERE entity_type='club_plan' AND entity_id=?", (str(plan_id),)).fetchone()[0]
        self.assertEqual(plan_status, "approved")
        self.assertEqual(versions, 2)
        self.assertGreaterEqual(audit_count, 4)

    def test_secret_election_allows_one_vote_and_publishes_aggregate_results(self):
        admin_headers = self.auth_headers("admin")
        _, club = self.request("/api/clubs", {
            "slug": "saylov-klubi", "name": "Saylov klubi", "category": "Talabalar klubi"
        }, headers=admin_headers)
        candidate_headers = self.auth_headers("student", "candidate@example.test")
        voter_headers = self.auth_headers("student", "voter@example.test")
        with server.database() as db:
            candidate_id = db.execute("SELECT id FROM users WHERE email='candidate@example.test'").fetchone()[0]
            voter_id = db.execute("SELECT id FROM users WHERE email='voter@example.test'").fetchone()[0]
            now = server.now_utc().isoformat()
            db.executemany(
                "INSERT INTO club_memberships (club_id,user_id,membership_role,status,applied_at) VALUES (?,?,'member','active',?)",
                [(club["id"], candidate_id, now), (club["id"], voter_id, now)],
            )
        starts = (server.now_utc() + server.timedelta(minutes=5)).isoformat()
        ends = (server.now_utc() + server.timedelta(minutes=10)).isoformat()
        dean_headers = self.auth_headers("dean")
        status, election = self.request("/api/elections", {
            "club_id": club["id"], "position_title": "Koordinator", "starts_at": starts, "ends_at": ends
        }, headers=dean_headers)
        self.assertEqual(status, 201)
        election_id = election["id"]
        self.assertEqual(self.request(f"/api/elections/{election_id}/candidates", {"statement": "Ochiq dastur"}, headers=candidate_headers)[0], 201)
        with server.database() as db:
            nominee_id = db.execute("SELECT id FROM election_candidates WHERE election_id=?", (election_id,)).fetchone()[0]
        candidate_review = self.request(
            f"/api/elections/{election_id}/candidates/{nominee_id}/review",
            {"decision": "approved"},
            headers=dean_headers,
        )
        self.assertEqual(candidate_review[0], 200)
        with server.database() as db:
            db.execute("UPDATE elections SET starts_at=? WHERE id=?", ((server.now_utc() - server.timedelta(minutes=1)).isoformat(), election_id))
        self.assertEqual(self.request(f"/api/elections/{election_id}/open", {}, headers=dean_headers)[0], 200)
        vote_payload = {"candidate_id": nominee_id}
        self.assertEqual(self.request(f"/api/elections/{election_id}/vote", vote_payload, headers=voter_headers)[0], 201)
        self.assertEqual(self.request(f"/api/elections/{election_id}/vote", vote_payload, headers=voter_headers)[0], 409)
        self.assertEqual(self.request(f"/api/elections/{election_id}/results")[0], 404)

        with server.database() as db:
            db.execute("UPDATE elections SET ends_at=? WHERE id=?", ((server.now_utc() - server.timedelta(seconds=1)).isoformat(), election_id))
            voter_columns = {row["name"] for row in db.execute("PRAGMA table_info(election_voters)")}
            tally_columns = {row["name"] for row in db.execute("PRAGMA table_info(election_tallies)")}
            audit = db.execute("SELECT actor_user_id,after_json FROM audit_logs WHERE action='election.aggregate_tally_updated'").fetchone()
        self.assertNotIn("candidate_id", voter_columns)
        self.assertNotIn("user_id", tally_columns)
        self.assertIsNone(audit["actor_user_id"])
        self.assertNotIn("candidate_id", audit["after_json"])
        self.assertEqual(self.request(f"/api/elections/{election_id}/close", {}, headers=dean_headers)[0], 200)
        self.assertEqual(self.request(f"/api/elections/{election_id}/publish", {}, headers=dean_headers)[0], 200)
        results_status, results = self.request(f"/api/elections/{election_id}/results")
        self.assertEqual(results_status, 200)
        self.assertEqual(results["items"][0]["vote_count"], 1)

    def test_member_is_persisted(self):
        image_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        photo = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")
        headers = self.auth_headers("admin")
        status, _ = self.request("/api/members", {
            "first": "Test", "last": "Koordinator", "role": "Sinov", "duty": "Sinov vazifasi", "photo": photo
        }, headers=headers)
        self.assertEqual(status, 201)
        _, state = self.request("/api/state")
        self.assertEqual(len(state["members"]), 12)
        self.assertEqual(state["members"][-1][:2], ["Test", "Koordinator"])
        self.assertTrue(state["members"][-1][5].startswith("/api/uploads/"))
        with urllib.request.urlopen(self.base_url + state["members"][-1][5]) as response:
            self.assertEqual(response.read(), image_bytes)

    def test_existing_database_migrates_member_photo_column(self):
        server.DB_PATH = Path(self.temp_dir.name) / "legacy.sqlite3"
        with server.database() as db:
            db.execute("""
                CREATE TABLE members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    first_name TEXT NOT NULL,
                    last_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    duty TEXT NOT NULL,
                    kpi INTEGER NOT NULL DEFAULT 0,
                    name_key TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                )
            """)
            db.execute(
                "INSERT INTO members (first_name,last_name,role,duty,kpi,name_key,created_at) VALUES (?,?,?,?,?,?,?)",
                ("Old", "Member", "Role", "Duty", 0, "old member", "test"),
            )
            db.execute("""
                CREATE TABLE reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    member_name TEXT NOT NULL,
                    week TEXT NOT NULL,
                    event TEXT NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    proof INTEGER NOT NULL DEFAULT 0,
                    images TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                )
            """)
            db.execute(
                "INSERT INTO reports (member_name,week,event,category,description,score,status,proof,images,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("Old Member", "2026-W1", "Old Event", "Club", "Legacy report", 50, "Tekshiruvda", 0, "[]", "test"),
            )
        server.init_db()
        with server.database() as db:
            columns = {row["name"] for row in db.execute("PRAGMA table_info(members)")}
            member = db.execute("SELECT first_name,last_name,photo FROM members WHERE name_key='old member'").fetchone()
            report_columns = {row["name"] for row in db.execute("PRAGMA table_info(reports)")}
            report = db.execute("SELECT event,club_id,period_type FROM reports WHERE member_name='Old Member'").fetchone()
        self.assertIn("photo", columns)
        self.assertEqual((member["first_name"], member["last_name"], member["photo"]), ("Old", "Member", None))
        self.assertTrue({"club_id", "plan_id", "submitted_by", "period_type", "title"}.issubset(report_columns))
        self.assertEqual((report["event"], report["club_id"], report["period_type"]), ("Old Event", None, "weekly"))

    def test_report_upload_and_approval_are_persisted(self):
        image_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        coordinator_headers = self.auth_headers("coordinator")
        with server.database() as db:
            coordinator_id = db.execute("SELECT id FROM users WHERE email='coordinator@example.test'").fetchone()[0]
            club_id = db.execute(
                "INSERT INTO clubs (slug,name,description,category,status,created_by,created_at,updated_at) VALUES ('report-club','Report Club','','Test','active',?,?,?)",
                (coordinator_id, server.now_utc().isoformat(), server.now_utc().isoformat()),
            ).lastrowid
            db.execute(
                "INSERT INTO club_memberships (club_id,user_id,membership_role,status,applied_at) VALUES (?,?,'coordinator','active',?)",
                (club_id, coordinator_id, server.now_utc().isoformat()),
            )
        status, _ = self.request("/api/reports", {
            "member": "Jasmina Yangiyeva",
            "week": "2026-W46",
            "event": "Sinov tadbiri",
            "category": "Intellektual loyihalar",
            "description": "API sinovi",
            "score": 80,
            "proof": True,
            "club_id": club_id,
            "images": ["data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")],
        }, headers=coordinator_headers)
        self.assertEqual(status, 201)

        with server.database() as db:
            report_row = db.execute("SELECT id,status,images FROM reports WHERE event='Sinov tadbiri'").fetchone()
        report = {"id": report_row["id"], "status": report_row["status"], "images": json.loads(report_row["images"])}
        self.assertEqual(report["status"], "Tekshiruvda")
        self.assertEqual(len(report["images"]), 1)
        public_reports = self.request("/api/state")[1]["reports"]
        self.assertEqual([report["event"] for report in public_reports], ["Zakovat turniri"])
        with self.assertRaises(urllib.error.HTTPError) as pending_image:
            urllib.request.urlopen(self.base_url + report["images"][0])
        self.assertEqual(pending_image.exception.code, 404)

        dean_headers = self.auth_headers("dean")
        status, _ = self.request(f"/api/reports/{report['id']}/review", {
            "decision": "changes_requested", "score": 65, "feedback": "Natijani batafsil yozing."
        }, headers=dean_headers)
        self.assertEqual(status, 200)
        status, updated = self.request(f"/api/reports/{report['id']}/update", {
            "description": "API sinovi: ishtirokchilar soni va natija kiritildi.", "change_note": "Izohga javob"
        }, headers=coordinator_headers)
        self.assertEqual(status, 200)
        self.assertEqual(updated["version"], 2)
        status, _ = self.request(f"/api/reports/{report['id']}/review", {
            "decision": "approved", "score": 80, "feedback": "Tasdiqlandi."
        }, headers=dean_headers)
        self.assertEqual(status, 200)
        version_status, versions = self.request(f"/api/reports/{report['id']}/versions", headers={"Cookie": dean_headers["Cookie"]})
        self.assertEqual(version_status, 200)
        self.assertEqual(len(versions["items"]), 2)
        with urllib.request.urlopen(self.base_url + report["images"][0]) as response:
            self.assertEqual(response.read(), image_bytes)
        _, state = self.request("/api/state")
        self.assertEqual(state["reports"][0]["status"], "Tasdiqlangan")


if __name__ == "__main__":
    unittest.main()
