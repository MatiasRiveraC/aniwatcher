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

const DL_PAGE_SIZE = 50;
let dlPage = 1;

async function loadDownloads() {
  allDownloads = await api.downloaded.list();
  renderDownloads();
}

// Search box: a new filter starts again at page 1
function filterDownloads() {
  dlPage = 1;
  renderDownloads();
}

function dlGoToPage(page) {
  dlPage = page;
  renderDownloads();
  document.getElementById('dlList').scrollTop = 0;
}

// Day heading in the browser's own time zone; undated entries (older history and
// "already on disk" markers) have no day
function dlDayLabel(d) {
  return d.date
    ? new Date(d.date).toLocaleDateString(undefined, { weekday: 'long', year: 'numeric', month: 'short', day: 'numeric' })
    : 'No date';
}

function renderDownloads() {
  const q        = (document.getElementById('dlSearch').value || '').toLowerCase();
  // Newest first. The list is stored oldest first, so reversing before the (stable)
  // sort keeps undated entries newest first too, after all dated ones.
  const filtered = [...allDownloads].reverse()
    .filter(d => !q || (d.title || '').toLowerCase().includes(q) || (d.url || '').toLowerCase().includes(q))
    .sort((a, b) => (Date.parse(b.date) || 0) - (Date.parse(a.date) || 0));
  const el    = document.getElementById('dlList');
  const pager = document.getElementById('dlPager');
  document.getElementById('dlCount').textContent   = `${filtered.length} / ${allDownloads.length} entries`;
  document.getElementById('selectAll').checked = false;

  if (!filtered.length) {
    el.innerHTML = '<div style="padding:2rem;text-align:center;color:var(--muted);font-size:.85rem">No entries</div>';
    pager.innerHTML = '';
    return;
  }

  const pages = Math.ceil(filtered.length / DL_PAGE_SIZE);
  dlPage      = Math.min(Math.max(dlPage, 1), pages);
  const shown = filtered.slice((dlPage - 1) * DL_PAGE_SIZE, dlPage * DL_PAGE_SIZE);

  // Per-day totals over the whole filtered list, so a day split across pages shows its full count
  const perDay = {};
  filtered.forEach(d => { const k = dlDayLabel(d); perDay[k] = (perDay[k] || 0) + 1; });

  let lastDay = null;
  el.innerHTML = shown.map(d => {
    const title = d.title || d.url || '';
    const url   = d.url   || d;
    const time  = d.date  ? new Date(d.date).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
    const day   = dlDayLabel(d);
    const head  = day === lastDay ? '' : `
    <div style="position:sticky;top:0;z-index:1;display:flex;justify-content:space-between;padding:.45rem 1rem;background:var(--card);border-bottom:1px solid var(--border);font-size:.75rem;font-weight:600;color:var(--muted);letter-spacing:.05em;text-transform:uppercase">
      <span>${escHtml(day)}</span><span>${perDay[day]} torrent${perDay[day] === 1 ? '' : 's'}</span>
    </div>`;
    lastDay = day;
    return `${head}
    <div style="display:flex;align-items:center;gap:.75rem;padding:.6rem 1rem;border-bottom:1px solid var(--border);font-size:.8rem">
      <input type="checkbox" class="dl-check" data-url="${escHtml(url)}"/>
      <div style="flex:1;min-width:0">
        <div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text)" title="${escHtml(url)}">${escHtml(title)}</div>
        ${time ? `<div style="font-size:.72rem;color:var(--muted)">${time}</div>` : ''}
      </div>
      <button onclick="deleteSingle('${escHtml(url)}')" style="background:none;border:none;color:var(--accent);cursor:pointer;font-size:.9rem;flex-shrink:0">✕</button>
    </div>`;
  }).join('');

  pager.innerHTML = pages === 1 ? '' : `
    <button class="btn-icon" onclick="dlGoToPage(${dlPage - 1})" ${dlPage === 1 ? 'disabled' : ''}>‹ Newer</button>
    <span style="font-size:.8rem;color:var(--muted)">Page ${dlPage} / ${pages}</span>
    <button class="btn-icon" onclick="dlGoToPage(${dlPage + 1})" ${dlPage === pages ? 'disabled' : ''}>Older ›</button>`;
}

function toggleSelectAll() {
  const checked = document.getElementById('selectAll').checked;
  document.querySelectorAll('.dl-check').forEach(cb => cb.checked = checked);
}

async function deleteSingle(url) {
  await api.downloaded.delete([url]);
  allDownloads = allDownloads.filter(d => (d.url || d) !== url);
  renderDownloads();
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
