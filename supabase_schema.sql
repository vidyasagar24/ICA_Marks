-- ==============================================================================
-- ACADEMIC ASSESSMENT MANAGEMENT SYSTEM (AAMS)
-- Supabase PostgreSQL Relational Schema & Initial Seed Data
-- Project: fhhksgrxgbhikmoajspe
-- ==============================================================================

-- 1. Academic Years
CREATE TABLE IF NOT EXISTS academic_years (
    id SERIAL PRIMARY KEY,
    year_code VARCHAR(30) NOT NULL UNIQUE,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Active',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Degree Programmes
CREATE TABLE IF NOT EXISTS programmes (
    id SERIAL PRIMARY KEY,
    code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL,
    description VARCHAR(255),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Semesters
CREATE TABLE IF NOT EXISTS semesters (
    id SERIAL PRIMARY KEY,
    number INT NOT NULL UNIQUE,
    name VARCHAR(30) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- 4. Sections
CREATE TABLE IF NOT EXISTS sections (
    id SERIAL PRIMARY KEY,
    programme_id INT NOT NULL REFERENCES programmes(id) ON DELETE CASCADE,
    academic_year_id INT NOT NULL REFERENCES academic_years(id) ON DELETE CASCADE,
    semester_id INT NOT NULL REFERENCES semesters(id) ON DELETE CASCADE,
    name VARCHAR(20) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_programme_year_sem_section UNIQUE (programme_id, academic_year_id, semester_id, name)
);

-- 5. Faculty Profiles
CREATE TABLE IF NOT EXISTS faculty (
    id SERIAL PRIMARY KEY,
    faculty_id_code VARCHAR(30) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    department VARCHAR(100) NOT NULL,
    designation VARCHAR(80) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Active',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 6. User Accounts
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'faculty',
    faculty_id INT UNIQUE REFERENCES faculty(id) ON DELETE SET NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 7. Subjects Master
CREATE TABLE IF NOT EXISTS subjects (
    id SERIAL PRIMARY KEY,
    subject_code VARCHAR(30) NOT NULL,
    subject_name VARCHAR(150) NOT NULL,
    programme_id INT NOT NULL REFERENCES programmes(id) ON DELETE CASCADE,
    semester_id INT NOT NULL REFERENCES semesters(id) ON DELETE CASCADE,
    credits INT NOT NULL DEFAULT 3,
    ica_max DOUBLE PRECISION NOT NULL DEFAULT 50.0,
    tee_max DOUBLE PRECISION NOT NULL DEFAULT 100.0,
    status VARCHAR(20) NOT NULL DEFAULT 'Active',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_subject_prog_sem UNIQUE (subject_code, programme_id, semester_id)
);

-- 8. Students
CREATE TABLE IF NOT EXISTS students (
    id SERIAL PRIMARY KEY,
    register_number VARCHAR(30) NOT NULL UNIQUE,
    student_id_code VARCHAR(30) NOT NULL UNIQUE,
    student_name VARCHAR(100) NOT NULL,
    programme_id INT NOT NULL REFERENCES programmes(id) ON DELETE CASCADE,
    academic_year_id INT NOT NULL REFERENCES academic_years(id) ON DELETE CASCADE,
    current_semester_id INT NOT NULL REFERENCES semesters(id) ON DELETE CASCADE,
    section_id INT NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    email VARCHAR(120),
    status VARCHAR(20) NOT NULL DEFAULT 'Active',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 9. Student Enrollments
CREATE TABLE IF NOT EXISTS student_enrollments (
    enrollment_id SERIAL PRIMARY KEY,
    student_id INT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    year_id INT NOT NULL REFERENCES academic_years(id) ON DELETE CASCADE,
    programme_id INT NOT NULL REFERENCES programmes(id) ON DELETE CASCADE,
    semester_id INT NOT NULL REFERENCES semesters(id) ON DELETE CASCADE,
    section_id INT NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_student_year_semester_enrollment UNIQUE (student_id, year_id, semester_id)
);

-- 10. Faculty Subject Allocations
CREATE TABLE IF NOT EXISTS faculty_subject_mapping (
    id SERIAL PRIMARY KEY,
    academic_year_id INT NOT NULL REFERENCES academic_years(id) ON DELETE CASCADE,
    programme_id INT NOT NULL REFERENCES programmes(id) ON DELETE CASCADE,
    semester_id INT NOT NULL REFERENCES semesters(id) ON DELETE CASCADE,
    section_id INT NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    subject_id INT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    faculty_id INT NOT NULL REFERENCES faculty(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'Active',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_faculty_subject_section_alloc UNIQUE (academic_year_id, programme_id, semester_id, section_id, subject_id, faculty_id)
);

-- 11. Assessments
CREATE TABLE IF NOT EXISTS assessments (
    id SERIAL PRIMARY KEY,
    mapping_id INT NOT NULL REFERENCES faculty_subject_mapping(id) ON DELETE CASCADE,
    assessment_name VARCHAR(80) NOT NULL,
    assessment_type VARCHAR(40) NOT NULL DEFAULT 'Test',
    max_marks DOUBLE PRECISION NOT NULL DEFAULT 20.0,
    weightage DOUBLE PRECISION NOT NULL DEFAULT 100.0,
    order_num INT NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_mapping_assessment_name UNIQUE (mapping_id, assessment_name)
);

-- 12. Marks
CREATE TABLE IF NOT EXISTS marks (
    id SERIAL PRIMARY KEY,
    student_id INT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    assessment_id INT NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
    mapping_id INT NOT NULL REFERENCES faculty_subject_mapping(id) ON DELETE CASCADE,
    score DOUBLE PRECISION,
    status VARCHAR(20) NOT NULL DEFAULT 'Present',
    remarks VARCHAR(255),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_student_assessment_mapping_mark UNIQUE (student_id, assessment_id, mapping_id)
);

-- 13. Submissions
CREATE TABLE IF NOT EXISTS submissions (
    id SERIAL PRIMARY KEY,
    mapping_id INT NOT NULL REFERENCES faculty_subject_mapping(id) ON DELETE CASCADE,
    assessment_id INT REFERENCES assessments(id) ON DELETE CASCADE,
    submitted_by_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    submission_date TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(30) NOT NULL DEFAULT 'Draft',
    reviewed_by_id INT REFERENCES users(id) ON DELETE SET NULL,
    review_date TIMESTAMP WITHOUT TIME ZONE,
    review_comments TEXT
);

-- 14. Audit Logs
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    user_id INT REFERENCES users(id) ON DELETE SET NULL,
    user_name VARCHAR(80),
    role VARCHAR(30),
    action VARCHAR(80) NOT NULL,
    entity_type VARCHAR(60) NOT NULL,
    entity_id VARCHAR(50),
    field_name VARCHAR(60),
    old_value TEXT,
    updated_value TEXT,
    ip_address VARCHAR(45)
);

CREATE TABLE IF NOT EXISTS marks_audit (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    mark_id INT NOT NULL REFERENCES marks(id) ON DELETE CASCADE,
    old_marks DOUBLE PRECISION,
    new_marks DOUBLE PRECISION,
    changed_by INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reason VARCHAR(255)
);

-- Indexes for high performance
CREATE INDEX IF NOT EXISTS idx_student_reg ON students(register_number);
CREATE INDEX IF NOT EXISTS idx_marks_student ON marks(student_id);
CREATE INDEX IF NOT EXISTS idx_marks_assessment ON marks(assessment_id);
CREATE INDEX IF NOT EXISTS idx_marks_mapping ON marks(mapping_id);
CREATE INDEX IF NOT EXISTS idx_fsm_alloc ON faculty_subject_mapping(academic_year_id, programme_id, semester_id, section_id);
