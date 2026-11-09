-- ==============================================================================
-- Faculty Assessment & Student Marks Management System (AAMS)
-- MySQL 8.0 Relational Database Schema
-- Version: 1.0 | Date: 09 November 2026
-- ==============================================================================

CREATE DATABASE IF NOT EXISTS academic_assessment_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE academic_assessment_db;

-- 1. Academic Years
CREATE TABLE IF NOT EXISTS academic_years (
    id INT AUTO_INCREMENT PRIMARY KEY,
    year_code VARCHAR(30) NOT NULL UNIQUE,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    status ENUM('Active', 'Archived', 'Upcoming') NOT NULL DEFAULT 'Active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_academic_year_code (year_code)
) ENGINE=InnoDB;

-- 2. Degree Programmes
CREATE TABLE IF NOT EXISTS programmes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL,
    description VARCHAR(255) NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_programme_code (code)
) ENGINE=InnoDB;

-- 3. Semesters
CREATE TABLE IF NOT EXISTS semesters (
    id INT AUTO_INCREMENT PRIMARY KEY,
    number INT NOT NULL UNIQUE,
    name VARCHAR(30) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
) ENGINE=InnoDB;

-- 4. Sections
CREATE TABLE IF NOT EXISTS sections (
    id INT AUTO_INCREMENT PRIMARY KEY,
    programme_id INT NOT NULL,
    academic_year_id INT NOT NULL,
    semester_id INT NOT NULL,
    name VARCHAR(20) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_programme_year_sem_section UNIQUE (programme_id, academic_year_id, semester_id, name),
    CONSTRAINT fk_sections_programme FOREIGN KEY (programme_id) REFERENCES programmes(id) ON DELETE CASCADE,
    CONSTRAINT fk_sections_year FOREIGN KEY (academic_year_id) REFERENCES academic_years(id) ON DELETE CASCADE,
    CONSTRAINT fk_sections_semester FOREIGN KEY (semester_id) REFERENCES semesters(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- 5. Faculty Master
CREATE TABLE IF NOT EXISTS faculty (
    id INT AUTO_INCREMENT PRIMARY KEY,
    faculty_id_code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    department VARCHAR(100) NOT NULL,
    designation VARCHAR(100) NOT NULL,
    status ENUM('Active', 'Inactive') NOT NULL DEFAULT 'Active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_faculty_code (faculty_id_code)
) ENGINE=InnoDB;

-- 6. User Accounts & Authentication
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(60) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('admin', 'faculty') NOT NULL DEFAULT 'faculty',
    faculty_id INT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_users_faculty FOREIGN KEY (faculty_id) REFERENCES faculty(id) ON DELETE SET NULL,
    INDEX idx_username (username)
) ENGINE=InnoDB;

-- 7. Student Master
CREATE TABLE IF NOT EXISTS students (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id_code VARCHAR(50) NULL,
    register_number VARCHAR(50) NOT NULL UNIQUE,
    student_name VARCHAR(120) NOT NULL,
    programme_id INT NOT NULL,
    academic_year_id INT NOT NULL,
    current_semester_id INT NOT NULL,
    section_id INT NOT NULL,
    email VARCHAR(120) NULL,
    status ENUM('Active', 'Inactive') NOT NULL DEFAULT 'Active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_students_programme FOREIGN KEY (programme_id) REFERENCES programmes(id),
    CONSTRAINT fk_students_year FOREIGN KEY (academic_year_id) REFERENCES academic_years(id),
    CONSTRAINT fk_students_sem FOREIGN KEY (current_semester_id) REFERENCES semesters(id),
    CONSTRAINT fk_students_section FOREIGN KEY (section_id) REFERENCES sections(id),
    INDEX idx_register_number (register_number)
) ENGINE=InnoDB;

-- 8. Student Enrollments History (TRD Section 5.3 & BL-10, BL-11)
CREATE TABLE IF NOT EXISTS student_enrollments (
    enrollment_id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    year_id INT NOT NULL,
    programme_id INT NOT NULL,
    semester_id INT NOT NULL,
    section_id INT NOT NULL,
    status ENUM('active','inactive') DEFAULT 'active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_enr_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    CONSTRAINT fk_enr_year FOREIGN KEY (year_id) REFERENCES academic_years(id) ON DELETE CASCADE,
    CONSTRAINT fk_enr_programme FOREIGN KEY (programme_id) REFERENCES programmes(id) ON DELETE CASCADE,
    CONSTRAINT fk_enr_semester FOREIGN KEY (semester_id) REFERENCES semesters(id) ON DELETE CASCADE,
    CONSTRAINT fk_enr_section FOREIGN KEY (section_id) REFERENCES sections(id) ON DELETE CASCADE,
    UNIQUE (student_id, year_id, semester_id)
) ENGINE=InnoDB;

-- 9. Subject Master
CREATE TABLE IF NOT EXISTS subjects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    subject_code VARCHAR(30) NOT NULL,
    subject_name VARCHAR(150) NOT NULL,
    programme_id INT NOT NULL,
    semester_id INT NOT NULL,
    credits INT NOT NULL DEFAULT 3,
    ica_max DECIMAL(5,2) NOT NULL DEFAULT 50.00,
    tee_max DECIMAL(5,2) NOT NULL DEFAULT 100.00,
    status ENUM('Active', 'Inactive') NOT NULL DEFAULT 'Active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_subject_prog_sem UNIQUE (subject_code, programme_id, semester_id),
    CONSTRAINT fk_subjects_programme FOREIGN KEY (programme_id) REFERENCES programmes(id),
    CONSTRAINT fk_subjects_semester FOREIGN KEY (semester_id) REFERENCES semesters(id),
    INDEX idx_subject_code (subject_code)
) ENGINE=InnoDB;

-- 9. Faculty-Subject-Section Mapping (Critical Allocation Matrix)
CREATE TABLE IF NOT EXISTS faculty_subject_mapping (
    id INT AUTO_INCREMENT PRIMARY KEY,
    academic_year_id INT NOT NULL,
    programme_id INT NOT NULL,
    semester_id INT NOT NULL,
    section_id INT NOT NULL,
    subject_id INT NOT NULL,
    faculty_id INT NOT NULL,
    status ENUM('Active', 'Inactive') NOT NULL DEFAULT 'Active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT uq_faculty_subject_section_alloc UNIQUE (academic_year_id, programme_id, semester_id, section_id, subject_id, faculty_id),
    CONSTRAINT fk_map_year FOREIGN KEY (academic_year_id) REFERENCES academic_years(id),
    CONSTRAINT fk_map_programme FOREIGN KEY (programme_id) REFERENCES programmes(id),
    CONSTRAINT fk_map_sem FOREIGN KEY (semester_id) REFERENCES semesters(id),
    CONSTRAINT fk_map_section FOREIGN KEY (section_id) REFERENCES sections(id),
    CONSTRAINT fk_map_subject FOREIGN KEY (subject_id) REFERENCES subjects(id),
    CONSTRAINT fk_map_faculty FOREIGN KEY (faculty_id) REFERENCES faculty(id)
) ENGINE=InnoDB;

-- 10. Assessment Components
CREATE TABLE IF NOT EXISTS assessments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    mapping_id INT NOT NULL,
    assessment_name VARCHAR(80) NOT NULL,
    assessment_type VARCHAR(40) NOT NULL DEFAULT 'Test',
    max_marks DECIMAL(5,2) NOT NULL DEFAULT 20.00,
    weightage DECIMAL(5,2) NOT NULL DEFAULT 100.00,
    order_num INT NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_mapping_assessment_name UNIQUE (mapping_id, assessment_name),
    CONSTRAINT fk_assessments_mapping FOREIGN KEY (mapping_id) REFERENCES faculty_subject_mapping(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- 11. Student Assessment Marks
CREATE TABLE IF NOT EXISTS marks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    assessment_id INT NOT NULL,
    mapping_id INT NOT NULL,
    score DECIMAL(5,2) NULL,
    status ENUM('Present', 'Absent', 'Exempted') NOT NULL DEFAULT 'Present',
    remarks VARCHAR(255) NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT uq_student_assessment_mapping_mark UNIQUE (student_id, assessment_id, mapping_id),
    CONSTRAINT fk_marks_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    CONSTRAINT fk_marks_assessment FOREIGN KEY (assessment_id) REFERENCES assessments(id) ON DELETE CASCADE,
    CONSTRAINT fk_marks_mapping FOREIGN KEY (mapping_id) REFERENCES faculty_subject_mapping(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- 12. Marks Workflow Submissions
CREATE TABLE IF NOT EXISTS submissions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    mapping_id INT NOT NULL,
    assessment_id INT NULL,
    submitted_by_id INT NULL,
    status ENUM('Draft', 'Submitted', 'Under Review', 'Approved', 'Reopened') NOT NULL DEFAULT 'Draft',
    submission_date DATETIME NULL,
    reviewed_by_id INT NULL,
    review_date DATETIME NULL,
    review_comments TEXT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_submissions_mapping FOREIGN KEY (mapping_id) REFERENCES faculty_subject_mapping(id) ON DELETE CASCADE,
    CONSTRAINT fk_submissions_assessment FOREIGN KEY (assessment_id) REFERENCES assessments(id) ON DELETE SET NULL,
    CONSTRAINT fk_submissions_submitted_by FOREIGN KEY (submitted_by_id) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT fk_submissions_reviewed_by FOREIGN KEY (reviewed_by_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- 13. Marks Audit Trail (TRD Section 5.3 & BL-09)
CREATE TABLE IF NOT EXISTS marks_audit (
    audit_id INT AUTO_INCREMENT PRIMARY KEY,
    mark_id INT NOT NULL,
    old_marks DECIMAL(7,2) NULL,
    new_marks DECIMAL(7,2) NULL,
    changed_by INT NULL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reason VARCHAR(500) NULL,
    CONSTRAINT fk_audit_mark FOREIGN KEY (mark_id) REFERENCES marks(id) ON DELETE CASCADE,
    CONSTRAINT fk_audit_user FOREIGN KEY (changed_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- 14. Audit Logs
CREATE TABLE IF NOT EXISTS audit_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL,
    user_name VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL,
    action VARCHAR(60) NOT NULL,
    entity_type VARCHAR(60) NOT NULL,
    entity_id VARCHAR(60) NULL,
    previous_value TEXT NULL,
    updated_value TEXT NULL,
    ip_address VARCHAR(45) NULL,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_audit_action (action),
    INDEX idx_audit_entity (entity_type),
    INDEX idx_audit_timestamp (timestamp)
) ENGINE=InnoDB;
