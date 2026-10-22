// ── Downloads tab ─────────────────────────────────────────────────────────────

let allDownloads = [];

function enrichTitles() {
  const btn      = document.getElementById('enrichBtn');
  const progress = document.getElementById('enrichProgress');
  const bar      = document.getElementById('enrichBar');
  const label    = document.getElementById('enrichLabel');
  const pct      = document.getElementById('enrichPct');
  const current  = document.getElementById('enrichCurrent');

  btn.disabled    = true;
  btn.textContent = '⟳ Fetching…';
  progress.classList.add('active');

  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws    = new WebSocket(`${proto}://${location.host}/ws/enrich`);

  ws.onmessage = e => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'start') {
      label.textContent = `Fetching ${msg.total} titles…`;
    } else if (msg.type === 'progress') {
      const p = Math.round(msg.current / msg.total * 100);
      bar.style.width   = p + '%';
      pct.textContent   = p + '%';
      label.textContent = `${msg.current} / ${msg.total}`;
      current.textContent = msg.title;
    } else if (msg.type === 'done') {
      bar.style.width   = '100%';
      pct.textContent   = '100%';
      label.textContent = `Done — updated ${msg.updated} titles`;
      current.textContent = '';
      btn.disabled    = false;
      btn.textContent = '⟳ Fetch titles';
      toast(`Updated ${msg.updated} titles`, 'success');
      loadDownloads();
      setTimeout(() => progress.classList.remove('active'), 3000);
    }
  };

  ws.onerror = () => {
    toast('WebSocket error', 'error');
    btn.disabled    = false;
    btn.textContent = '⟳ Fetch titles';
    progress.classList.remove('active');
  };
}

async function loadDownloads() {
  allDownloads = await api.downloaded.list();
  filterDownloads();
}

function filterDownloads() {
  const q        = (document.getElementById('dlSearch').value || '').toLowerCase();
  const filtered = allDownloads.filter(d =>
    !q || (d.title || '').toLowerCase().includes(q) || (d.url || '').toLowerCase().includes(q)
  );
  const el = document.getElementById('dlList');
  document.getElementById('dlCount').textContent   = `${filtered.length} / ${allDownloads.length} entries`;
  document.getElementById('selectAll').checked = false;

  if (!filtered.length) {
    el.innerHTML = '<div style="padding:2rem;text-align:center;color:var(--muted);font-size:.85rem">No entries</div>';
    return;
  }

  el.innerHTML = filtered.map(d => {
    const title = d.title || d.url || '';
    const url   = d.url   || d;
    const date  = d.date  ? new Date(d.date).toLocaleDateString() : '';
    return `
    <div style="display:flex;align-items:center;gap:.75rem;padding:.6rem 1rem;border-bottom:1px solid var(--border);font-size:.8rem">
      <input type="checkbox" class="dl-check" data-url="${escHtml(url)}"/>
      <div style="flex:1;min-width:0">
        <div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text)" title="${escHtml(url)}">${escHtml(title)}</div>
        ${date ? `<div style="font-size:.72rem;color:var(--muted)">${date}</div>` : ''}
      </div>
      <button onclick="deleteSingle('${escHtml(url)}')" style="background:none;border:none;color:var(--accent);cursor:pointer;font-size:.9rem;flex-shrink:0">✕</button>
    </div>`;
  }).join('');
}

function toggleSelectAll() {
  const checked = document.getElementById('selectAll').checked;
  document.querySelectorAll('.dl-check').forEach(cb => cb.checked = checked);
}

async function deleteSingle(url) {
  await api.downloaded.delete([url]);
  allDownloads = allDownloads.filter(d => (d.url || d) !== url);
  filterDownloads();
  toast('Removed 1 entry', 'success');
}

async function deleteSelected() {
  const selected = [...document.querySelectorAll('.dl-check:checked')].map(cb => cb.dataset.url);
  if (!selected.length) { toast('Nothing selected', 'warn'); return; }
  if (!confirm(`Remove ${selected.length} entries from download history?`)) return;
  const res = await api.downloaded.delete(selected);
  toast(`Removed ${res.removed} entries`, 'success');
  await loadDownloads();
}
