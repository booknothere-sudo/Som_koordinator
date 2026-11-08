PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS roles (
    role_key TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS permissions (
    permission_key TEXT PRIMARY KEY,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_key TEXT NOT NULL REFERENCES roles(role_key) ON DELETE CASCADE,
    permission_key TEXT NOT NULL REFERENCES permissions(permission_key) ON DELETE CASCADE,
    PRIMARY KEY (role_key, permission_key)
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    profile_photo_path TEXT,
    status TEXT NOT NULL DEFAULT 'pending_verification'
        CHECK (status IN ('pending_verification', 'verified', 'rejected', 'suspended')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS user_roles (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_key TEXT NOT NULL REFERENCES roles(role_key) ON DELETE RESTRICT,
    granted_by INTEGER REFERENCES users(id) ON DELETE RESTRICT,
    granted_at TEXT NOT NULL,
    PRIMARY KEY (user_id, role_key)
);

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    locale TEXT NOT NULL DEFAULT 'uz',
    email_notifications INTEGER NOT NULL DEFAULT 1 CHECK (email_notifications IN (0, 1)),
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash TEXT PRIMARY KEY,
    csrf_hash TEXT NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT
);

CREATE TABLE IF NOT EXISTS student_verifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    student_number TEXT NOT NULL,
    faculty TEXT NOT NULL,
    study_group TEXT NOT NULL,
    verification_photo_path TEXT NOT NULL,
    photo_policy_ack_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected')),
    reviewed_by INTEGER REFERENCES users(id) ON DELETE RESTRICT,
    review_note TEXT,
    created_at TEXT NOT NULL,
    reviewed_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_student_verifications_active_number
    ON student_verifications(student_number)
    WHERE status IN ('pending', 'approved');

CREATE TABLE IF NOT EXISTS clubs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL,
    cover_photo_path TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('draft', 'active', 'archived')),
    created_by INTEGER REFERENCES users(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS club_memberships (
    club_id INTEGER NOT NULL REFERENCES clubs(id) ON DELETE RESTRICT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    membership_role TEXT NOT NULL DEFAULT 'member'
        CHECK (membership_role IN ('member', 'coordinator')),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'active', 'rejected', 'left')),
    applied_at TEXT NOT NULL,
    decided_by INTEGER REFERENCES users(id) ON DELETE RESTRICT,
    decided_at TEXT,
    PRIMARY KEY (club_id, user_id)
);

CREATE TABLE IF NOT EXISTS club_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    club_id INTEGER NOT NULL REFERENCES clubs(id) ON DELETE RESTRICT,
    created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    period_type TEXT NOT NULL CHECK (period_type IN ('weekly', 'monthly')),
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    title TEXT NOT NULL,
    objectives TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'submitted', 'approved', 'rejected', 'changes_requested')),
    reviewed_by INTEGER REFERENCES users(id) ON DELETE RESTRICT,
    reviewed_at TEXT,
    review_note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (period_end >= period_start)
);

CREATE TABLE IF NOT EXISTS plan_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL REFERENCES club_plans(id) ON DELETE RESTRICT,
    version_number INTEGER NOT NULL,
    snapshot_json TEXT NOT NULL,
    changed_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    change_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE (plan_id, version_number)
);

CREATE TABLE IF NOT EXISTS plan_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL REFERENCES club_plans(id) ON DELETE RESTRICT,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    assigned_to INTEGER REFERENCES users(id) ON DELETE RESTRICT,
    due_at TEXT,
    status TEXT NOT NULL DEFAULT 'todo'
        CHECK (status IN ('todo', 'in_progress', 'done', 'cancelled')),
    created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS club_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    club_id INTEGER NOT NULL REFERENCES clubs(id) ON DELETE RESTRICT,
    plan_id INTEGER REFERENCES club_plans(id) ON DELETE RESTRICT,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    starts_at TEXT NOT NULL,
    ends_at TEXT NOT NULL,
    location TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned', 'completed', 'cancelled')),
    created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (ends_at > starts_at)
);

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
    created_at TEXT NOT NULL,
    club_id INTEGER REFERENCES clubs(id) ON DELETE RESTRICT,
    plan_id INTEGER REFERENCES club_plans(id) ON DELETE RESTRICT,
    submitted_by INTEGER REFERENCES users(id) ON DELETE RESTRICT,
    period_type TEXT NOT NULL DEFAULT 'weekly' CHECK (period_type IN ('weekly', 'monthly')),
    title TEXT
);

CREATE TABLE IF NOT EXISTS report_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL REFERENCES reports(id) ON DELETE RESTRICT,
    version_number INTEGER NOT NULL,
    snapshot_json TEXT NOT NULL,
    changed_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    change_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE (report_id, version_number)
);

CREATE TABLE IF NOT EXISTS report_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL REFERENCES reports(id) ON DELETE RESTRICT,
    reviewer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected', 'changes_requested')),
    score INTEGER CHECK (score BETWEEN 0 AND 100),
    feedback TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS elections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    club_id INTEGER NOT NULL REFERENCES clubs(id) ON DELETE RESTRICT,
    position_title TEXT NOT NULL,
    starts_at TEXT NOT NULL,
    ends_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'candidate_review', 'open', 'closed', 'published', 'cancelled')),
    created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    approved_by INTEGER REFERENCES users(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    CHECK (ends_at > starts_at)
);

CREATE TABLE IF NOT EXISTS election_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    election_id INTEGER NOT NULL REFERENCES elections(id) ON DELETE RESTRICT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    statement TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected', 'withdrawn')),
    reviewed_by INTEGER REFERENCES users(id) ON DELETE RESTRICT,
    reviewed_at TEXT,
    review_note TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (election_id, user_id)
);

CREATE TABLE IF NOT EXISTS election_voters (
    election_id INTEGER NOT NULL REFERENCES elections(id) ON DELETE RESTRICT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    has_voted INTEGER NOT NULL DEFAULT 1 CHECK (has_voted IN (0, 1)),
    PRIMARY KEY (election_id, user_id)
);

CREATE TABLE IF NOT EXISTS election_ballots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    election_id INTEGER NOT NULL REFERENCES elections(id) ON DELETE RESTRICT,
    candidate_id INTEGER NOT NULL REFERENCES election_candidates(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS election_tallies (
    election_id INTEGER NOT NULL REFERENCES elections(id) ON DELETE RESTRICT,
    candidate_id INTEGER NOT NULL REFERENCES election_candidates(id) ON DELETE RESTRICT,
    vote_count INTEGER NOT NULL DEFAULT 0 CHECK (vote_count >= 0),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (election_id, candidate_id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id INTEGER REFERENCES users(id) ON DELETE RESTRICT,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    before_json TEXT,
    after_json TEXT,
    request_id TEXT,
    previous_hash TEXT,
    entry_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS audit_logs_no_update
BEFORE UPDATE ON audit_logs
BEGIN
    SELECT RAISE(ABORT, 'audit logs are append-only');
END;

CREATE TRIGGER IF NOT EXISTS audit_logs_no_delete
BEFORE DELETE ON audit_logs
BEGIN
    SELECT RAISE(ABORT, 'audit logs are append-only');
END;

CREATE TABLE IF NOT EXISTS system_settings (
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT NOT NULL,
    updated_by INTEGER REFERENCES users(id) ON DELETE RESTRICT,
    updated_at TEXT NOT NULL
);

INSERT OR IGNORE INTO roles(role_key, label, description) VALUES
    ('student', 'Tasdiqlangan SOM talabasi', 'Talabalik maqomi dekanat tomonidan tasdiqlangan.'),
    ('coordinator', 'Klub koordinatori', 'Biriktirilgan klub reja va hisobotlarini yuritadi.'),
    ('dean', 'Dekanat', 'Talabalar, rejalar, nomzodlar va hisobotlarni ko‘rib chiqadi.'),
    ('admin', 'Admin', 'Tizim bo‘yicha boshqaruv huquqiga ega.');

INSERT OR IGNORE INTO permissions(permission_key, description) VALUES
    ('clubs.join', 'Klubga a’zo bo‘lish'),
    ('elections.candidate', 'Saylovga nomzod bo‘lish'),
    ('elections.vote', 'Saylovda ovoz berish'),
    ('plans.manage', 'Klub rejalarini yaratish va tahrirlash'),
    ('plans.review', 'Klub rejalarini ko‘rib chiqish'),
    ('tasks.manage', 'Vazifalarni taqsimlash va holatini yangilash'),
    ('reports.submit', 'Klub hisobotini yuborish'),
    ('reviews.manage', 'Reja va hisobotlarni ko‘rib chiqish'),
    ('students.verify', 'Talaba verifikatsiyasini ko‘rib chiqish'),
    ('candidates.review', 'Saylov nomzodlarini ko‘rib chiqish'),
    ('users.manage', 'Foydalanuvchi va rollarni boshqarish'),
    ('settings.manage', 'Tizim sozlamalarini boshqarish');

INSERT OR IGNORE INTO role_permissions(role_key, permission_key) VALUES
    ('student', 'clubs.join'),
    ('student', 'elections.candidate'),
    ('student', 'elections.vote'),
    ('coordinator', 'plans.manage'),
    ('coordinator', 'tasks.manage'),
    ('coordinator', 'reports.submit'),
    ('dean', 'reviews.manage'),
    ('dean', 'plans.review'),
    ('dean', 'students.verify'),
    ('dean', 'candidates.review'),
    ('admin', 'clubs.join'),
    ('admin', 'elections.candidate'),
    ('admin', 'elections.vote'),
    ('admin', 'plans.manage'),
    ('admin', 'plans.review'),
    ('admin', 'tasks.manage'),
    ('admin', 'reports.submit'),
    ('admin', 'reviews.manage'),
    ('admin', 'students.verify'),
    ('admin', 'candidates.review'),
    ('admin', 'users.manage'),
    ('admin', 'settings.manage');

CREATE INDEX IF NOT EXISTS idx_user_roles_user ON user_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_expiry ON auth_sessions(user_id, expires_at);
CREATE INDEX IF NOT EXISTS idx_verifications_queue ON student_verifications(status, created_at);
CREATE INDEX IF NOT EXISTS idx_club_memberships_club_status ON club_memberships(club_id, status);
CREATE INDEX IF NOT EXISTS idx_club_plans_club_period ON club_plans(club_id, period_start, period_end);
CREATE INDEX IF NOT EXISTS idx_plan_tasks_assignee_status ON plan_tasks(assigned_to, status, due_at);
CREATE INDEX IF NOT EXISTS idx_club_events_calendar ON club_events(club_id, starts_at, status);
CREATE INDEX IF NOT EXISTS idx_report_reviews_report ON report_reviews(report_id, created_at);
CREATE INDEX IF NOT EXISTS idx_elections_status_window ON elections(status, starts_at, ends_at);
CREATE INDEX IF NOT EXISTS idx_candidates_election_status ON election_candidates(election_id, status);
CREATE INDEX IF NOT EXISTS idx_ballots_election ON election_ballots(election_id);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_logs(entity_type, entity_id, created_at);
