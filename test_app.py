import unittest
import io
import json
from datetime import datetime
from app import create_app
from app.models import (
    db, User, Faculty, Student, StudentEnrollment, AcademicYear, Programme, Semester, Section,
    Subject, FacultySubjectMapping, Assessment, Mark, Submission, AuditLog, MarksAudit
)
from app.services.analytics_service import get_admin_dashboard_kpis, get_section_analysis, get_faculty_workload_analysis
from app.services.excel_service import generate_assessment_template, parse_marks_upload, export_marks_sheet
from app.services.pdf_service import generate_section_marks_pdf, generate_student_grade_card_pdf

class AcademicAssessmentSystemTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
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

if __name__ == '__main__':
    unittest.main()
