const PROGRESS_API_URL = `${URL_PREFIX}/api/progress`;
const LEVELS = ['N5', 'N4', 'N3', 'N2', 'N1', 'N0'];

async function loadProgress() {
  const tbody = document.getElementById('progress-tbody');
  const resp = await AUTH.request(PROGRESS_API_URL);
  if (!resp || !resp.ok) {
    tbody.innerHTML = '<tr><td colspan="3">Failed to load progress.</td></tr>';
    return;
  }

  const data = await resp.json();
  const rows = [];

  for (const level of LEVELS) {
    if (level in data) {
      rows.push(`
        <tr>
          <td>${level}</td>
          <td>${data[level].silver_pct}%</td>
          <td>${data[level].gold_pct}%</td>
        </tr>`);
    }
  }

  if (data.total) {
    rows.push(`
      <tr class="progress-total">
        <td><strong>Total</strong></td>
        <td><strong>${data.total.silver_pct}%</strong></td>
        <td><strong>${data.total.gold_pct}%</strong></td>
      </tr>`);
  }

  tbody.innerHTML = rows.length ? rows.join('') : '<tr><td colspan="3">No progress yet.</td></tr>';
}

document.addEventListener('DOMContentLoaded', loadProgress);
