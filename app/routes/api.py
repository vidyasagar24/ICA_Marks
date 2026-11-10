import io
from datetime import datetime
from functools import wraps
from flask import Blueprint, jsonify, request, current_app
from flask_login import login_user, logout_user, login_required, current_user

from app.models import (
    db, User, Faculty, Student, StudentEnrollment, AcademicYear, Programme,
    Semester, Section, Subject, FacultySubjectMapping, Assessment, Mark,
    Submission, AuditLog, MarksAudit
)
from app.services.audit_service import log_action
from app.services.analytics_service import (
    get_admin_dashboard_kpis, get_section_analysis, get_faculty_workload_analysis, get_subject_wise_analysis
)

api_bp = Blueprint('api', __name__, url_prefix='/api')

def api_response(success=True, message="", data=None, errors=None, status_code=200):
    """Standardized TRD Section 6.4 API response envelope"""
    payload = {
        "success": success,
        "message": message
    }
    if data is not None:
        payload["data"] = data
    if errors is not None:
        payload["errors"] = errors
    return jsonify(payload), status_code

def admin_api_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return api_response(False, "Authentication required", errors=["Not logged in"], status_code=401)
        if not current_user.is_admin:
            return api_response(False, "Access forbidden: Administrators only", errors=["Forbidden"], status_code=403)
        return f(*args, **kwargs)
    return decorated

def faculty_api_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return api_response(False, "Authentication required", errors=["Not logged in"], status_code=401)
        if not current_user.is_faculty_role:
            return api_response(False, "Access forbidden: Faculty only", errors=["Forbidden"], status_code=403)
        return f(*args, **kwargs)
    return decorated


# ==============================================================================
# 6.1 AUTHENTICATION APIS
# ==============================================================================

@api_bp.route('/auth/login', methods=['POST'])
def api_login():
    data = request.get_json() or request.form
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return api_response(False, "Username and password required", status_code=400)

    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
        if not user.is_active:
            return api_response(False, "Account is deactivated", status_code=403)

        login_user(user)
        log_action('API_LOGIN', 'User', entity_id=user.id, updated_value={'username': user.username, 'role': user.role}, user=user)
        return api_response(True, "Login successful", data={
            "user_id": user.id,
            "username": user.username,
            "role": user.role,
            "faculty_id": user.faculty_id
        })

    return api_response(False, "Invalid username or password", status_code=401)


@api_bp.route('/auth/logout', methods=['POST'])
@login_required
def api_logout():
    log_action('API_LOGOUT', 'User', entity_id=current_user.id)
    logout_user()
    return api_response(True, "Logged out successfully")


@api_bp.route('/auth/profile', methods=['GET'])
@login_required
def api_profile():
    profile_data = {
        "user_id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "is_active": current_user.is_active,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None
    }
    if current_user.faculty_profile:
        fp = current_user.faculty_profile
        profile_data["faculty"] = {
            "id": fp.id,
            "code": fp.faculty_id_code,
            "name": fp.name,
            "email": fp.email,
            "department": fp.department,
            "designation": fp.designation
        }
    return api_response(True, "User profile retrieved", data=profile_data)


@api_bp.route('/auth/change-password', methods=['POST'])
@login_required
def api_change_password():
    data = request.get_json() or request.form
    curr_pwd = data.get('current_password', '')
    new_pwd = data.get('new_password', '')

    if not current_user.check_password(curr_pwd):
        return api_response(False, "Current password does not match", status_code=400)

    if len(new_pwd) < 6:
        return api_response(False, "Password must be at least 6 characters", status_code=400)

    current_user.set_password(new_pwd)
    db.session.commit()
    log_action('PASSWORD_CHANGE', 'User', entity_id=current_user.id)
    return api_response(True, "Password updated successfully")


# ==============================================================================
# 6.2 ADMIN APIS
# ==============================================================================

@api_bp.route('/admin/dashboard', methods=['GET'])
@login_required
@admin_api_required
def api_admin_dashboard():
    year_id = request.args.get('academic_year_id', type=int)
    prog_id = request.args.get('programme_id', type=int)
    sem_id = request.args.get('semester_id', type=int)

    kpis = get_admin_dashboard_kpis({'academic_year_id': year_id, 'programme_id': prog_id, 'semester_id': sem_id})
    return api_response(True, "Admin dashboard statistics retrieved", data=kpis)


@api_bp.route('/admin/academic-years', methods=['GET', 'POST'])
@login_required
@admin_api_required
def api_academic_years():
    if request.method == 'POST':
        data = request.get_json() or request.form
        year_code = data.get('year_code', '').strip()
        start_date_str = data.get('start_date', '')
        end_date_str = data.get('end_date', '')
        status = data.get('status', 'Active')

        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            return api_response(False, "Invalid date format. Use YYYY-MM-DD", status_code=400)

        if AcademicYear.query.filter_by(year_code=year_code).first():
            return api_response(False, f"Academic year '{year_code}' already exists", status_code=400)

        ay = AcademicYear(year_code=year_code, start_date=start_date, end_date=end_date, status=status)
        db.session.add(ay)
        db.session.commit()
        return api_response(True, "Academic year created", data={"id": ay.id, "year_code": ay.year_code})

    years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
    return api_response(True, "Academic years retrieved", data=[{
        "id": y.id, "year_code": y.year_code, "start_date": str(y.start_date), "end_date": str(y.end_date), "status": y.status
    } for y in years])


@api_bp.route('/admin/programmes', methods=['GET', 'POST'])
@login_required
@admin_api_required
def api_programmes():
    if request.method == 'POST':
        data = request.get_json() or request.form
        code = data.get('code', '').strip().upper()
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()

        if Programme.query.filter_by(code=code).first():
            return api_response(False, f"Programme '{code}' already exists", status_code=400)

        prog = Programme(code=code, name=name, description=description)
        db.session.add(prog)
        db.session.commit()
        return api_response(True, "Programme created", data={"id": prog.id, "code": prog.code, "name": prog.name})

    progs = Programme.query.order_by(Programme.code.asc()).all()
    return api_response(True, "Programmes retrieved", data=[{
        "id": p.id, "code": p.code, "name": p.name, "description": p.description, "is_active": p.is_active
    } for p in progs])


@api_bp.route('/admin/semesters', methods=['GET', 'POST'])
@login_required
@admin_api_required
def api_semesters():
    if request.method == 'POST':
        data = request.get_json() or request.form
        num = int(data.get('number', 0))
        name = data.get('name', f"Semester {num}")

        if Semester.query.filter_by(number=num).first():
            return api_response(False, f"Semester {num} already exists", status_code=400)

        sem = Semester(number=num, name=name)
        db.session.add(sem)
        db.session.commit()
        return api_response(True, "Semester created", data={"id": sem.id, "number": sem.number, "name": sem.name})

    sems = Semester.query.order_by(Semester.number.asc()).all()
    return api_response(True, "Semesters retrieved", data=[{
        "id": s.id, "number": s.number, "name": s.name
    } for s in sems])


@api_bp.route('/admin/sections', methods=['GET', 'POST'])
@login_required
@admin_api_required
def api_sections():
    if request.method == 'POST':
        data = request.get_json() or request.form
        prog_id = data.get('programme_id')
        year_id = data.get('academic_year_id')
        sem_id = data.get('semester_id')
        name = data.get('name', '').strip().upper()

        if Section.query.filter_by(programme_id=prog_id, academic_year_id=year_id, semester_id=sem_id, name=name).first():
            return api_response(False, f"Section '{name}' already exists in this cohort", status_code=400)

        sec = Section(programme_id=prog_id, academic_year_id=year_id, semester_id=sem_id, name=name)
        db.session.add(sec)
        db.session.commit()
        return api_response(True, "Section created", data={"id": sec.id, "name": sec.name, "display_name": sec.display_name})

    sections = Section.query.order_by(Section.name.asc()).all()
    return api_response(True, "Sections retrieved", data=[{
        "id": s.id, "name": s.name, "programme": s.programme.code, "year": s.academic_year.year_code, "semester": s.semester.name
    } for s in sections])


@api_bp.route('/admin/students', methods=['GET', 'POST'])
@login_required
@admin_api_required
def api_students():
    if request.method == 'POST':
        data = request.get_json() or request.form
        reg_no = data.get('register_number', '').strip().upper()
        name = data.get('student_name', '').strip()
        prog_id = data.get('programme_id')
        year_id = data.get('academic_year_id')
        sem_id = data.get('semester_id')
        sec_id = data.get('section_id')
        email = data.get('email', '').strip().lower()

        # BL-01: Unique register number
        if Student.query.filter_by(register_number=reg_no).first():
            return api_response(False, f"Student register number '{reg_no}' already exists (BL-01)", status_code=400)

        stu = Student(
            register_number=reg_no,
            student_id_code=reg_no,
            student_name=name,
            programme_id=prog_id,
            academic_year_id=year_id,
            current_semester_id=sem_id,
            section_id=sec_id,
            email=email,
            status='Active'
        )
        db.session.add(stu)
        db.session.flush()

        # BL-10: Track enrollment history in student_enrollments
        enrollment = StudentEnrollment(
            student_id=stu.id,
            year_id=year_id,
            programme_id=prog_id,
            semester_id=sem_id,
            section_id=sec_id,
            status='active'
        )
        db.session.add(enrollment)
        db.session.commit()
        log_action('API_CREATE_STUDENT', 'Student', entity_id=stu.id, updated_value={'reg_no': reg_no, 'name': name})
        return api_response(True, "Student registered successfully", data={"id": stu.id, "register_number": stu.register_number})

    # GET students list
    students = Student.query.order_by(Student.register_number.asc()).all()
    return api_response(True, "Students retrieved", data=[{
        "id": s.id,
        "register_number": s.register_number,
        "name": s.student_name,
        "programme": s.programme.code,
        "semester": s.current_semester.name,
        "section": s.section.name,
        "status": s.status
    } for s in students])


@api_bp.route('/admin/students/<int:id>', methods=['PUT'])
@login_required
@admin_api_required
def api_update_student(id):
    stu = Student.query.get_or_404(id)
    data = request.get_json() or request.form

    stu.student_name = data.get('student_name', stu.student_name).strip()
    stu.email = data.get('email', stu.email).strip().lower()
    stu.status = data.get('status', stu.status)

    # Check for section transfer or semester promotion (BL-11)
    new_sec_id = data.get('section_id')
    new_sem_id = data.get('semester_id')
    new_year_id = data.get('academic_year_id')

    if new_sec_id and int(new_sec_id) != stu.section_id:
        stu.section_id = int(new_sec_id)
    if new_sem_id and int(new_sem_id) != stu.current_semester_id:
        stu.current_semester_id = int(new_sem_id)
    if new_year_id and int(new_year_id) != stu.academic_year_id:
        stu.academic_year_id = int(new_year_id)

    # Record / update enrollment record preserving history (BL-10, BL-11)
    existing_enroll = StudentEnrollment.query.filter_by(
        student_id=stu.id,
        year_id=stu.academic_year_id,
        semester_id=stu.current_semester_id
    ).first()

    if existing_enroll:
        existing_enroll.section_id = stu.section_id
    else:
        new_enroll = StudentEnrollment(
            student_id=stu.id,
            year_id=stu.academic_year_id,
            programme_id=stu.programme_id,
            semester_id=stu.current_semester_id,
            section_id=stu.section_id,
            status='active'
        )
        db.session.add(new_enroll)

    db.session.commit()
    log_action('API_UPDATE_STUDENT', 'Student', entity_id=stu.id, updated_value={'name': stu.student_name, 'status': stu.status})
    return api_response(True, "Student updated successfully", data={"id": stu.id, "register_number": stu.register_number})


@api_bp.route('/admin/students/import', methods=['POST'])
@login_required
@admin_api_required
def api_import_students():
    file = request.files.get('file')
    prog_id = request.form.get('programme_id', type=int)
    year_id = request.form.get('academic_year_id', type=int)
    sem_id = request.form.get('semester_id', type=int)
    sec_id = request.form.get('section_id', type=int)

    if not file:
        return api_response(False, "File upload required", status_code=400)

    try:
        import pandas as pd
        if file.filename.lower().endswith('.csv'):
            df = pd.read_csv(file, dtype=str)
        else:
            df = pd.read_excel(file, dtype=str)

        reg_col, name_col, email_col = None, None, None
        for c in df.columns:
            cup = str(c).upper().strip()
            if 'REG' in cup: reg_col = c
            elif 'NAME' in cup: name_col = c
            elif 'EMAIL' in cup: email_col = c

        if not reg_col or not name_col:
            return api_response(False, "Missing required columns: Register Number and Student Name", status_code=400)

        added = 0
        skipped = 0
        for _, row in df.iterrows():
            r = str(row[reg_col]).strip().upper()
            n = str(row[name_col]).strip()
            e = str(row[email_col]).strip().lower() if email_col and pd.notna(row[email_col]) else None
            if not r or r == 'NAN': continue

            if Student.query.filter_by(register_number=r).first():
                skipped += 1
                continue

            stu = Student(
                register_number=r, student_id_code=r, student_name=n,
                programme_id=prog_id, academic_year_id=year_id, current_semester_id=sem_id,
                section_id=sec_id, email=e, status='Active'
            )
            db.session.add(stu)
            db.session.flush()

            enroll = StudentEnrollment(
                student_id=stu.id, year_id=year_id, programme_id=prog_id,
                semester_id=sem_id, section_id=sec_id, status='active'
            )
            db.session.add(enroll)
            added += 1

        db.session.commit()
        return api_response(True, f"Bulk import complete: {added} added, {skipped} duplicates skipped", data={"added": added, "skipped": skipped})
    except Exception as ex:
        db.session.rollback()
        return api_response(False, f"Failed to parse file: {str(ex)}", status_code=400)


@api_bp.route('/admin/faculty', methods=['GET', 'POST'])
@login_required
@admin_api_required
def api_faculty():
    if request.method == 'POST':
        data = request.get_json() or request.form
        code = data.get('faculty_id_code', '').strip().upper()
        name = data.get('name', '').strip()
        email = data.get('email', '').strip().lower()
        dept = data.get('department', '').strip()
        desig = data.get('designation', '').strip()
        username = data.get('username', '').strip()
        password = data.get('password', '').strip() or 'Faculty@123'

        # BL-02: Unique faculty username
        if User.query.filter_by(username=username).first():
            return api_response(False, f"Username '{username}' already exists (BL-02)", status_code=400)
        if Faculty.query.filter((Faculty.faculty_id_code == code) | (Faculty.email == email)).first():
            return api_response(False, "Faculty code or email already in use", status_code=400)

        fac = Faculty(faculty_id_code=code, name=name, email=email, department=dept, designation=desig, status='Active')
        db.session.add(fac)
        db.session.flush()

        user = User(username=username, role='faculty', faculty_id=fac.id, is_active=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return api_response(True, "Faculty account created", data={"id": fac.id, "username": username, "faculty_name": name})

    faculty_list = Faculty.query.order_by(Faculty.name.asc()).all()
    return api_response(True, "Faculty list retrieved", data=[{
        "id": f.id, "code": f.faculty_id_code, "name": f.name, "email": f.email, "department": f.department, "status": f.status
    } for f in faculty_list])


@api_bp.route('/admin/subjects', methods=['GET', 'POST'])
@login_required
@admin_api_required
def api_subjects():
    if request.method == 'POST':
        data = request.get_json() or request.form
        code = data.get('subject_code', '').strip().upper()
        name = data.get('subject_name', '').strip()
        prog_id = data.get('programme_id')
        sem_id = data.get('semester_id')
        credits = int(data.get('credits', 3))
        ica_max = float(data.get('ica_max', 50.0))
        tee_max = float(data.get('tee_max', 100.0))

        if Subject.query.filter_by(subject_code=code, programme_id=prog_id, semester_id=sem_id).first():
            return api_response(False, f"Subject '{code}' already exists for this programme/sem", status_code=400)

        subj = Subject(subject_code=code, subject_name=name, programme_id=prog_id, semester_id=sem_id, credits=credits, ica_max=ica_max, tee_max=tee_max, status='Active')
        db.session.add(subj)
        db.session.commit()
        return api_response(True, "Subject created", data={"id": subj.id, "code": subj.subject_code, "name": subj.subject_name})

    subjects = Subject.query.order_by(Subject.subject_code.asc()).all()
    return api_response(True, "Subjects retrieved", data=[{
        "id": s.id, "code": s.subject_code, "name": s.subject_name, "credits": s.credits, "ica_max": s.ica_max, "tee_max": s.tee_max
    } for s in subjects])


@api_bp.route('/admin/mappings', methods=['GET', 'POST'])
@login_required
@admin_api_required
def api_mappings():
    if request.method == 'POST':
        data = request.get_json() or request.form
        year_id = data.get('academic_year_id')
        prog_id = data.get('programme_id')
        sem_id = data.get('semester_id')
        sec_id = data.get('section_id')
        subj_id = data.get('subject_id')
        fac_id = data.get('faculty_id')

        # Check duplicate allocation
        if FacultySubjectMapping.query.filter_by(
            academic_year_id=year_id, programme_id=prog_id, semester_id=sem_id,
            section_id=sec_id, subject_id=subj_id, faculty_id=fac_id
        ).first():
            return api_response(False, "Duplicate active allocation detected for this faculty and class", status_code=400)

        mapping = FacultySubjectMapping(
            academic_year_id=year_id, programme_id=prog_id, semester_id=sem_id,
            section_id=sec_id, subject_id=subj_id, faculty_id=fac_id, status='Active'
        )
        db.session.add(mapping)
        db.session.flush()

        # Seed balanced ICA distribution + TEE matching subject limits
        from app.services.assessment_service import seed_default_assessments_for_mapping
        seed_default_assessments_for_mapping(mapping)

        db.session.commit()
        return api_response(True, "Allocation created", data={"mapping_id": mapping.id, "display_title": mapping.display_title})

    mappings = FacultySubjectMapping.query.order_by(FacultySubjectMapping.id.desc()).all()
    return api_response(True, "Allocations retrieved", data=[{
        "id": m.id, "subject": m.subject.subject_code, "section": m.section.name, "faculty": m.faculty.name, "status": m.status
    } for m in mappings])


@api_bp.route('/admin/mappings/<int:id>', methods=['PUT'])
@login_required
@admin_api_required
def api_update_mapping(id):
    mapping = FacultySubjectMapping.query.get_or_404(id)
    data = request.get_json() or request.form

    if 'is_active' in data:
        mapping.status = 'Active' if bool(data['is_active']) else 'Inactive'
    if 'status' in data:
        mapping.status = data['status']

    db.session.commit()
    return api_response(True, "Mapping updated", data={"id": mapping.id, "status": mapping.status})


@api_bp.route('/admin/assessments', methods=['POST'])
@login_required
@admin_api_required
def api_configure_assessment():
    data = request.get_json() or request.form
    mapping_id = data.get('mapping_id')
    name = data.get('assessment_name', '').strip()
    atype = data.get('assessment_type', 'Test')
    max_m = float(data.get('maximum_marks', 20.0))
    weight = float(data.get('weightage', 100.0))

    if max_m <= 0:
        return api_response(False, "Maximum marks must be greater than zero", status_code=400)

    mapping = FacultySubjectMapping.query.get_or_404(mapping_id)
    ass = Assessment.query.filter_by(mapping_id=mapping.id, assessment_name=name).first()

    if ass:
        ass.max_marks = max_m
        ass.weightage = weight
        ass.assessment_type = atype
    else:
        ass = Assessment(mapping_id=mapping.id, assessment_name=name, assessment_type=atype, max_marks=max_m, weightage=weight)
        db.session.add(ass)

    db.session.commit()
    return api_response(True, "Assessment component configured", data={"assessment_id": ass.id, "name": ass.assessment_name, "max_marks": ass.max_marks})


@api_bp.route('/admin/marks', methods=['GET'])
@login_required
@admin_api_required
def api_admin_marks():
    mapping_id = request.args.get('mapping_id', type=int)
    if not mapping_id:
        return api_response(False, "Parameter 'mapping_id' is required", status_code=400)

    analysis = get_section_analysis(mapping_id)
    return api_response(True, "Consolidated marks retrieved", data={
        "mapping_id": mapping_id,
        "total_enrolled": analysis['total_enrolled'],
        "assessments": analysis['assessments'],
        "grade_distribution": analysis['grade_distribution']
    })


@api_bp.route('/admin/reports', methods=['GET'])
@login_required
@admin_api_required
def api_admin_reports():
    kpis = get_admin_dashboard_kpis()
    return api_response(True, "Consolidated report statistics retrieved", data=kpis)


# ==============================================================================
# 6.3 FACULTY APIS
# ==============================================================================

@api_bp.route('/faculty/dashboard', methods=['GET'])
@login_required
@faculty_api_required
def api_faculty_dashboard():
    analysis = get_faculty_workload_analysis(current_user.faculty_id)
    return api_response(True, "Faculty dashboard metrics retrieved", data={
        "faculty_name": analysis['faculty'].name,
        "subjects_count": analysis['subjects_count'],
        "sections_count": analysis['sections_count'],
        "total_students": analysis['total_students'],
        "overall_completion": analysis['overall_completion'],
        "pending_submissions": analysis['pending_submissions']
    })


@api_bp.route('/faculty/mappings', methods=['GET'])
@login_required
@faculty_api_required
def api_faculty_mappings():
    # BL-03: Faculty can access only assigned mappings
    mappings = FacultySubjectMapping.query.filter_by(
        faculty_id=current_user.faculty_id,
        status='Active'
    ).all()

    return api_response(True, "Assigned mappings retrieved", data=[{
        "mapping_id": m.id,
        "subject_code": m.subject.subject_code,
        "subject_name": m.subject.subject_name,
        "programme": m.programme.code,
        "semester": m.semester.name,
        "section": m.section.name,
        "year": m.academic_year.year_code
    } for m in mappings])


@api_bp.route('/faculty/students/<int:mapping_id>', methods=['GET'])
@login_required
@faculty_api_required
def api_faculty_students(mapping_id):
    # BL-03: Check allocation
    mapping = FacultySubjectMapping.query.filter_by(id=mapping_id, faculty_id=current_user.faculty_id, status='Active').first()
    if not mapping:
        return api_response(False, "Unauthorized: Mapping not assigned to this faculty (BL-03)", status_code=403)

    students = Student.query.filter_by(section_id=mapping.section_id, status='Active').order_by(Student.register_number.asc()).all()
    return api_response(True, "Enrolled students retrieved", data=[{
        "student_id": s.id,
        "register_number": s.register_number,
        "name": s.student_name,
        "email": s.email
    } for s in students])


@api_bp.route('/faculty/assessments/<int:mapping_id>', methods=['GET'])
@login_required
@faculty_api_required
def api_faculty_assessments(mapping_id):
    mapping = FacultySubjectMapping.query.filter_by(id=mapping_id, faculty_id=current_user.faculty_id, status='Active').first()
    if not mapping:
        return api_response(False, "Unauthorized access", status_code=403)

    assessments = Assessment.query.filter_by(mapping_id=mapping.id, is_active=True).order_by(Assessment.order_num.asc()).all()
    return api_response(True, "Assessments retrieved", data=[{
        "assessment_id": a.id,
        "name": a.assessment_name,
        "type": a.assessment_type,
        "max_marks": a.max_marks,
        "order": a.order_num
    } for a in assessments])


@api_bp.route('/faculty/marks/save', methods=['POST'])
@login_required
@faculty_api_required
def api_faculty_save_marks():
    """
    BL-04, BL-05, BL-06, BL-07, BL-08, BL-09:
    Save marks with validation: 0 <= score <= max_marks, check locks, record marks_audit.
    """
    data = request.get_json() or {}
    mapping_id = data.get('mapping_id')
    marks_list = data.get('marks', [])  # list of {student_id, assessment_id, score, status}

    mapping = FacultySubjectMapping.query.filter_by(id=mapping_id, faculty_id=current_user.faculty_id, status='Active').first()
    if not mapping:
        return api_response(False, "Unauthorized mapping access (BL-03)", status_code=403)

    # BL-07, BL-08: Check submission lock status
    sub = Submission.query.filter_by(mapping_id=mapping.id).order_by(Submission.id.desc()).first()
    if sub and sub.status in ['Submitted', 'Under Review', 'Approved']:
        return api_response(False, f"Marks entry is locked (Submission Status: {sub.status}) (BL-07, BL-08)", status_code=400)

    # Validation errors collection
    validation_errors = []
    saved_count = 0

    for item in marks_list:
        stu_id = item.get('student_id')
        ass_id = item.get('assessment_id')
        raw_val = item.get('score')
        status = item.get('status', 'Present')

        student = Student.query.get(stu_id)
        ass = Assessment.query.get(ass_id)

        if not student or not ass or ass.mapping_id != mapping.id:
            validation_errors.append({"student_id": stu_id, "error": "Invalid student or assessment reference"})
            continue

        score = None
        if status in ['Absent', 'absent', 'AB']:
            status = 'Absent'
        elif status in ['Exempted', 'exempted', 'EX']:
            status = 'Exempted'
        elif raw_val is not None and str(raw_val).strip() not in ['', '-']:
            try:
                score = float(raw_val)
                # BL-05, BL-06: 0 <= score <= max_marks
                if score < 0:
                    validation_errors.append({"register_number": student.register_number, "field": ass.assessment_name, "error": f"Score cannot be negative ({score}) (BL-06)"})
                    continue
                if score > ass.max_marks:
                    validation_errors.append({"register_number": student.register_number, "field": ass.assessment_name, "error": f"Marks ({score}) exceed maximum marks ({ass.max_marks}) (BL-05)"})
                    continue
                status = 'Present'
            except (ValueError, TypeError):
                validation_errors.append({"register_number": student.register_number, "field": ass.assessment_name, "error": f"Invalid non-numeric score '{raw_val}'"})
                continue
        else:
            # Empty mark
            mark = Mark.query.filter_by(student_id=stu_id, assessment_id=ass_id, mapping_id=mapping.id).first()
            if mark:
                db.session.delete(mark)
            continue

        mark = Mark.query.filter_by(student_id=stu_id, assessment_id=ass_id, mapping_id=mapping.id).first()
        old_score = mark.score if mark else None

        if mark:
            mark.score = score
            mark.status = status
            mark.updated_at = datetime.utcnow()
        else:
            mark = Mark(
                student_id=stu_id,
                assessment_id=ass_id,
                mapping_id=mapping.id,
                score=score,
                status=status
            )
            db.session.add(mark)
            db.session.flush()

        # BL-09: Log to marks_audit if modified
        if old_score != score:
            audit_entry = MarksAudit(
                mark_id=mark.id,
                old_marks=old_score,
                new_marks=score,
                changed_by=current_user.id,
                reason="Faculty table entry/update"
            )
            db.session.add(audit_entry)
        saved_count += 1

    if validation_errors:
        return api_response(False, "Validation failed", errors=validation_errors, status_code=400)

    db.session.commit()
    return api_response(True, "Marks saved successfully", data={
        "mapping_id": mapping.id,
        "saved_records": saved_count,
        "status": "draft"
    })


@api_bp.route('/faculty/marks/<int:assessment_id>', methods=['GET'])
@login_required
@faculty_api_required
def api_faculty_get_marks(assessment_id):
    ass = Assessment.query.get_or_404(assessment_id)
    mapping = FacultySubjectMapping.query.filter_by(id=ass.mapping_id, faculty_id=current_user.faculty_id).first()
    if not mapping:
        return api_response(False, "Unauthorized access", status_code=403)

    marks = Mark.query.filter_by(assessment_id=ass.id).all()
    return api_response(True, "Assessment marks retrieved", data={
        "assessment_id": ass.id,
        "assessment_name": ass.assessment_name,
        "max_marks": ass.max_marks,
        "marks": [{
            "student_id": m.student_id,
            "register_number": m.student.register_number,
            "score": m.score,
            "status": m.status
        } for m in marks]
    })


@api_bp.route('/faculty/submit/<int:assessment_id>', methods=['POST'])
@login_required
@faculty_api_required
def api_faculty_submit_marks(assessment_id):
    """Submits marks for formal review (Draft -> Submitted)"""
    ass = Assessment.query.get_or_404(assessment_id)
    mapping = FacultySubjectMapping.query.filter_by(id=ass.mapping_id, faculty_id=current_user.faculty_id).first()
    if not mapping:
        return api_response(False, "Unauthorized", status_code=403)

    sub = Submission.query.filter_by(mapping_id=mapping.id, assessment_id=ass.id).first()
    if not sub:
        sub = Submission(mapping_id=mapping.id, assessment_id=ass.id, submitted_by_id=current_user.id)
        db.session.add(sub)

    sub.status = 'Submitted'
    sub.submission_date = datetime.utcnow()
    db.session.commit()
    log_action('API_SUBMIT_MARKS', 'Submission', entity_id=sub.id)
    return api_response(True, "Marks submitted for administrative review", data={"submission_id": sub.id, "status": "submitted"})


@api_bp.route('/faculty/reports', methods=['GET'])
@login_required
@faculty_api_required
def api_faculty_reports():
    analysis = get_faculty_workload_analysis(current_user.faculty_id)
    return api_response(True, "Faculty performance report retrieved", data={
        "overall_completion": analysis['overall_completion'],
        "allocations_count": analysis['total_allocations'],
        "students_count": analysis['total_students']
    })


# ==============================================================================
# FRONTEND INTERACTIVE AJAX & CASCADE HELPERS
# ==============================================================================

@api_bp.route('/cascade/sections')
@login_required
def get_sections():
    prog_id = request.args.get('programme_id', type=int)
    year_id = request.args.get('academic_year_id', type=int)
    sem_id = request.args.get('semester_id', type=int)

    q = Section.query.filter_by(is_active=True)
    if prog_id:
        q = q.filter_by(programme_id=prog_id)
    if year_id:
        q = q.filter_by(academic_year_id=year_id)
    if sem_id:
        q = q.filter_by(semester_id=sem_id)

    sections = q.order_by(Section.name.asc()).all()
    return jsonify([{'id': s.id, 'name': s.name, 'display': s.display_name} for s in sections])


@api_bp.route('/cascade/subjects')
@login_required
def get_subjects():
    prog_id = request.args.get('programme_id', type=int)
    sem_id = request.args.get('semester_id', type=int)

    q = Subject.query.filter_by(status='Active')
    if prog_id:
        q = q.filter_by(programme_id=prog_id)
    if sem_id:
        q = q.filter_by(semester_id=sem_id)

    subjects = q.order_by(Subject.subject_code.asc()).all()
    return jsonify([{'id': s.id, 'code': s.subject_code, 'name': s.subject_name, 'display': f"{s.subject_code} - {s.subject_name}"} for s in subjects])


@api_bp.route('/analytics/section/<int:mapping_id>')
@login_required
def section_chart_data(mapping_id):
    mapping = FacultySubjectMapping.query.get_or_404(mapping_id)
    if current_user.is_faculty_role and mapping.faculty_id != current_user.faculty_id:
        return jsonify({'error': 'Unauthorized'}), 403

    analysis = get_section_analysis(mapping_id)
    
    labels = [a['name'] for a in analysis['assessments']]
    averages = [a['average'] for a in analysis['assessments']]
    highest = [a['highest'] for a in analysis['assessments']]
    lowest = [a['lowest'] for a in analysis['assessments']]
    pass_pcts = [a['pass_percentage'] for a in analysis['assessments']]

    grade_labels = list(analysis['grade_distribution'].keys())
    grade_counts = list(analysis['grade_distribution'].values())

    return jsonify({
        'assessment_labels': labels,
        'averages': averages,
        'highest': highest,
        'lowest': lowest,
        'pass_percentages': pass_pcts,
        'grade_labels': grade_labels,
        'grade_counts': grade_counts,
        'total_enrolled': analysis['total_enrolled']
    })


@api_bp.route('/marks/quick-save', methods=['POST'])
@login_required
def quick_save_mark():
    """AJAX single-cell auto-save for interactive marks grid"""
    data = request.get_json() or {}
    student_id = data.get('student_id')
    assessment_id = data.get('assessment_id')
    mapping_id = data.get('mapping_id')
    raw_val = str(data.get('value', '')).strip().upper()

    mapping = FacultySubjectMapping.query.get_or_404(mapping_id)
    if current_user.is_faculty_role and mapping.faculty_id != current_user.faculty_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    sub = Submission.query.filter_by(mapping_id=mapping.id).order_by(Submission.id.desc()).first()
    if sub and sub.status in ['Submitted', 'Under Review', 'Approved']:
        return jsonify({'success': False, 'message': 'Entry locked: Submission is under review or approved.'}), 400

    ass = Assessment.query.get_or_404(assessment_id)
    mark = Mark.query.filter_by(student_id=student_id, assessment_id=assessment_id, mapping_id=mapping_id).first()

    if raw_val in ['', '-']:
        if mark:
            db.session.delete(mark)
            db.session.commit()
        return jsonify({'success': True, 'action': 'deleted', 'display': '-'})

    if raw_val in ['AB', 'ABSENT']:
        status = 'Absent'
        score = None
    elif raw_val in ['EX', 'EXEMPT', 'EXEMPTED']:
        status = 'Exempted'
        score = None
    else:
        try:
            score = float(raw_val)
            if score < 0 or score > ass.max_marks:
                return jsonify({'success': False, 'message': f"Score cannot exceed {ass.max_marks} or be negative."}), 400
            status = 'Present'
        except ValueError:
            return jsonify({'success': False, 'message': "Enter a valid number, 'AB', or 'EX'."}), 400

    old_score = mark.score if mark else None
    old_status = mark.status if mark else None
    is_new = (mark is None)
    if mark:
        mark.score = score
        mark.status = status
        mark.updated_at = datetime.utcnow()
    else:
        mark = Mark(
            student_id=student_id,
            assessment_id=assessment_id,
            mapping_id=mapping_id,
            score=score,
            status=status
        )
        db.session.add(mark)
        db.session.flush()

    if is_new or old_score != score or old_status != status:
        audit_entry = MarksAudit(
            mark_id=mark.id,
            old_marks=old_score,
            new_marks=score,
            changed_by=current_user.id,
            reason="AJAX quick-save"
        )
        db.session.add(audit_entry)

    db.session.commit()
    display_str = 'AB' if status == 'Absent' else ('EX' if status == 'Exempted' else f"{score:g}")
    return jsonify({'success': True, 'score': score, 'status': status, 'display': display_str})
