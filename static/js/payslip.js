/* payslip.js — live preview + download logic */

const fmt = (n) => '₹' + Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// ── PF toggle ──────────────────────────────────────────────────────────────
document.querySelectorAll('input[name="pf_mode"]').forEach(radio => {
  radio.addEventListener('change', () => {
    const manual = document.getElementById('pf_manual');
    manual.style.display = radio.value === 'manual' ? 'block' : 'none';
    if (radio.value === 'auto') {
      manual.value = '';
    }
    debouncedPreview();
  });
});

// ── Live preview debounce ──────────────────────────────────────────────────
let previewTimer = null;
function debouncedPreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(updatePreview, 300);
}

// Watch all inputs
document.querySelectorAll('input, select').forEach(el => {
  el.addEventListener('input', debouncedPreview);
  el.addEventListener('change', debouncedPreview);
});

// ── Text preview helpers ───────────────────────────────────────────────────
function textVal(id) {
  return (document.getElementById(id)?.value || '').trim();
}
function numVal(id) {
  const v = parseFloat(document.getElementById(id)?.value);
  return isNaN(v) || v < 0 ? 0 : v;
}
function selectVal(id) {
  const el = document.getElementById(id);
  return el ? el.options[el.selectedIndex].value : '';
}

// ── Update text preview fields ─────────────────────────────────────────────
function updateTextPreview() {
  const company = textVal('company_name') || 'Company Name';
  const month   = selectVal('month');
  const year    = selectVal('year');
  const empName = textVal('emp_name') || 'Employee Name';
  const desig   = textVal('designation');
  const dept    = textVal('department');
  const empId   = textVal('emp_id');
  const otherEarnLabel = textVal('other_earn_label') || 'Other Allowance';
  const otherDedLabel  = textVal('other_ded_label')  || 'Other Deduction';
  const otherEarn = numVal('other_earn');
  const otherDed  = numVal('other_ded');
  const pt  = numVal('pt');
  const tds = numVal('tds');

  document.getElementById('prev-company').textContent = company;
  document.getElementById('prev-period').textContent  = month && year ? `${month} ${year}` : 'Pay Period';
  document.getElementById('prev-name').textContent    = empName;

  let meta = [];
  if (desig) meta.push(desig);
  if (dept)  meta.push(dept);
  if (empId) meta.push(`ID: ${empId}`);
  document.getElementById('prev-meta').textContent = meta.join(' · ');

  document.getElementById('pv-basic').textContent   = fmt(numVal('basic'));
  document.getElementById('pv-hra').textContent     = fmt(numVal('hra'));
  document.getElementById('pv-special').textContent = fmt(numVal('special'));

  // Other earn row
  const otherEarnRow = document.getElementById('pv-other-earn-row');
  otherEarnRow.style.display = otherEarn > 0 ? '' : 'none';
  document.getElementById('pv-other-earn-label').textContent = otherEarnLabel;
  document.getElementById('pv-other-earn').textContent = fmt(otherEarn);

  // PT row
  document.getElementById('pv-pt-row').style.display = pt > 0 ? '' : 'none';
  document.getElementById('pv-pt').textContent = fmt(pt);

  // TDS row
  document.getElementById('pv-tds-row').style.display = tds > 0 ? '' : 'none';
  document.getElementById('pv-tds').textContent = fmt(tds);

  // Other ded row
  const otherDedRow = document.getElementById('pv-other-ded-row');
  otherDedRow.style.display = otherDed > 0 ? '' : 'none';
  document.getElementById('pv-other-ded-label').textContent = otherDedLabel;
  document.getElementById('pv-other-ded').textContent = fmt(otherDed);
}

// ── Fetch computed totals from server ─────────────────────────────────────
async function updatePreview() {
  updateTextPreview();

  const basic      = numVal('basic');
  const hra        = numVal('hra');
  const special    = numVal('special');
  const other_earn = numVal('other_earn');
  const pf_mode    = document.querySelector('input[name="pf_mode"]:checked')?.value || 'auto';
  const pf_manual  = numVal('pf_manual');
  const pt         = numVal('pt');
  const tds        = numVal('tds');
  const other_ded  = numVal('other_ded');

  // Show preview panel
  if (basic > 0 || hra > 0 || special > 0) {
    document.getElementById('preview-placeholder').style.display = 'none';
    document.getElementById('preview-content').style.display = 'block';
  }

  try {
    const res = await fetch('/payslip-generator/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ basic, hra, special, other_earn, pf_mode, pf_manual, pt, tds, other_ded })
    });

    const data = await res.json();

    if (data.error) {
      document.getElementById('pv-gross').textContent    = '—';
      document.getElementById('pv-pf').textContent       = '—';
      document.getElementById('pv-total-ded').textContent = '—';
      document.getElementById('pv-net-pay').textContent  = '—';
      return;
    }

    document.getElementById('pv-gross').textContent     = fmt(data.gross);
    document.getElementById('pv-pf').textContent        = fmt(data.pf);
    document.getElementById('pv-total-ded').textContent = fmt(data.total_ded);
    document.getElementById('pv-net-pay').textContent   = fmt(data.net_pay);

  } catch (e) {
    // Silent fail on preview — don't block user
  }
}

// ── Download PDF ───────────────────────────────────────────────────────────
async function downloadPDF() {
  clearErrors();

  const btn = document.getElementById('download-btn');
  btn.classList.add('loading');
  btn.disabled = true;

  const formData = new FormData();
  const fields = [
    'emp_name','emp_id','designation','department','pan',
    'company_name','company_addr','month','year',
    'basic','hra','special','other_earn','other_earn_label',
    'pf_manual','pt','tds','other_ded','other_ded_label'
  ];
  fields.forEach(f => {
    const el = document.getElementById(f) || document.querySelector(`[name="${f}"]`);
    if (el) formData.append(f, el.value);
  });

  // pf_mode radio
  const pfMode = document.querySelector('input[name="pf_mode"]:checked')?.value || 'auto';
  formData.append('pf_mode', pfMode);

  try {
    const res = await fetch('/payslip-generator/download', {
      method: 'POST',
      body: formData
    });

    if (res.ok) {
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      const empName = (document.getElementById('emp_name')?.value || 'payslip').trim().replace(/\s+/g, '_');
      const month   = selectVal('month');
      const year    = selectVal('year');
      a.href     = url;
      a.download = `payslip_${empName}_${month}_${year}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } else {
      const data = await res.json();
      showErrors(data.errors || ['Something went wrong. Please try again.']);
    }
  } catch (e) {
    showErrors(['Network error. Please check your connection and try again.']);
  } finally {
    btn.classList.remove('loading');
    btn.disabled = false;
  }
}

// ── Error display ──────────────────────────────────────────────────────────
function showErrors(errors) {
  const container = document.getElementById('error-container');
  container.innerHTML = `
    <div class="alert alert-error" role="alert">
      <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24" style="flex-shrink:0;margin-top:2px;">
        <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
      </svg>
      <div>
        <strong>Please fix the following:</strong>
        <ul>${errors.map(e => `<li>${e}</li>`).join('')}</ul>
      </div>
    </div>
  `;
  container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function clearErrors() {
  document.getElementById('error-container').innerHTML = '';
  document.querySelectorAll('.error-field').forEach(el => el.classList.remove('error-field'));
}

// ── Reset ──────────────────────────────────────────────────────────────────
function resetForm() {
  document.querySelectorAll('input[type="text"], input[type="number"]').forEach(el => el.value = '');
  document.getElementById('month').selectedIndex = 0;
  const yearSelect = document.getElementById('year');
  for (let i = 0; i < yearSelect.options.length; i++) {
    if (yearSelect.options[i].value === '2025') { yearSelect.selectedIndex = i; break; }
  }
  document.querySelector('input[name="pf_mode"][value="auto"]').checked = true;
  document.getElementById('pf_manual').style.display = 'none';
  clearErrors();
  document.getElementById('preview-placeholder').style.display = 'block';
  document.getElementById('preview-content').style.display = 'none';
}

// ── PAN uppercase on type ─────────────────────────────────────────────────
document.getElementById('pan').addEventListener('input', function() {
  this.value = this.value.toUpperCase();
});

// Init
updatePreview();
