import io
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import pandas as pd
from app.models import Student, Assessment, Mark, FacultySubjectMapping

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


def parse_marks_upload(file_storage, mapping_id):
    """
    Parse uploaded Excel / CSV file for marks entry.
    Validates students and max marks constraints.
    Returns: {
        'success': bool,
        'records': list of dicts: {'student_id': id, 'reg_no': str, 'name': str, 'marks': {ass_id: {'score': float, 'status': str}}},
        'errors': list of error strings,
        'warnings': list of warning strings
    }
    """
    mapping = FacultySubjectMapping.query.get_or_404(mapping_id)
    students = Student.query.filter_by(section_id=mapping.section_id).all()
    student_by_reg = {s.register_number.strip().upper(): s for s in students}

    assessments = Assessment.query.filter_by(mapping_id=mapping.id, is_active=True).all()
    ass_by_name = {a.assessment_name.strip().upper(): a for a in assessments}

    filename = file_storage.filename.lower()
    errors = []
    warnings = []
    records = []

    try:
        if filename.endswith('.csv'):
            df = pd.read_csv(file_storage)
        else:
            # Excel might have metadata in top rows. Let's find header row
            wb = openpyxl.load_workbook(file_storage, data_only=True)
            ws = wb.active
            
            # Find row containing "Register Number"
            header_row_idx = None
            for r in range(1, 20):
                row_vals = [str(ws.cell(row=r, column=c).value or '').strip().upper() for c in range(1, 25)]
                if any('REGISTER NUMBER' in v or 'REG. NO' in v or 'REG NO' in v for v in row_vals):
                    header_row_idx = r
                    break
            
            if not header_row_idx:
                return {'success': False, 'errors': ["Could not locate 'Register Number' column header in the sheet."]}
            
            # Read into dataframe starting from header row
            file_storage.seek(0)
            df = pd.read_excel(file_storage, skiprows=header_row_idx - 1)
    except Exception as e:
        return {'success': False, 'errors': [f"Failed to read file: {str(e)}"]}

    # Clean DataFrame columns
    df.columns = [str(c).strip() for c in df.columns]

    # Find Register Number column
    reg_col = None
    for c in df.columns:
        cup = c.upper()
        if 'REGISTER NUMBER' in cup or 'REG. NO' in cup or 'REG NO' in cup or cup == 'REG_NO':
            reg_col = c
            break

    if not reg_col:
        return {'success': False, 'errors': ["Column 'Register Number' is missing."]}

    # Map remaining columns to assessments
    col_to_assessment = {}
    for c in df.columns:
        if c == reg_col or 'NAME' in c.upper() or 'S.NO' in c.upper() or 'SERIAL' in c.upper():
            continue
        # Assessment header could be "Test 1\n(Max: 20)" or "Test 1"
        clean_name = c.split('\n')[0].split('(')[0].strip().upper()
        matched_ass = ass_by_name.get(clean_name)
        if matched_ass:
            col_to_assessment[c] = matched_ass

    if not col_to_assessment:
        return {
            'success': False,
            'errors': [f"No matching assessment columns found in the sheet. Expected one of: {', '.join(ass_by_name.keys())}"]
        }

    # Iterate rows and validate
    for idx, row in df.iterrows():
        raw_reg = row.get(reg_col)
        if pd.isna(raw_reg) or str(raw_reg).strip() == '':
            continue
        
        reg_no = str(raw_reg).strip().upper()
        student = student_by_reg.get(reg_no)
        if not student:
            errors.append(f"Row {idx + 2}: Register Number '{reg_no}' is not enrolled in this section.")
            continue

        stu_marks = {}
        for col, ass in col_to_assessment.items():
            val = row.get(col)
            if pd.isna(val) or str(val).strip() == '' or str(val).strip() == '-':
                # Missing or blank marks
                continue
            
            sval = str(val).strip().upper()
            if sval in ['AB', 'ABSENT']:
                stu_marks[ass.id] = {'score': None, 'status': 'Absent'}
            elif sval in ['EX', 'EXEMPT', 'EXEMPTED']:
                stu_marks[ass.id] = {'score': None, 'status': 'Exempted'}
            else:
                try:
                    num_val = float(val)
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
        return {'success': False, 'errors': errors, 'records': []}

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
