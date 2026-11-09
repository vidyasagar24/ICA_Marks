document.addEventListener('DOMContentLoaded', function () {
  // Toggle mobile sidebar
  const sidebarToggle = document.getElementById('sidebarToggle');
  const sidebar = document.getElementById('sidebar');
  if (sidebarToggle && sidebar) {
    sidebarToggle.addEventListener('click', function () {
      sidebar.classList.toggle('show-sidebar');
    });
  }

  // Auto-dismiss alerts after 5 seconds
  const alerts = document.querySelectorAll('.alert-dismissible');
  alerts.forEach(function (alert) {
    setTimeout(function () {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
      if (bsAlert) bsAlert.close();
    }, 5000);
  });

  // Dynamic Cascade Dropdowns for Section & Subject
  const progSelect = document.getElementById('cascade_programme');
  const yearSelect = document.getElementById('cascade_year');
  const semSelect = document.getElementById('cascade_sem');
  const secSelect = document.getElementById('cascade_section');
  const subjSelect = document.getElementById('cascade_subject');

  function updateSections() {
    if (!secSelect) return;
    const pId = progSelect ? progSelect.value : '';
    const yId = yearSelect ? yearSelect.value : '';
    const sId = semSelect ? semSelect.value : '';

    if (!pId || !sId) return;

    fetch(`/api/cascade/sections?programme_id=${pId}&academic_year_id=${yId}&semester_id=${sId}`)
      .then(res => res.json())
      .then(data => {
        secSelect.innerHTML = '<option value="">-- Select Section --</option>';
        data.forEach(item => {
          const opt = document.createElement('option');
          opt.value = item.id;
          opt.textContent = `Section ${item.name}`;
          secSelect.appendChild(opt);
        });
      })
      .catch(err => console.error('Error fetching sections:', err));
  }

  function updateSubjects() {
    if (!subjSelect) return;
    const pId = progSelect ? progSelect.value : '';
    const sId = semSelect ? semSelect.value : '';

    if (!pId || !sId) return;

    fetch(`/api/cascade/subjects?programme_id=${pId}&semester_id=${sId}`)
      .then(res => res.json())
      .then(data => {
        subjSelect.innerHTML = '<option value="">-- Select Subject --</option>';
        data.forEach(item => {
          const opt = document.createElement('option');
          opt.value = item.id;
          opt.textContent = item.display;
          subjSelect.appendChild(opt);
        });
      })
      .catch(err => console.error('Error fetching subjects:', err));
  }

  if (progSelect) progSelect.addEventListener('change', () => { updateSections(); updateSubjects(); });
  if (yearSelect) yearSelect.addEventListener('change', updateSections);
  if (semSelect) semSelect.addEventListener('change', () => { updateSections(); updateSubjects(); });
});
