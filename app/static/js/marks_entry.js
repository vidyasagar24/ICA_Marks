document.addEventListener('DOMContentLoaded', function () {
  const table = document.getElementById('marksEntryTable');
  if (!table) return;

  const mappingId = table.dataset.mappingId;
  const isLocked = table.dataset.isLocked === 'true';
  const inputs = table.querySelectorAll('.marks-input');

  function updateRowCalculations(row) {
    const studentInputs = row.querySelectorAll('.marks-input');
    let totalScore = 0.0;
    let totalMax = 0.0;
    let missingCount = 0;

    studentInputs.forEach(input => {
      const maxMarks = parseFloat(input.dataset.maxMarks) || 0;
      const rawVal = input.value.trim().toUpperCase();

      if (rawVal === '' || rawVal === '-') {
        missingCount++;
        totalMax += maxMarks;
      } else if (rawVal === 'AB') {
        totalMax += maxMarks;
      } else if (rawVal === 'EX') {
        // Exempted does not count against total max
      } else {
        const val = parseFloat(rawVal);
        if (!isNaN(val)) {
          totalScore += val;
          totalMax += maxMarks;
        }
      }
    });

    const totalCell = row.querySelector('.row-total-score');
    const pctCell = row.querySelector('.row-percentage');

    if (totalCell) {
      totalCell.textContent = totalScore.toFixed(1).replace(/\.0$/, '');
    }

    if (pctCell) {
      if (totalMax > 0) {
        const pct = (totalScore / totalMax) * 100;
        pctCell.textContent = pct.toFixed(1) + '%';
        pctCell.className = 'row-percentage fw-bold ' + (pct >= 50 ? 'text-success' : (pct >= 40 ? 'text-warning' : 'text-danger'));
      } else {
        pctCell.textContent = '-';
        pctCell.className = 'row-percentage text-muted';
      }
    }
  }

  function validateInput(input) {
    const maxMarks = parseFloat(input.dataset.maxMarks) || 100;
    const rawVal = input.value.trim().toUpperCase();

    if (rawVal === '' || rawVal === '-') {
      input.classList.remove('is-invalid-mark', 'is-saved-mark');
      return true;
    }

    if (rawVal === 'AB' || rawVal === 'EX') {
      input.value = rawVal;
      input.classList.remove('is-invalid-mark');
      input.classList.add('is-saved-mark');
      return true;
    }

    const numVal = parseFloat(rawVal);
    if (isNaN(numVal) || numVal < 0 || numVal > maxMarks) {
      input.classList.add('is-invalid-mark');
      input.classList.remove('is-saved-mark');
      return false;
    }

    input.value = numVal;
    input.classList.remove('is-invalid-mark');
    input.classList.add('is-saved-mark');
    return true;
  }

  // Recalculate on input
  inputs.forEach(input => {
    if (isLocked) {
      input.disabled = true;
      return;
    }

    input.addEventListener('input', function () {
      const row = this.closest('tr');
      validateInput(this);
      updateRowCalculations(row);
    });

    input.addEventListener('blur', function () {
      const row = this.closest('tr');
      const isValid = validateInput(this);
      updateRowCalculations(row);

      // Optional AJAX Auto-save if valid
      if (isValid && mappingId) {
        const studentId = this.dataset.studentId;
        const assessmentId = this.dataset.assessmentId;
        const rawVal = this.value.trim().toUpperCase();

        fetch('/api/marks/quick-save', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            mapping_id: mappingId,
            student_id: studentId,
            assessment_id: assessmentId,
            value: rawVal
          })
        })
        .then(res => res.json())
        .then(data => {
          if (data.success) {
            input.classList.add('is-saved-mark');
          }
        })
        .catch(err => console.log('Auto-save notice:', err));
      }
    });

    // Keyboard navigation (Arrow keys)
    input.addEventListener('keydown', function (e) {
      const currRow = this.closest('tr');
      const currColIndex = Array.from(currRow.querySelectorAll('.marks-input')).indexOf(this);

      if (e.key === 'ArrowDown') {
        const nextRow = currRow.nextElementSibling;
        if (nextRow) {
          const target = nextRow.querySelectorAll('.marks-input')[currColIndex];
          if (target) { target.focus(); target.select(); e.preventDefault(); }
        }
      } else if (e.key === 'ArrowUp') {
        const prevRow = currRow.previousElementSibling;
        if (prevRow) {
          const target = prevRow.querySelectorAll('.marks-input')[currColIndex];
          if (target) { target.focus(); target.select(); e.preventDefault(); }
        }
      }
    });
  });

  // Initial calculation across all rows
  table.querySelectorAll('tbody tr').forEach(row => {
    updateRowCalculations(row);
  });
});
