import unittest
import io
import json
import os
import tempfile
from datetime import datetime
from app import create_app
from app.config import Config
from app.models import (
    db, User, Faculty, Student, StudentEnrollment, AcademicYear, Programme, Semester, Section,
    Subject, FacultySubjectMapping, Assessment, Mark, Submission, AuditLog, MarksAudit
)
from app.services.analytics_service import (
    get_admin_dashboard_kpis, get_section_analysis, get_faculty_workload_analysis, get_section_consolidated_sheet
)
from app.services.excel_service import (
    generate_assessment_template, parse_marks_upload, export_marks_sheet, export_section_consolidated_excel
)
from app.services.pdf_service import (
    generate_section_marks_pdf, generate_student_grade_card_pdf, generate_section_consolidated_pdf
)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(prefix='aams_test_', suffix='.db')
os.close(_TEST_DB_FD)


class _IsolatedTestConfig(Config):
    """Isolated SQLite test config so test runs never touch live Supabase."""
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{_TEST_DB_PATH.replace(chr(92), '/')}"
    SQLALCHEMY_ENGINE_OPTIONS = {}


class AcademicAssessmentSystemTestCase(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        try:
            if os.path.exists(_TEST_DB_PATH):
                os.remove(_TEST_DB_PATH)
        except OSError:
            pass

    def setUp(self):
        self.app = create_app(_IsolatedTestConfig)
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    def login(self, username, password):
        return self.client.post('/auth/login', data=dict(
            username=username,
            password=password
        ), follow_redirects=True)

    def logout(self):
        return self.client.get('/auth/logout', follow_redirects=True)

    # -------------------------------------------------------------------------
    # 1. Authentication & Basic Role Tests
    # -------------------------------------------------------------------------
    def test_01_authentication_admin(self):
        res = self.login('admin', 'Admin@123')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Institutional Academic Dashboard', res.data)
        self.logout()

    def test_02_authentication_faculty(self):
        res = self.login('faculty_a', 'Faculty@123')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Faculty Assessment Portal', res.data)
        self.logout()

    def test_03_invalid_login(self):
        res = self.login('admin', 'WrongPass')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Invalid username or password', res.data)

    def test_04_admin_dashboard_kpis(self):
        self.login('admin', 'Admin@123')
        kpis = get_admin_dashboard_kpis()
        self.assertGreater(kpis['total_students'], 0)
        self.assertGreater(kpis['total_faculty'], 0)
        self.assertGreater(kpis['total_allocations'], 0)
        self.logout()

    def test_05_admin_pages_accessible(self):
        self.login('admin', 'Admin@123')
        for endpoint in ['/admin/dashboard', '/admin/academic-years', '/admin/programmes', '/admin/semesters', '/admin/sections', '/admin/faculty', '/admin/subjects', '/admin/mappings', '/admin/students', '/admin/marks-review', '/admin/users', '/admin/audit-logs']:
            res = self.client.get(endpoint)
            self.assertEqual(res.status_code, 200, f"Failed accessing {endpoint}")
        self.logout()

    # -------------------------------------------------------------------------
    # 2. TRD Section 13 Essential Test Cases
    # -------------------------------------------------------------------------

    # Essential Test 1: Faculty A must not see Faculty B's subjects
    def test_essential_01_faculty_isolation(self):
        self.login('faculty_a', 'Faculty@123')
        res = self.client.get('/faculty/my-allocations')
        self.assertEqual(res.status_code, 200)
        # Faculty A is assigned MA201 (Sec A) and DS201.
        # Faculty B is assigned MA201 (Sec B).
        # In my-allocations, Faculty A should see Section A, not Section B
        self.assertIn(b'Section A', res.data)
        self.assertNotIn(b'Section B', res.data)
        self.logout()

    # Essential Test 2: Faculty A must not enter marks for an unassigned section
    def test_essential_02_unassigned_section_entry_forbidden(self):
        # Faculty B is assigned mapping id 2
        fac_b = Faculty.query.filter_by(faculty_id_code='FAC002').first()
        b_mapping = FacultySubjectMapping.query.filter_by(faculty_id=fac_b.id).first()

        # Faculty A logs in and attempts to access Faculty B's marks entry page
        self.login('faculty_a', 'Faculty@123')
        res = self.client.get(f'/faculty/allocations/{b_mapping.id}/marks', follow_redirects=True)
        # Must return 403 Forbidden
        self.assertEqual(res.status_code, 403)
        self.logout()

    # Essential Test 3: Admin must be able to view all faculty marks
    def test_essential_03_admin_views_all_marks(self):
        self.login('admin', 'Admin@123')
        mappings = FacultySubjectMapping.query.all()
        for m in mappings:
            res = self.client.get(f'/reports/consolidated?mapping_id={m.id}')
            self.assertEqual(res.status_code, 200)
            self.assertIn(m.subject.subject_code.encode(), res.data)
        self.logout()

    # Essential Test 4: An invalid register number must be rejected during Excel upload
    def test_essential_04_invalid_reg_no_rejected(self):
        mapping = FacultySubjectMapping.query.filter_by(status='Active').first()
        # Create CSV with invalid register number
        csv_data = "Register Number,Student Name,Test 1\nINVALID_9999,Fake Student,15\n"
        file_obj = io.BytesIO(csv_data.encode('utf-8'))
        file_obj.filename = "marks.csv"

        result = parse_marks_upload(file_obj, mapping.id)
        self.assertFalse(result['success'])
        self.assertTrue(any('not enrolled' in err for err in result['errors']))

    # Essential Test 5: Marks exceeding the maximum must be rejected
    def test_essential_05_marks_exceeding_max_rejected(self):
        mapping = FacultySubjectMapping.query.filter_by(status='Active').first()
        ass = Assessment.query.filter_by(mapping_id=mapping.id).first()
        student = Student.query.filter_by(section_id=mapping.section_id).first()

        # Score greater than max_marks (e.g., max is 20, score is 999)
        excess_score = ass.max_marks + 50.0
        csv_data = f"Register Number,Student Name,{ass.assessment_name}\n{student.register_number},{student.student_name},{excess_score}\n"
        file_obj = io.BytesIO(csv_data.encode('utf-8'))
        file_obj.filename = "marks.csv"

        result = parse_marks_upload(file_obj, mapping.id)
        self.assertFalse(result['success'])
        self.assertTrue(any('exceeds maximum' in err for err in result['errors']))

    # Essential Test 6: Submitted marks must be locked
    def test_essential_06_submitted_marks_locked(self):
        # Ensure a submission is in 'Submitted' state
        sub = Submission.query.first()
        sub.status = 'Submitted'
        db.session.commit()

        # Log in as faculty assigned to this mapping
        faculty_user = sub.mapping.faculty.user_account
        self.login(faculty_user.username, 'Faculty@123')

        # Try to post marks to locked mapping
        res = self.client.post(f'/faculty/allocations/{sub.mapping_id}/marks', data={
            'action': 'save_draft'
        }, follow_redirects=True)

        self.assertIn(b'Marks entry is currently locked', res.data)
        self.logout()

    # Essential Test 7: Admin must be able to reopen a submission
    def test_essential_07_admin_reopens_submission(self):
        sub = Submission.query.first()
        sub.status = 'Submitted'
        db.session.commit()

        self.login('admin', 'Admin@123')
        res = self.client.post(f'/admin/submissions/{sub.id}/action', data={
            'action': 'reopen',
            'comments': 'Please check scores for question 2'
        }, follow_redirects=True)

        self.assertEqual(res.status_code, 200)
        self.assertIn(b'has been REOPENED', res.data)

        # Verify DB state
        reopened_sub = Submission.query.get(sub.id)
        self.assertEqual(reopened_sub.status, 'Reopened')
        self.assertEqual(reopened_sub.review_comments, 'Please check scores for question 2')
        self.logout()

    # Essential Test 8: Previous academic year marks must remain unchanged when students are promoted
    def test_essential_08_historical_marks_preserved_on_promotion(self):
        student = Student.query.first()
        old_marks_count = Mark.query.filter_by(student_id=student.id).count()

        # Admin promotes student
        self.login('admin', 'Admin@123')
        target_sem = Semester.query.filter_by(number=student.current_semester.number + 1).first()
        if not target_sem:
            target_sem = Semester.query.filter_by(number=3).first()

        res = self.client.post('/admin/students', data={
            'action': 'promote_semester',
            'student_id': student.id,
            'new_semester_id': target_sem.id,
            'new_section_id': student.section_id
        }, follow_redirects=True)

        self.assertEqual(res.status_code, 200)
        # Check marks count is preserved
        new_marks_count = Mark.query.filter_by(student_id=student.id).count()
        self.assertEqual(old_marks_count, new_marks_count)
        self.logout()

    # Essential Test 9: Changing a faculty mapping must not change historical marks
    def test_essential_09_mapping_change_preserves_marks(self):
        mapping = FacultySubjectMapping.query.filter_by(status='Active').first()
        initial_marks = Mark.query.filter_by(mapping_id=mapping.id).all()
        initial_count = len(initial_marks)

        # Deactivate / toggle mapping
        self.login('admin', 'Admin@123')
        res = self.client.post(f'/admin/mappings/{mapping.id}/toggle-status', follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        # Verify historical marks are untouched
        current_marks = Mark.query.filter_by(mapping_id=mapping.id).all()
        self.assertEqual(len(current_marks), initial_count)

        # Restore active status
        self.client.post(f'/admin/mappings/{mapping.id}/toggle-status', follow_redirects=True)
        self.logout()

    # Essential Test 10: Audit logs must record every authorized marks modification
    def test_essential_10_audit_logs_record_modifications(self):
        initial_audit_count = MarksAudit.query.count()
        mapping = FacultySubjectMapping.query.filter_by(status='Active').first()
        
        # Unlock all submissions for this mapping
        for s in Submission.query.filter_by(mapping_id=mapping.id).all():
            s.status = 'Draft'
        db.session.commit()
        
        # Call quick-save API
        faculty_user = mapping.faculty.user_account
        self.login(faculty_user.username, 'Faculty@123')
        
        ass = Assessment.query.filter_by(mapping_id=mapping.id).first()
        student = Student.query.filter_by(section_id=mapping.section_id).first()
        existing_mark = Mark.query.filter_by(mapping_id=mapping.id, student_id=student.id, assessment_id=ass.id).first()
        old_val = existing_mark.score if (existing_mark and existing_mark.score is not None) else -1
        # Pick a value guaranteed to be different from previous value
        target_score1 = round(ass.max_marks * 0.5, 1)
        target_score2 = round(ass.max_marks * 0.8, 1)
        valid_score = target_score2 if old_val == target_score1 else target_score1

        res = self.client.post('/api/marks/quick-save', json={
            'mapping_id': mapping.id,
            'student_id': student.id,
            'assessment_id': ass.id,
            'value': valid_score
        })
        self.assertEqual(res.status_code, 200, f"Quick save failed: {res.get_data(as_text=True)}")

        # Verify a new MarksAudit row was committed
        new_audit_count = MarksAudit.query.count()
        self.assertGreater(new_audit_count, initial_audit_count)
        self.logout()

    # -------------------------------------------------------------------------
    # 3. TRD Section 6 REST APIs Tests
    # -------------------------------------------------------------------------
    def test_11_rest_api_auth_profile(self):
        # Test login API
        res = self.client.post('/api/auth/login', json={'username': 'admin', 'password': 'Admin@123'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['role'], 'admin')

        # Test profile API
        res2 = self.client.get('/api/auth/profile')
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.get_json()['data']['username'], 'admin')

        # Test logout API
        res3 = self.client.post('/api/auth/logout')
        self.assertEqual(res3.status_code, 200)

    def test_12_rest_api_admin_endpoints(self):
        self.login('admin', 'Admin@123')
        for endpoint in ['/api/admin/dashboard', '/api/admin/academic-years', '/api/admin/programmes', '/api/admin/semesters', '/api/admin/sections', '/api/admin/students', '/api/admin/faculty', '/api/admin/subjects', '/api/admin/mappings']:
            res = self.client.get(endpoint)
            self.assertEqual(res.status_code, 200, f"API {endpoint} failed")
            payload = res.get_json()
            self.assertTrue(payload['success'])
        self.logout()

    def test_13_rest_api_faculty_endpoints(self):
        self.login('faculty_a', 'Faculty@123')
        res = self.client.get('/api/faculty/dashboard')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])

        res2 = self.client.get('/api/faculty/mappings')
        self.assertEqual(res2.status_code, 200)
        data = res2.get_json()['data']
        self.assertGreater(len(data), 0)

        mapping_id = data[0]['mapping_id']
        res3 = self.client.get(f'/api/faculty/students/{mapping_id}')
        self.assertEqual(res3.status_code, 200)

        res4 = self.client.get(f'/api/faculty/assessments/{mapping_id}')
        self.assertEqual(res4.status_code, 200)
        self.logout()

    # -------------------------------------------------------------------------
    # 4. Excel & PDF Services
    # -------------------------------------------------------------------------
    def test_14_excel_and_pdf_generation(self):
        mapping = FacultySubjectMapping.query.filter_by(status='Active').first()
        template_bytes = generate_assessment_template(mapping.id)
        self.assertIsNotNone(template_bytes)
        self.assertGreater(len(template_bytes.getvalue()), 1000)

        pdf_bytes = generate_section_marks_pdf(mapping.id)
        self.assertIsNotNone(pdf_bytes)
        self.assertTrue(pdf_bytes.getvalue().startswith(b'%PDF'))

    def test_15_section_consolidated_all_subjects_and_exports(self):
        self.login('admin', 'Admin@123')
        section = Section.query.filter_by(name='A').first()
        res = self.client.get(f'/reports/consolidated?view_mode=section&section_id={section.id}')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'MA201', res.data)
        self.assertIn(b'CE202', res.data)
        self.assertIn(b'CE203', res.data)

        for fmt in ['xlsx', 'csv', 'pdf']:
            exp = self.client.get(f'/reports/export/section-consolidated/{section.id}/{fmt}')
            self.assertEqual(exp.status_code, 200, f"Export {fmt} failed")
            exp.close()
        self.logout()

    def test_16_flexible_excel_csv_marks_upload_and_numeric_regno(self):
        mapping = FacultySubjectMapping.query.filter_by(status='Active').first()
        # Ensure mapping is unlocked
        for s in Submission.query.filter_by(mapping_id=mapping.id).all():
            s.status = 'Draft'
        # Add numeric-ID student like 70022400622
        num_stu = Student(
            register_number='70022400622',
            student_id_code='70022400622',
            student_name='Numeric Reg Student',
            programme_id=mapping.programme_id,
            academic_year_id=mapping.academic_year_id,
            current_semester_id=mapping.semester_id,
            section_id=mapping.section_id,
            status='Active'
        )
        db.session.add(num_stu)
        db.session.commit()

        # Upload CSV using compact/aliased names ("Test1", "Quiz", "TEE", "Mini Project (10)") and float-like reg ID
        csv_data = (
            "S.No,Reg No,Student Name,Test1,Quiz,Mini Project (10),TEE\n"
            "1,70022400622.0,Numeric Reg Student,18,8,9,88\n"
        )
        file_obj = io.BytesIO(csv_data.encode('utf-8'))
        file_obj.filename = "marks_custom.csv"

        result = parse_marks_upload(file_obj, mapping.id, auto_create=True)
        self.assertTrue(result['success'], f"Expected upload success, got errors: {result.get('errors')}")
        self.assertEqual(len(result['records']), 1)
        self.assertGreaterEqual(len(result['records'][0]['marks']), 4)

        mini_ass = Assessment.query.filter_by(mapping_id=mapping.id, assessment_name='Mini Project').first()
        self.assertIsNotNone(mini_ass)
        self.assertEqual(mini_ass.max_marks, 10.0)
        db.session.rollback()

    def test_17_faculty_custom_ica_distribution(self):
        # Faculty A logs in and configures custom ICA split for their mapping
        self.login('faculty_a', 'Faculty@123')
        fac_a = Faculty.query.filter_by(faculty_id_code='FAC001').first()
        # Use DS201 mapping (unlocked Draft)
        mapping = FacultySubjectMapping.query.filter_by(faculty_id=fac_a.id, status='Active').order_by(FacultySubjectMapping.id.desc()).first()
        for s in Submission.query.filter_by(mapping_id=mapping.id).all():
            s.status = 'Draft'
        db.session.commit()

        # GET config page
        res_get = self.client.get(f'/faculty/allocations/{mapping.id}/ica-distribution')
        self.assertEqual(res_get.status_code, 200)
        self.assertIn(b'Faculty ICA Distribution Setup', res_get.data)

        # POST custom distribution totaling 50 (Test1: 15, Test2: 15, Quiz: 10, Assignment: 10)
        res_post = self.client.post(f'/faculty/allocations/{mapping.id}/ica-distribution', data={
            'component_id[]': ['', '', '', ''],
            'component_name[]': ['Test1', 'Test2', 'Quiz', 'Assignment'],
            'component_type[]': ['Test', 'Test', 'Quiz', 'Assignment'],
            'component_max[]': ['15', '15', '10', '10'],
            'include_tee': '1',
            'tee_max': '100'
        }, follow_redirects=True)
        self.assertEqual(res_post.status_code, 200)
        self.assertIn(b'ICA distribution updated successfully', res_post.data)

        active_asses = Assessment.query.filter_by(mapping_id=mapping.id, is_active=True).order_by(Assessment.order_num.asc()).all()
        names = [a.assessment_name for a in active_asses]
        self.assertEqual(names, ['Test1', 'Test2', 'Quiz', 'Assignment', 'Term End Examination'])
        self.logout()

    def test_18_xlsx_template_roundtrip_http_upload(self):
        # Faculty logs in, downloads official .xlsx template, fills scores, and uploads via POST
        self.login('faculty_a', 'Faculty@123')
        fac_a = Faculty.query.filter_by(faculty_id_code='FAC001').first()
        mapping = FacultySubjectMapping.query.filter_by(faculty_id=fac_a.id, status='Active').order_by(FacultySubjectMapping.id.desc()).first()
        for s in Submission.query.filter_by(mapping_id=mapping.id).all():
            s.status = 'Draft'
        db.session.commit()

        res_tpl = self.client.get(f'/faculty/allocations/{mapping.id}/template')
        self.assertEqual(res_tpl.status_code, 200)

        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(res_tpl.data))
        ws = wb.active
        # Row 9 is first student in generated template; fill first assessment cell
        ws.cell(row=9, column=4, value=14)
        out = io.BytesIO()
        wb.save(out)
        out.seek(0)

        res_up = self.client.post(
            f'/faculty/allocations/{mapping.id}/upload',
            data={'file': (out, 'Marks_Template.xlsx'), 'auto_create_components': '1'},
            content_type='multipart/form-data',
            follow_redirects=True
        )
        self.assertEqual(res_up.status_code, 200)
        self.assertIn(b'Successfully imported', res_up.data)
        self.logout()

    def test_19_renamed_ica_component_and_consolidated_ica_total(self):
        # Reproduce renaming an existing 'ICA' assessment to 'Presentation' while type stays 'ICA',
        # and verify both Faculty Portal and Admin Consolidated Sheets reflect full ICA total (not just Presentation).
        from app.services.assessment_service import split_ica_assessments
        from app.services.analytics_service import get_section_consolidated_sheet

        self.login('faculty_a', 'Faculty@123')
        fac_a = Faculty.query.filter_by(faculty_id_code='FAC001').first()
        mapping = FacultySubjectMapping.query.filter_by(faculty_id=fac_a.id, status='Active').order_by(FacultySubjectMapping.id.desc()).first()
        for s in Submission.query.filter_by(mapping_id=mapping.id).all():
            s.status = 'Draft'
        # Ensure mapping has a seeded 'ICA' row to test legacy rename behavior
        if not Assessment.query.filter_by(mapping_id=mapping.id, assessment_name='ICA').first():
            db.session.add(Assessment(mapping_id=mapping.id, assessment_name='ICA', assessment_type='ICA', max_marks=50.0, order_num=5, is_active=True))
        db.session.commit()

        all_ass = Assessment.query.filter_by(mapping_id=mapping.id, is_active=True).order_by(Assessment.order_num).all()
        ica_row = next((a for a in all_ass if a.assessment_name.upper() == 'ICA'), None)
        test1_row = next((a for a in all_ass if 'TEST 1' in a.assessment_name.upper()), all_ass[0])
        test2_row = next((a for a in all_ass if 'TEST 2' in a.assessment_name.upper()), all_ass[1])
        assign_row = next((a for a in all_ass if 'ASSIGN' in a.assessment_name.upper()), all_ass[2])
        quiz_row = next((a for a in all_ass if 'QUIZ' in a.assessment_name.upper()), all_ass[3])

        # Submit form renaming ICA -> Presentation while leaving type as 'ICA' and unchecking TEE
        res_cfg = self.client.post(f'/faculty/allocations/{mapping.id}/ica-distribution', data={
            'component_id[]': [str(test1_row.id), str(test2_row.id), str(assign_row.id), str(quiz_row.id), str(ica_row.id)],
            'component_name[]': ['Test 1', 'Test 2', 'Assignment', 'Quiz', 'Presentation'],
            'component_type[]': ['Test', 'Test', 'Assignment', 'Quiz', 'ICA'],
            'component_max[]': ['10', '10', '10', '10', '10'],
        }, follow_redirects=True)
        self.assertEqual(res_cfg.status_code, 200)

        active = Assessment.query.filter_by(mapping_id=mapping.id, is_active=True).order_by(Assessment.order_num).all()
        pres = next((a for a in active if a.assessment_name == 'Presentation'), None)
        self.assertIsNotNone(pres)
        self.assertNotEqual(pres.assessment_type, 'ICA')

        # Also simulate legacy DB state where Presentation still has assessment_type='ICA'
        pres.assessment_type = 'ICA'
        db.session.commit()
        internals, explicit_ica, tee_ass = split_ica_assessments(active)
        self.assertIsNone(explicit_ica)
        self.assertIsNone(tee_ass)
        self.assertEqual(len(internals), 5)

        # Enter 9 + 5 + 9 + 5 + 4 = 32 for first student in section
        stu = Student.query.filter_by(section_id=mapping.section_id, status='Active').order_by(Student.register_number.asc()).first()
        Mark.query.filter_by(mapping_id=mapping.id, student_id=stu.id).delete()
        for comp, val in zip(active, [9.0, 5.0, 9.0, 5.0, 4.0]):
            db.session.add(Mark(student_id=stu.id, assessment_id=comp.id, mapping_id=mapping.id, score=val, status='Present'))
        db.session.commit()

        # Verify Faculty Marks Entry treats it as auto-ICA (no explicit standalone ICA column masking components)
        res_marks = self.client.get(f'/faculty/allocations/{mapping.id}/marks')
        self.assertEqual(res_marks.status_code, 200)
        self.assertIn(b'data-has-explicit-ica="false"', res_marks.data)
        self.logout()

        # Verify Admin Consolidated Sheet shows ICA = 32 (not 4) and Total = 32.0 out of 50 (64.0% PASS)
        sheet = get_section_consolidated_sheet(mapping.section_id)
        stu_row = next(r for r in sheet['students_data'] if r['student'].id == stu.id)
        subj_cell = stu_row['subjects'][mapping.id]
        self.assertEqual(subj_cell['ica_disp'], '32')
        self.assertEqual(subj_cell['tee_disp'], '-')
        self.assertEqual(subj_cell['total_score'], 32.0)
        self.assertEqual(subj_cell['total_max'], 50.0)
        self.assertEqual(subj_cell['percentage'], 64.0)
        self.assertTrue(subj_cell['is_pass'])

        self.login('admin', 'Admin@123')
        res_cons = self.client.get(f'/reports/consolidated?view_mode=section&section_id={mapping.section_id}')
        self.assertEqual(res_cons.status_code, 200)
        self.assertIn(b'Total <span class="d-block text-secondary fw-normal" style="font-size: 0.68rem;">(50)</span>', res_cons.data)
        self.logout()

if __name__ == '__main__':
    unittest.main()
