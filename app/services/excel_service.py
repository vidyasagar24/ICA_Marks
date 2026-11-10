import io
import re
import math
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import pandas as pd
from app.models import db, Student, Assessment, Mark, FacultySubjectMapping


def normalize_reg_no(val):
    """Normalize student register numbers across Excel/CSV types (strips trailing .0 on numeric IDs)."""
    if val is None:
        return ''
    if isinstance(val, int) and not isinstance(val, bool):
        return str(val).strip().upper()
    if isinstance(val, float):
        if pd.isna(val):
            return ''
        if val.is_integer():
            return str(int(val)).strip().upper()
    s = str(val).strip()
    if s.endswith('.0') and s[:-2].lstrip('-').isdigit():
        s = s[:-2]
    return s.upper()


def _canon_key(text):
    return re.sub(r'[^A-Z0-9]', '', str(text or '').upper())


def _is_reg_header(val):
    """Match a column header cell representing student register/roll number (ignores prose/instructions rows)."""
    raw = str(val or '').strip()
    if not raw or len(raw) > 45:
        return False
    base = re.split(r'[\n\(\[/]', raw, maxsplit=1)[0].strip()
    u = _canon_key(base)
    return u in {
        'REGISTERNUMBER', 'REGISTERNO', 'REGNO', 'REGNUMBER', 'REG',
        'ROLLNO', 'ROLLNUMBER', 'STUDENTID', 'STUDENTIDCODE', 'PRN', 'SAPID', 'UID'
    }


_SKIP_UPLOAD_COLS = {
    'SNO', 'SRNO', 'SERIAL', 'SERIALNO', 'SLNO', 'SL', 'NO',
    'NAME', 'STUDENTNAME', 'EMAIL', 'EMAILID', 'MAIL', 'PHONE', 'MOBILE',
    'TOTAL', 'TOTALSCORE', 'TOTALSCORED', 'GRANDTOTAL', 'MAX', 'MAXTOTAL', 'MAXMARKS',
    'PERCENTAGE', 'PCT', 'RESULT', 'GRADE', 'DIVISION', 'STATUS', 'REMARKS',
    'PASSFAIL', 'SECTION', 'SEMESTER', 'PROGRAMME', 'BRANCH', 'COURSE', 'SUBJECT', 'SUBJECTCODE', 'FACULTY'
}

_ALIAS_GROUPS = [
    {'TEST1', 'T1', 'UT1', 'CT1', 'IA1', 'MID1', 'UNITTEST1'},
    {'TEST2', 'T2', 'UT2', 'CT2', 'IA2', 'MID2', 'UNITTEST2'},
    {'TEST3', 'T3', 'UT3', 'CT3', 'IA3', 'UNITTEST3'},
    {'QUIZ', 'QUIZ1', 'Q1'},
    {'QUIZ2', 'Q2'},
    {'ASSIGNMENT', 'ASSIGNMENTS', 'ASSIGN', 'ASSG', 'ASSGN', 'HW'},
    {'TEE', 'TERMEND', 'TERMENDEXAM', 'TERMENDEXAMINATION', 'ENDSEM', 'ESE', 'FINAL', 'FINALEXAM', 'THEORY', 'WRITTENEXAM'},
    {'ICA', 'INTERNAL', 'IA', 'INTERNALASSESSMENT', 'CONTINUOUSASSESSMENT'},
    {'MIDTERM', 'MIDSEM', 'MSE', 'MIDTERMEXAM', 'MIDTERMTEST'},
    {'LAB', 'LABPRACTICAL', 'PRACTICAL', 'PRAC'},
]


def _extract_header_meta(col_header):
    """Extract clean assessment base name and optional max marks hint from column header."""
    raw = str(col_header or '').strip()
    max_hint = None
    m = re.search(
        r'(?:MAX\s*[:\-]\s*|/\s*|\(\s*(?:MAX\s*[:\-]?\s*)?|\[\s*(?:MAX\s*[:\-]?\s*)?)(\d+(?:\.\d+)?)\s*[\)\]]?\s*$',
        raw,
        flags=re.IGNORECASE
    )
    if m:
        try:
            val = float(m.group(1))
            if val > 0:
                max_hint = val
        except ValueError:
            pass
    base = raw.split('\n')[0]
    base = re.split(r'[\(\[/]|MAX\s*:', base, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    return base, max_hint


def _match_assessment(base_name, assessments):
    """Match an uploaded column header flexibly against active assessments for the course."""
    upper = base_name.strip().upper()
    canon = _canon_key(base_name)
    if not canon:
        return None

    # 1. Exact case-insensitive match
    for a in assessments:
        if a.assessment_name.strip().upper() == upper:
            return a

    # 2. Alphanumeric canonical match (e.g. 'Test1' <-> 'Test 1', 'Quiz1' <-> 'Quiz 1')
    for a in assessments:
        if _canon_key(a.assessment_name) == canon:
            return a

    # 3. Synonym group match
    for grp in _ALIAS_GROUPS:
        if canon in grp:
            for a in assessments:
                ac = _canon_key(a.assessment_name)
                if ac in grp:
                    return a
            # Also match TEE alias group against assessment_type == 'TEE'
            if 'TEE' in grp:
                for a in assessments:
                    if a.assessment_type == 'TEE':
                        return a
            # Match QUIZ alias against single Quiz type if unambiguous
            if 'QUIZ' in grp:
                quizzes = [a for a in assessments if a.assessment_type == 'Quiz']
                if len(quizzes) == 1:
                    return quizzes[0]
            if 'ASSIGNMENT' in grp:
                assigns = [a for a in assessments if a.assessment_type == 'Assignment']
                if len(assigns) == 1:
                    return assigns[0]
    return None


def _infer_assessment_type(name):
    u = _canon_key(name)
    if any(k in u for k in ('TEE', 'TERMEND', 'ENDSEM', 'FINAL', 'ESE')):
        return 'TEE'
    if 'QUIZ' in u:
        return 'Quiz'
    if 'ASSIGN' in u or 'ASSG' in u or 'HW' in u:
        return 'Assignment'
    if 'MID' in u:
        return 'Mid-Term'
    if 'LAB' in u or 'PRAC' in u:
        return 'Lab'
    if u in ('ICA', 'INTERNAL', 'INTERNALASSESSMENT'):
        return 'ICA'
    if 'TEST' in u or 'UNIT' in u or u.startswith('UT') or u.startswith('CT') or u.startswith('T1') or u.startswith('T2'):
        return 'Test'
    return 'Other'


def _read_spreadsheet_table(file_storage, filename):
    """Load uploaded .xlsx/.xls/.csv locating the Register Number header row automatically."""
    if filename.endswith('.csv'):
        raw_bytes = file_storage.read()
        text = None
        for enc in ('utf-8-sig', 'utf-8', 'latin-1'):
            try:
                text = raw_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise ValueError("Unable to decode CSV file encoding.")
        lines = text.splitlines()
        header_idx = 0
        for i, line in enumerate(lines[:25]):
            cells = [c.strip().strip('"').strip("'") for c in line.split(',')]
            if any(_is_reg_header(c) for c in cells):
                header_idx = i
                break
        return pd.read_csv(io.StringIO(text), skiprows=header_idx, dtype=str)

    # Excel (.xlsx / .xls)
    file_storage.seek(0)
    raw_df = pd.read_excel(file_storage, header=None, dtype=object)
    header_idx = None
    for r_idx in range(min(25, len(raw_df))):
        row_vals = raw_df.iloc[r_idx].tolist()
        if any(_is_reg_header(v) for v in row_vals):
            header_idx = r_idx
            break

    if header_idx is None:
        raise ValueError("Could not locate a 'Register Number' / 'Reg No' column header in the first 25 rows.")

    headers = []
    sub_row = raw_df.iloc[header_idx + 1].tolist() if (header_idx + 1) < len(raw_df) else None
    has_max_subrow = sub_row is not None and any('MAX' in str(v or '').upper() for v in sub_row) and not any(
        normalize_reg_no(v) for i, v in enumerate(sub_row) if _is_reg_header(raw_df.iloc[header_idx].iloc[i])
    )

    raw_headers = raw_df.iloc[header_idx].tolist()
    for idx_c, h in enumerate(raw_headers):
        h_str = '' if (h is None or (isinstance(h, float) and pd.isna(h))) else str(h).strip()
        if not h_str:
            h_str = f"Unnamed_{idx_c}"
        elif has_max_subrow and sub_row[idx_c] is not None and not (isinstance(sub_row[idx_c], float) and pd.isna(sub_row[idx_c])):
            sub_str = str(sub_row[idx_c]).strip()
            if 'MAX' in sub_str.upper() and 'MAX' not in h_str.upper():
                h_str = f"{h_str} ({sub_str})"
        headers.append(h_str)

    data_start = header_idx + (2 if has_max_subrow else 1)
    df = raw_df.iloc[data_start:].copy().reset_index(drop=True)
    df.columns = headers
    return df

def create_styled_header(ws, row, headers, fill_color="1F4E79", font_color="FFFFFF"):
    fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type="solid")
    font = Font(name="Calibri", size=11, bold=True, color=font_color)
    border = Border(
        left=Side(style='thin', color='CCCCCC'),
        right=Side(style='thin', color='CCCCCC'),
        top=Side(style='thin', color='CCCCCC'),
        bottom=Side(style='thin', color='CCCCCC')
    )
    for col_idx, text in enumerate(headers, 1):
        cell = ws.cell(row=row, column=col_idx, value=text)
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border

def auto_fit_columns(ws):
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val = str(cell.value or '')
            if '\n' in val:
                lines = val.split('\n')
                max_len = max(max_len, max(len(line) for line in lines))
            else:
                max_len = max(max_len, len(val))
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

def generate_assessment_template(mapping_id):
    """
    Generate an Excel spreadsheet template for a mapping prefilled with:
    Register Number, Student Name, and Assessment columns with Max Marks.
    """
    mapping = FacultySubjectMapping.query.get_or_404(mapping_id)
    students = Student.query.filter_by(
        section_id=mapping.section_id,
        status='Active'
    ).order_by(Student.register_number.asc()).all()

    assessments = Assessment.query.filter_by(
        mapping_id=mapping.id,
        is_active=True
    ).order_by(Assessment.order_num.asc()).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Marks Entry"

    # Title Banner
    ws.merge_cells("A1:G1")
    title_cell = ws["A1"]
    title_cell.value = "ACADEMIC ASSESSMENT MANAGEMENT SYSTEM - MARKS ENTRY TEMPLATE"
    title_cell.font = Font(name="Calibri", size=14, bold=True, color="1F4E79")
    title_cell.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 28

    # Metadata Details
    meta_info = [
        f"Subject: {mapping.subject.subject_code} - {mapping.subject.subject_name}",
        f"Programme: {mapping.programme.name} ({mapping.programme.code})",
        f"Academic Year: {mapping.academic_year.year_code} | Semester: {mapping.semester.name} | Section: {mapping.section.name}",
        f"Faculty: {mapping.faculty.name} ({mapping.faculty.faculty_id_code})",
        "Instructions: Enter numeric score, 'AB' for Absent, or 'EX' for Exempted. Do not modify Register Number."
    ]
    for r_idx, info in enumerate(meta_info, 2):
        ws.cell(row=r_idx, column=1, value=info).font = Font(name="Calibri", size=10, italic=(r_idx == 6), color="333333")
        ws.row_dimensions[r_idx].height = 18

    # Table Headers
    header_row = 8
    headers = ["S.No", "Register Number", "Student Name"]
    for ass in assessments:
        headers.append(f"{ass.assessment_name}\n(Max: {ass.max_marks})")

    create_styled_header(ws, header_row, headers)
    ws.row_dimensions[header_row].height = 28

    # Existing marks cache
    marks_map = {}
    existing_marks = Mark.query.filter_by(mapping_id=mapping.id).all()
    for m in existing_marks:
        marks_map[(m.student_id, m.assessment_id)] = m

    # Data Rows
    thin_border = Border(
        left=Side(style='thin', color='E0E0E0'),
        right=Side(style='thin', color='E0E0E0'),
        top=Side(style='thin', color='E0E0E0'),
        bottom=Side(style='thin', color='E0E0E0')
    )

    data_start = 9
    for idx, stu in enumerate(students, 1):
        curr_row = data_start + idx - 1
        ws.row_dimensions[curr_row].height = 20
        
        c1 = ws.cell(row=curr_row, column=1, value=idx)
        c1.alignment = Alignment(horizontal="center")
        c1.border = thin_border
        
        c2 = ws.cell(row=curr_row, column=2, value=stu.register_number)
        c2.alignment = Alignment(horizontal="center")
        c2.font = Font(bold=True)
        c2.border = thin_border
        
        c3 = ws.cell(row=curr_row, column=3, value=stu.student_name)
        c3.border = thin_border

        for col_idx, ass in enumerate(assessments, 4):
            val = None
            mark_entry = marks_map.get((stu.id, ass.id))
            if mark_entry:
                if mark_entry.status == 'Absent':
                    val = 'AB'
                elif mark_entry.status == 'Exempted':
                    val = 'EX'
                elif mark_entry.score is not None:
                    val = mark_entry.score
            
            cell = ws.cell(row=curr_row, column=col_idx, value=val)
            cell.alignment = Alignment(horizontal="center")
            cell.border = thin_border

    auto_fit_columns(ws)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def _col_has_mark_values(series):
    """Return True if column contains at least one valid mark entry (numeric, AB, EX)."""
    for v in series:
        if pd.isna(v):
            continue
        s = str(v).strip().upper()
        if not s or s == '-':
            continue
        if s in ('AB', 'ABSENT', 'EX', 'EXEMPT', 'EXEMPTED'):
            return True
        try:
            float(s)
            return True
        except ValueError:
            return False
    return False


def parse_marks_upload(file_storage, mapping_id, auto_create=False):
    """
    Parse uploaded Excel / CSV file for marks entry.
    Supports flexible column names (e.g. Test1, Test 1, Quiz, TEE), numeric register IDs,
    and optional automatic creation of custom faculty ICA components.
    """
    mapping = FacultySubjectMapping.query.get_or_404(mapping_id)
    students = Student.query.filter_by(section_id=mapping.section_id).all()
    student_by_reg = {}
    for s in students:
        r1 = normalize_reg_no(s.register_number)
        if r1:
            student_by_reg[r1] = s
        r2 = normalize_reg_no(s.student_id_code)
        if r2 and r2 not in student_by_reg:
            student_by_reg[r2] = s

    all_assessments = Assessment.query.filter_by(mapping_id=mapping.id).order_by(Assessment.order_num.asc()).all()
    active_assessments = [a for a in all_assessments if a.is_active]
    all_by_name = {a.assessment_name.strip().upper(): a for a in all_assessments}

    filename = (file_storage.filename or '').lower()
    errors = []
    warnings = []
    records = []
    auto_created_names = []

    try:
        df = _read_spreadsheet_table(file_storage, filename)
    except Exception as e:
        return {'success': False, 'errors': [f"Failed to read file: {str(e)}"]}

    df.columns = [str(c).strip() for c in df.columns]

    # Locate Register Number column
    reg_col = None
    for c in df.columns:
        if _is_reg_header(c):
            reg_col = c
            break

    if not reg_col:
        return {'success': False, 'errors': ["Column 'Register Number' (or 'Reg No') is missing in the uploaded sheet."]}

    # Map sheet columns to existing active assessments or auto-create custom ICA columns
    col_to_assessment = {}
    matched_ass_ids = set()
    next_order = (max((a.order_num for a in all_assessments), default=0) + 1)

    for c in df.columns:
        if c == reg_col:
            continue
        cup = c.upper()
        if cup.startswith('UNNAMED'):
            continue
        base_name, max_hint = _extract_header_meta(c)
        canon_base = _canon_key(base_name)
        if not canon_base or canon_base in _SKIP_UPLOAD_COLS or 'NAME' in cup or 'S.NO' in cup or 'SERIAL' in cup:
            continue

        matched_ass = _match_assessment(base_name, active_assessments)
        if matched_ass and matched_ass.id not in matched_ass_ids:
            col_to_assessment[c] = matched_ass
            matched_ass_ids.add(matched_ass.id)
        elif not matched_ass and auto_create and _col_has_mark_values(df[c]):
            # Determine reasonable max marks from header or observed scores
            inferred_max = max_hint
            if not inferred_max:
                numeric_vals = []
                for v in df[c]:
                    try:
                        if not pd.isna(v) and str(v).strip() not in ('', '-', 'AB', 'ABSENT', 'EX', 'EXEMPT', 'EXEMPTED'):
                            numeric_vals.append(float(v))
                    except ValueError:
                        pass
                top_val = max(numeric_vals) if numeric_vals else 20.0
                inferred_max = float(max(20.0, math.ceil(top_val / 5.0) * 5.0))

            existing_inactive = all_by_name.get(base_name.upper())
            if existing_inactive:
                existing_inactive.is_active = True
                if max_hint:
                    existing_inactive.max_marks = inferred_max
                target_ass = existing_inactive
            else:
                target_ass = Assessment(
                    mapping_id=mapping.id,
                    assessment_name=base_name[:80],
                    assessment_type=_infer_assessment_type(base_name),
                    max_marks=inferred_max,
                    order_num=next_order,
                    is_active=True
                )
                db.session.add(target_ass)
                db.session.flush()
                all_by_name[base_name.upper()] = target_ass
                next_order += 1

            col_to_assessment[c] = target_ass
            matched_ass_ids.add(target_ass.id)
            active_assessments.append(target_ass)
            auto_created_names.append(f"{target_ass.assessment_name} (Max: {target_ass.max_marks:g})")

    if not col_to_assessment:
        expected = ', '.join(a.assessment_name for a in active_assessments) or 'Test 1, Test 2, Quiz, Assignment'
        return {
            'success': False,
            'errors': [f"No matching assessment columns found in the sheet. Expected one of: {expected}"]
        }

    # Iterate rows and validate
    for idx, row in df.iterrows():
        reg_no = normalize_reg_no(row.get(reg_col))
        if not reg_no:
            continue

        student = student_by_reg.get(reg_no)
        if not student:
            errors.append(f"Row {idx + 2}: Register Number '{reg_no}' is not enrolled in this section.")
            continue

        stu_marks = {}
        for col, ass in col_to_assessment.items():
            val = row.get(col)
            if pd.isna(val) or str(val).strip() == '' or str(val).strip() == '-':
                continue

            sval = str(val).strip().upper()
            if sval in ['AB', 'ABSENT']:
                stu_marks[ass.id] = {'score': None, 'status': 'Absent'}
            elif sval in ['EX', 'EXEMPT', 'EXEMPTED']:
                stu_marks[ass.id] = {'score': None, 'status': 'Exempted'}
            else:
                try:
                    num_val = float(sval)
                    if num_val < 0:
                        errors.append(f"Row {idx + 2} ({reg_no}): {ass.assessment_name} score cannot be negative ({num_val}).")
                    elif num_val > ass.max_marks:
                        errors.append(f"Row {idx + 2} ({reg_no}): {ass.assessment_name} score ({num_val}) exceeds maximum marks ({ass.max_marks}).")
                    else:
                        stu_marks[ass.id] = {'score': num_val, 'status': 'Present'}
                except ValueError:
                    errors.append(f"Row {idx + 2} ({reg_no}): Invalid score '{val}' for {ass.assessment_name}. Must be numeric, 'AB', or 'EX'.")

        records.append({
            'student_id': student.id,
            'reg_no': student.register_number,
            'student_name': student.student_name,
            'marks': stu_marks
        })

    if errors:
        db.session.rollback()
        return {'success': False, 'errors': errors, 'records': []}

    if auto_created_names:
        warnings.append(f"Added custom assessment column(s) from your spreadsheet: {', '.join(auto_created_names)}")

    return {
        'success': True,
        'records': records,
        'matched_count': len(records),
        'assessments_updated': [a.assessment_name for a in col_to_assessment.values()],
        'warnings': warnings
    }


def generate_student_import_template():
    """Generates an Excel template for bulk student upload"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Students"

    headers = ["Register Number", "Student Name", "Email", "Status"]
    create_styled_header(ws, 1, headers, fill_color="203764")

    # Sample data
    samples = [
        ["2026CE001", "Aarav Sharma", "aarav.sharma@univ.edu", "Active"],
        ["2026CE002", "Diya Patel", "diya.patel@univ.edu", "Active"],
        ["2026CE003", "Rohan Mehta", "rohan.mehta@univ.edu", "Active"],
    ]
    for r_idx, sample in enumerate(samples, 2):
        for c_idx, val in enumerate(sample, 1):
            cell = ws.cell(row=r_idx, column=c_idx, value=val)
            if c_idx == 1:
                cell.font = Font(bold=True)

    auto_fit_columns(ws)
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def export_marks_sheet(mapping_id, format='xlsx'):
    """Export complete marks table as Excel or CSV"""
    mapping = FacultySubjectMapping.query.get_or_404(mapping_id)
    students = Student.query.filter_by(section_id=mapping.section_id).order_by(Student.register_number.asc()).all()
    assessments = Assessment.query.filter_by(mapping_id=mapping.id, is_active=True).order_by(Assessment.order_num.asc()).all()
    
    marks_map = {}
    existing_marks = Mark.query.filter_by(mapping_id=mapping.id).all()
    for m in existing_marks:
        marks_map[(m.student_id, m.assessment_id)] = m

    rows = []
    for idx, stu in enumerate(students, 1):
        row_dict = {
            "S.No": idx,
            "Register Number": stu.register_number,
            "Student Name": stu.student_name
        }
        total_scored = 0.0
        total_max = 0.0
        for ass in assessments:
            m = marks_map.get((stu.id, ass.id))
            if m:
                if m.status == 'Absent':
                    row_dict[f"{ass.assessment_name} ({ass.max_marks})"] = 'AB'
                elif m.status == 'Exempted':
                    row_dict[f"{ass.assessment_name} ({ass.max_marks})"] = 'EX'
                elif m.score is not None:
                    row_dict[f"{ass.assessment_name} ({ass.max_marks})"] = m.score
                    total_scored += m.score
                    total_max += ass.max_marks
                else:
                    row_dict[f"{ass.assessment_name} ({ass.max_marks})"] = '-'
            else:
                row_dict[f"{ass.assessment_name} ({ass.max_marks})"] = '-'
            if not m or m.score is None:
                total_max += ass.max_marks

        pct = (total_scored / total_max * 100) if total_max > 0 else 0
        row_dict["Total Score"] = round(total_scored, 2)
        row_dict["Max Total"] = round(total_max, 2)
        row_dict["Percentage (%)"] = round(pct, 2)
        rows.append(row_dict)

    df = pd.DataFrame(rows)

    if format == 'csv':
        output = io.StringIO()
        df.to_csv(output, index=False)
        return io.BytesIO(output.getvalue().encode('utf-8'))
    else:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name="Consolidated Marks", index=False)
        output.seek(0)
        return output


def export_section_consolidated_excel(section_id, format='xlsx'):
    """
    Export consolidated marks sheet for an entire section across all mapped subjects.
    Supports .xlsx with professional two-tier styling and .csv.
    """
    from app.services.analytics_service import get_section_consolidated_sheet
    data = get_section_consolidated_sheet(section_id)
    section = data['section']
    mappings = data['mappings']
    students_data = data['students_data']
    subject_stats = data['subject_stats']
    subject_meta = data.get('subject_meta', {})
    overall_stats = data['overall_stats']

    if format == 'csv':
        rows = []
        for idx, row in enumerate(students_data, 1):
            r = {
                'S.No': idx,
                'Register Number': row['student'].register_number,
                'Student Name': row['student'].student_name
            }
            for m in mappings:
                subj_data = row['subjects'].get(m.id, {})
                code = m.subject.subject_code
                r[f"{code} ICA"] = subj_data.get('ica_disp', '-')
                r[f"{code} TEE"] = subj_data.get('tee_disp', '-')
                r[f"{code} Total"] = subj_data.get('total_score', '-')
            r['Grand Total'] = row['grand_total_score']
            r['Max Total'] = row['grand_total_max']
            r['Percentage'] = f"{row['overall_percentage']}%"
            r['Result'] = row['result']
            r['Division'] = row['division']
            rows.append(r)

        df = pd.DataFrame(rows)
        output = io.StringIO()
        df.to_csv(output, index=False)
        return io.BytesIO(output.getvalue().encode('utf-8'))

    # Excel format with professional two-tier formatting
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Section Consolidated Marks"

    # Title & Metadata
    ws.merge_cells("A1:K1")
    t_cell = ws["A1"]
    t_cell.value = "ACADEMIC ASSESSMENT MANAGEMENT SYSTEM - CONSOLIDATED SECTION GRADE SHEET"
    t_cell.font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    t_cell.fill = PatternFill(start_color="1B365D", end_color="1B365D", fill_type="solid")
    t_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 28

    meta_text = (
        f"Programme: {section.programme.name} ({section.programme.code}) | "
        f"Semester: {section.semester.name} | Section: {section.name} | "
        f"Academic Year: {section.academic_year.year_code} | "
        f"Total Students: {overall_stats['total_students']} | "
        f"Pass Rate: {overall_stats['class_pass_rate']}%"
    )
    ws.merge_cells("A2:K2")
    m_cell = ws["A2"]
    m_cell.value = meta_text
    m_cell.font = Font(name="Calibri", size=10, italic=True, color="FFFFFF")
    m_cell.fill = PatternFill(start_color="203764", end_color="203764", fill_type="solid")
    m_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 20

    # Header Row 1 (Tier 1) & Header Row 2 (Tier 2)
    row1 = 4
    row2 = 5
    thin_border = Border(
        left=Side(style='thin', color='CCCCCC'),
        right=Side(style='thin', color='CCCCCC'),
        top=Side(style='thin', color='CCCCCC'),
        bottom=Side(style='thin', color='CCCCCC')
    )
    h_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    h_fill_navy = PatternFill(start_color="1B365D", end_color="1B365D", fill_type="solid")
    h_fill_sub = PatternFill(start_color="2E5B88", end_color="2E5B88", fill_type="solid")

    # Fixed starting columns: S.No, Reg No, Name
    ws.merge_cells(start_row=row1, start_column=1, end_row=row2, end_column=1)
    ws.cell(row=row1, column=1, value="S.No")
    ws.merge_cells(start_row=row1, start_column=2, end_row=row2, end_column=2)
    ws.cell(row=row1, column=2, value="Register Number")
    ws.merge_cells(start_row=row1, start_column=3, end_row=row2, end_column=3)
    ws.cell(row=row1, column=3, value="Student Name")

    col_idx = 4
    for m in mappings:
        start_col = col_idx
        end_col = col_idx + 2
        ws.merge_cells(start_row=row1, start_column=start_col, end_row=row1, end_column=end_col)
        top_cell = ws.cell(row=row1, column=start_col, value=f"{m.subject.subject_code}: {m.subject.subject_name}")
        top_cell.font = h_font
        top_cell.fill = h_fill_navy
        top_cell.alignment = Alignment(horizontal="center", vertical="center")

        s_meta = subject_meta.get(m.id, {})
        h_ica = int(s_meta.get('ica_max', m.subject.ica_max))
        h_tee_enabled = s_meta.get('tee_enabled', True)
        h_tee = int(s_meta.get('tee_max', m.subject.tee_max))
        h_tot = int(s_meta.get('display_total_max', h_ica + h_tee))
        ws.cell(row=row2, column=start_col, value=f"ICA ({h_ica})")
        ws.cell(row=row2, column=start_col + 1, value=f"TEE ({h_tee if h_tee_enabled else '-'})")
        ws.cell(row=row2, column=end_col, value=f"Total ({h_tot})")
        col_idx += 3

    # Summary End Columns: Grand Total, Percentage, Result, Division
    end_cols = ["Grand Total", "Overall %", "Result", "Division"]
    for ec in end_cols:
        ws.merge_cells(start_row=row1, start_column=col_idx, end_row=row2, end_column=col_idx)
        c = ws.cell(row=row1, column=col_idx, value=ec)
        c.font = h_font
        c.fill = h_fill_navy
        c.alignment = Alignment(horizontal="center", vertical="center")
        col_idx += 1

    total_cols = col_idx - 1

    # Style header cells
    for r in [row1, row2]:
        ws.row_dimensions[r].height = 22
        for c in range(1, total_cols + 1):
            cell = ws.cell(row=r, column=c)
            cell.font = h_font
            cell.border = thin_border
            if not cell.fill or cell.fill.fill_type != 'solid':
                cell.fill = h_fill_sub
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # Data Rows
    current_row = 6
    for idx, s_row in enumerate(students_data, 1):
        ws.row_dimensions[current_row].height = 20
        ws.cell(row=current_row, column=1, value=idx).alignment = Alignment(horizontal="center")
        reg_c = ws.cell(row=current_row, column=2, value=s_row['student'].register_number)
        reg_c.font = Font(name="Consolas", bold=True, color="1B365D")
        reg_c.alignment = Alignment(horizontal="center")
        ws.cell(row=current_row, column=3, value=s_row['student'].student_name)

        c_pos = 4
        for m in mappings:
            subj_info = s_row['subjects'].get(m.id, {})
            ica_c = ws.cell(row=current_row, column=c_pos, value=subj_info.get('ica_disp', '-'))
            ica_c.alignment = Alignment(horizontal="center")

            tee_c = ws.cell(row=current_row, column=c_pos + 1, value=subj_info.get('tee_disp', '-'))
            tee_c.alignment = Alignment(horizontal="center")

            tot_val = subj_info.get('total_score', '-')
            tot_c = ws.cell(row=current_row, column=c_pos + 2, value=tot_val)
            tot_c.alignment = Alignment(horizontal="center")
            tot_c.font = Font(bold=True)
            if subj_info.get('is_pass') is False:
                tot_c.font = Font(bold=True, color="9C0006")
                tot_c.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")

            c_pos += 3

        # Grand Totals
        gt_c = ws.cell(row=current_row, column=c_pos, value=f"{s_row['grand_total_score']} / {s_row['grand_total_max']}")
        gt_c.font = Font(bold=True)
        gt_c.alignment = Alignment(horizontal="center")

        pct_c = ws.cell(row=current_row, column=c_pos + 1, value=f"{s_row['overall_percentage']}%")
        pct_c.font = Font(bold=True)
        pct_c.alignment = Alignment(horizontal="center")

        res_c = ws.cell(row=current_row, column=c_pos + 2, value=s_row['result'])
        res_c.font = Font(bold=True)
        res_c.alignment = Alignment(horizontal="center")
        if s_row['result'] == 'PASS':
            res_c.font = Font(bold=True, color="006100")
            res_c.fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
        elif s_row['result'] == 'FAIL':
            res_c.font = Font(bold=True, color="9C0006")
            res_c.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")

        div_c = ws.cell(row=current_row, column=c_pos + 3, value=s_row['division'])
        div_c.alignment = Alignment(horizontal="center")

        # Borders
        for c in range(1, total_cols + 1):
            ws.cell(row=current_row, column=c).border = thin_border

        current_row += 1

    # Class Average Row
    ws.row_dimensions[current_row].height = 22
    ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=3)
    avg_lbl = ws.cell(row=current_row, column=1, value="Class Average")
    avg_lbl.font = Font(bold=True, color="1B365D")
    avg_lbl.alignment = Alignment(horizontal="center", vertical="center")

    c_pos = 4
    for m in mappings:
        st = subject_stats.get(m.id, {})
        ws.cell(row=current_row, column=c_pos, value=st.get('avg_ica', '-')).alignment = Alignment(horizontal="center")
        ws.cell(row=current_row, column=c_pos + 1, value=st.get('avg_tee', '-')).alignment = Alignment(horizontal="center")
        t_c = ws.cell(row=current_row, column=c_pos + 2, value=st.get('avg_total', '-'))
        t_c.font = Font(bold=True)
        t_c.alignment = Alignment(horizontal="center")
        c_pos += 3

    ws.cell(row=current_row, column=c_pos, value="-").alignment = Alignment(horizontal="center")
    c_avg_pct = ws.cell(row=current_row, column=c_pos + 1, value=f"{overall_stats['class_average_pct']}%")
    c_avg_pct.font = Font(bold=True, color="1B365D")
    c_avg_pct.alignment = Alignment(horizontal="center")
    pass_rt = ws.cell(row=current_row, column=c_pos + 2, value=f"{overall_stats['class_pass_rate']}% Pass")
    pass_rt.font = Font(bold=True, color="006100")
    pass_rt.alignment = Alignment(horizontal="center")
    ws.cell(row=current_row, column=c_pos + 3, value="-").alignment = Alignment(horizontal="center")

    for c in range(1, total_cols + 1):
        cell = ws.cell(row=current_row, column=c)
        cell.border = thin_border
        cell.fill = PatternFill(start_color="F2F4F8", end_color="F2F4F8", fill_type="solid")

    auto_fit_columns(ws)
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output
