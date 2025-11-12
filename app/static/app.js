const state = {
  token: localStorage.getItem('token'),
  role: localStorage.getItem('role'),
  username: localStorage.getItem('username'),
  personnel: [],
  dutyTypes: [],
  equipment: [],
};

const authSection = document.getElementById('auth-section');
const appSection = document.getElementById('app');
const userInfo = document.getElementById('user-info');
const loginForm = document.getElementById('login-form');
const logoutBtn = document.getElementById('logout-btn');
const nav = document.getElementById('nav');

async function apiFetch(path, options = {}) {
  const headers = options.headers || {};
  headers['Content-Type'] = 'application/json';
  if (state.token) {
    headers['Authorization'] = `Bearer ${state.token}`;
  }
  try {
    const response = await fetch(path, { ...options, headers });
    const contentType = response.headers.get('Content-Type') || '';
    const isJson = contentType.includes('application/json');
    const payload = isJson ? await response.json() : await response.text();
    if (!response.ok) {
      throw new Error(payload.detail || payload.message || response.statusText);
    }
    return payload;
  } catch (error) {
    showToast(error.message || 'Помилка мережі');
    throw error;
  }
}

function showToast(message) {
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => {
    toast.classList.add('visible');
    setTimeout(() => {
      toast.classList.remove('visible');
      setTimeout(() => toast.remove(), 400);
    }, 2500);
  }, 50);
}

function setAuthenticated() {
  if (state.token) {
    authSection.classList.add('hidden');
    appSection.classList.remove('hidden');
    userInfo.textContent = `${state.username} (${state.role})`;
  } else {
    authSection.classList.remove('hidden');
    appSection.classList.add('hidden');
    userInfo.textContent = '';
  }
}

function showView(name) {
  document.querySelectorAll('.view').forEach((section) => {
    section.classList.add('hidden');
  });
  const target = document.getElementById(`view-${name}`);
  if (target) {
    target.classList.remove('hidden');
  }
}

async function loadBaseData() {
  const [personnel, dutyTypes, equipment] = await Promise.all([
    apiFetch('/api/personnel'),
    apiFetch('/api/duty-types'),
    apiFetch('/api/equipment'),
  ]);
  state.personnel = personnel;
  state.dutyTypes = dutyTypes;
  state.equipment = equipment;
  populateSelects();
  renderPersonnel(personnel);
}

function populateSelects() {
  const scheduleForm = document.getElementById('schedule-form');
  const planForm = document.getElementById('plan-form');
  const vacationForm = document.getElementById('vacation-form');

  const personOptions = state.personnel
    .map((p) => `<option value="${p.id}">${p.full_name} (${p.role})</option>`) 
    .join('');
  if (scheduleForm) {
    scheduleForm.person_id.innerHTML = `<option value="">--</option>${personOptions}`;
  }
  if (planForm) {
    planForm.pilot_id.innerHTML = `<option value="">--</option>${personOptions}`;
    planForm.navigator_id.innerHTML = `<option value="">--</option>${personOptions}`;
  }
  if (vacationForm) {
    vacationForm.person_id.innerHTML = `<option value="">--</option>${personOptions}`;
  }

  const dutyOptions = state.dutyTypes
    .map((d) => `<option value="${d.id}">${d.code} — ${d.name}</option>`) 
    .join('');
  if (scheduleForm) {
    scheduleForm.duty_type_id.innerHTML = `<option value="">--</option>${dutyOptions}`;
  }

  const uavOptions = state.equipment
    .filter((eq) => eq.category === 'uav')
    .map((eq) => `<option value="${eq.id}">${eq.name}</option>`)
    .join('');
  const vehicleOptions = state.equipment
    .filter((eq) => eq.category === 'vehicle')
    .map((eq) => `<option value="${eq.id}">${eq.name}</option>`)
    .join('');
  const batteryOptions = state.equipment
    .filter((eq) => eq.category === 'battery')
    .map((eq) => `<option value="${eq.id}">${eq.name}</option>`)
    .join('');

  if (planForm) {
    planForm.uav_id.innerHTML = `<option value="">--</option>${uavOptions}`;
    planForm.vehicle_id.innerHTML = `<option value="">--</option>${vehicleOptions}`;
    planForm.battery_id.innerHTML = `<option value="">--</option>${batteryOptions}`;
  }
}

function renderPersonnel(personnel) {
  const container = document.getElementById('personnel-table');
  if (!container) return;
  const rows = personnel
    .map(
      (p) => `
        <tr>
          <td>${p.full_name}</td>
          <td>${p.role}</td>
          <td>${p.callsign || ''}</td>
          <td>${p.unit}</td>
        </tr>
      `
    )
    .join('');
  container.innerHTML = `
    <table class="table">
      <thead>
        <tr><th>ПІБ</th><th>Роль</th><th>Позивний</th><th>Підрозділ</th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

async function loadDashboard() {
  const data = await apiFetch('/api/dashboard');
  renderDashboard(data);
}

function renderDashboard(data) {
  const container = document.getElementById('dashboard-content');
  if (!container) return;
  const planCards = data.plan
    .map(
      (item) => `
        <div class="card">
          <h3>${item.unit}</h3>
          <p><strong>Завдання:</strong> ${item.mission}</p>
          <p><strong>Час:</strong> ${(item.start_time || '--')} – ${(item.end_time || '--')}</p>
          <p><strong>Екіпаж:</strong> ${(item.pilot_name || '—')} / ${(item.navigator_name || '—')}</p>
        </div>
      `
    )
    .join('');
  const statusRows = data.statuses
    .map(
      (entry) => `
        <tr>
          <td>${entry.person.full_name}</td>
          <td>${entry.person.unit}</td>
          <td><span class="status-badge" style="background:${statusColor(entry.status)}">${entry.status}</span></td>
        </tr>
      `
    )
    .join('');
  container.innerHTML = `
    <div class="card-grid">${planCards || '<p>Немає завдань на сьогодні.</p>'}</div>
    <h3>Статуси персоналу (${data.date})</h3>
    <table class="table">
      <thead><tr><th>ПІБ</th><th>Підрозділ</th><th>Статус</th></tr></thead>
      <tbody>${statusRows}</tbody>
    </table>
  `;
}

function statusColor(status) {
  if (!status) return '#95a5a6';
  if (status.toLowerCase().includes('в')) return '#2ecc71';
  if (status.toLowerCase().includes('р')) return '#e67e22';
  return '#1f3c88';
}

async function loadSchedule() {
  const monthInput = document.getElementById('schedule-month');
  const month = monthInput.value || new Date().toISOString().slice(0, 7);
  if (!monthInput.value) monthInput.value = month;
  const data = await apiFetch(`/api/schedule?month=${month}`);
  renderSchedule(data.entries);
}

function renderSchedule(entries) {
  const container = document.getElementById('schedule-table');
  if (!container) return;
  if (!entries.length) {
    container.innerHTML = '<p>Даних немає.</p>';
    return;
  }
  const rows = entries
    .map(
      (item) => `
        <tr>
          <td>${item.duty_date}</td>
          <td>${item.full_name}</td>
          <td><span class="status-badge" style="background:${item.color}">${item.code}</span></td>
          <td>${item.note || ''}</td>
        </tr>
      `
    )
    .join('');
  container.innerHTML = `
    <table class="table">
      <thead><tr><th>Дата</th><th>Співробітник</th><th>Черга</th><th>Нотатки</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

async function loadPlan() {
  const dateInput = document.getElementById('plan-date');
  const date = dateInput.value || new Date().toISOString().slice(0, 10);
  if (!dateInput.value) dateInput.value = date;
  const data = await apiFetch(`/api/plan?date=${date}`);
  renderPlan(data.entries);
}

function renderPlan(entries) {
  const container = document.getElementById('plan-table');
  if (!container) return;
  if (!entries.length) {
    container.innerHTML = '<p>Даних немає.</p>';
    return;
  }
  const rows = entries
    .map(
      (item) => `
        <tr>
          <td>${item.unit}</td>
          <td>${item.mission}</td>
          <td>${item.start_time || ''} – ${item.end_time || ''}</td>
          <td>${item.pilot_name || '—'}</td>
          <td>${item.navigator_name || '—'}</td>
          <td>${item.uav_name || '—'}</td>
        </tr>
      `
    )
    .join('');
  container.innerHTML = `
    <table class="table">
      <thead><tr><th>Підрозділ</th><th>Завдання</th><th>Час</th><th>Пілот</th><th>Штурман</th><th>БПЛА</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

async function loadVacations() {
  const data = await apiFetch('/api/vacations');
  renderVacations(data);
}

function renderVacations(entries) {
  const container = document.getElementById('vacation-table');
  if (!container) return;
  if (!entries.length) {
    container.innerHTML = '<p>Даних немає.</p>';
    return;
  }
  const rows = entries
    .map(
      (item) => `
        <tr>
          <td>${item.full_name}</td>
          <td>${item.start_date}</td>
          <td>${item.end_date}</td>
          <td>${item.status}</td>
        </tr>
      `
    )
    .join('');
  container.innerHTML = `
    <table class="table">
      <thead><tr><th>Співробітник</th><th>Початок</th><th>Кінець</th><th>Статус</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

async function loadAnalytics() {
  const start = document.getElementById('analytics-start').value;
  const end = document.getElementById('analytics-end').value;
  let query = '';
  if (start && end) {
    query = `?start=${start}&end=${end}`;
  }
  const data = await apiFetch(`/api/analytics/summary${query}`);
  renderAnalytics(data);
}

function renderAnalytics(data) {
  const container = document.getElementById('analytics-content');
  if (!container) return;
    const dutyRows = data.duty_summary
      .map((item) => `<tr><td>${item.code}</td><td>${item.name}</td><td>${item.total}</td></tr>`)
      .join('');
  const workloadRows = data.workload
    .map((item) => `<tr><td>${item.full_name}</td><td>${item.total}</td></tr>`)
    .join('');
  container.innerHTML = `
      <div class="card-grid">
        <div>
          <h3>Чергування за типом</h3>
        <table class="table"><thead><tr><th>Код</th><th>Назва</th><th>К-сть</th></tr></thead><tbody>${dutyRows}</tbody></table>
      </div>
      <div>
        <h3>Навантаженість</h3>
        <table class="table"><thead><tr><th>Співробітник</th><th>К-сть чергувань</th></tr></thead><tbody>${workloadRows}</tbody></table>
      </div>
    </div>
  `;
}

function toggleFormsByRole() {
  const personnelForm = document.getElementById('personnel-form');
  const scheduleForm = document.getElementById('schedule-form');
  const planForm = document.getElementById('plan-form');
  const vacationForm = document.getElementById('vacation-form');
  const privileged = state.role === 'admin' || state.role === 'planner';
  if (personnelForm) personnelForm.classList.toggle('hidden', !privileged);
  if (scheduleForm) scheduleForm.classList.toggle('hidden', !privileged);
  if (planForm) planForm.classList.toggle('hidden', !privileged);
  if (vacationForm) vacationForm.classList.toggle('hidden', !privileged);
}

// Event bindings --------------------------------------------------

loginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const formData = new FormData(loginForm);
  try {
    const session = await apiFetch('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify(Object.fromEntries(formData.entries())),
    });
    state.token = session.token;
    state.role = session.role;
    state.username = session.username;
    localStorage.setItem('token', state.token);
    localStorage.setItem('role', state.role);
    localStorage.setItem('username', state.username);
    setAuthenticated();
    toggleFormsByRole();
    await loadBaseData();
    await loadDashboard();
    showView('dashboard');
  } catch (error) {
    console.error(error);
  }
});

logoutBtn.addEventListener('click', async () => {
  try {
    await apiFetch('/api/auth/logout', { method: 'POST' });
  } catch (error) {
    // ignore
  }
  state.token = null;
  state.role = null;
  state.username = null;
  localStorage.removeItem('token');
  localStorage.removeItem('role');
  localStorage.removeItem('username');
  setAuthenticated();
  showView('dashboard');
});

nav.querySelectorAll('button[data-view]').forEach((button) => {
  button.addEventListener('click', async () => {
    const view = button.dataset.view;
    showView(view);
    if (view === 'dashboard') await loadDashboard();
    if (view === 'personnel') renderPersonnel(state.personnel);
    if (view === 'schedule') await loadSchedule();
    if (view === 'plan') await loadPlan();
    if (view === 'vacations') await loadVacations();
    if (view === 'analytics') await loadAnalytics();
  });
});

const refreshScheduleBtn = document.getElementById('refresh-schedule');
if (refreshScheduleBtn) {
  refreshScheduleBtn.addEventListener('click', loadSchedule);
}

const refreshPlanBtn = document.getElementById('refresh-plan');
if (refreshPlanBtn) {
  refreshPlanBtn.addEventListener('click', loadPlan);
}

const refreshAnalyticsBtn = document.getElementById('refresh-analytics');
if (refreshAnalyticsBtn) {
  refreshAnalyticsBtn.addEventListener('click', loadAnalytics);
}

const personnelForm = document.getElementById('personnel-form');
if (personnelForm) {
  personnelForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const formData = new FormData(personnelForm);
    try {
      const created = await apiFetch('/api/personnel', {
        method: 'POST',
        body: JSON.stringify(Object.fromEntries(formData.entries())),
      });
      state.personnel.push(created);
      populateSelects();
      renderPersonnel(state.personnel);
      personnelForm.reset();
    } catch (error) {
      console.error(error);
    }
  });
}

const scheduleForm = document.getElementById('schedule-form');
if (scheduleForm) {
  scheduleForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const formData = new FormData(scheduleForm);
    try {
      await apiFetch('/api/schedule', {
        method: 'POST',
        body: JSON.stringify(Object.fromEntries(formData.entries())),
      });
      await loadSchedule();
      scheduleForm.reset();
    } catch (error) {
      console.error(error);
    }
  });
}

const planForm = document.getElementById('plan-form');
if (planForm) {
  planForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const formData = new FormData(planForm);
    try {
      await apiFetch('/api/plan', {
        method: 'POST',
        body: JSON.stringify(Object.fromEntries(formData.entries())),
      });
      await loadPlan();
      planForm.reset();
    } catch (error) {
      console.error(error);
    }
  });
}

const vacationForm = document.getElementById('vacation-form');
if (vacationForm) {
  vacationForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const formData = new FormData(vacationForm);
    try {
      await apiFetch('/api/vacations', {
        method: 'POST',
        body: JSON.stringify(Object.fromEntries(formData.entries())),
      });
      await loadVacations();
      vacationForm.reset();
    } catch (error) {
      console.error(error);
    }
  });
}

function init() {
  if (state.token) {
    setAuthenticated();
    toggleFormsByRole();
    loadBaseData()
      .then(() => {
        showView('dashboard');
        return loadDashboard();
      })
      .catch(() => {
        // token might be invalid
        state.token = null;
        localStorage.removeItem('token');
        setAuthenticated();
      });
  } else {
    setAuthenticated();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  init();
});
