// ── Watchlist ─────────────────────────────────────────────────────────────────

let selectedMode   = 'ongoing';
const liveScanIds    = new Set();
const liveScanTimers = {};

// Season / mode helpers
function onSeasonChange() {
  const sel = document.getElementById('seasonInput');
  const c   = document.getElementById('seasonCustom');
  c.style.display = sel.value === 'custom' ? 'block' : 'none';
  if (sel.value === 'custom') c.focus();
}

function getSelectedSeason() {
  const sel = document.getElementById('seasonInput');
  if (sel.value === 'custom') {
    const n = parseInt(document.getElementById('seasonCustom').value);
    return (!n || n < 1) ? 1 : n;
  }
  return parseInt(sel.value);
}

function setMode(m) {
  selectedMode = m;
  document.getElementById('modeOngoing').classList.toggle('active',  m === 'ongoing');
  document.getElementById('modeComplete').classList.toggle('active', m === 'complete');
}

// Status helpers
function statusColor(s) {
  if (s === 'FINISHED')         return 'var(--green)';
  if (s === 'RELEASING')        return 'var(--blue)';
  if (s === 'NOT_YET_RELEASED') return 'var(--muted)';
  return 'var(--muted)';
}
function statusLabel(s) {
  if (s === 'FINISHED')         return 'Finished';
  if (s === 'RELEASING')        return 'Airing';
  if (s === 'NOT_YET_RELEASED') return 'Not yet aired';
  return '';
}

// Data loading
async function loadWatchlist() {
  const list = await api.watchlist.list();
  renderWatchlist(list);
}

async function loadStatus() {
  try {
    const d = await api.status();
    document.getElementById('headerStats').innerHTML =
      `<span><b>${d.downloaded}</b> grabbed</span><span><b>${d.renamed}</b> renamed</span>`;
    const badge = document.getElementById('bellBadge');
    if (d.unread_notifications > 0) {
      badge.style.display = 'flex';
      badge.textContent   = d.unread_notifications;
    } else {
      badge.style.display = 'none';
    }
  } catch {}
}

function renderWatchlist(list) {
  document.getElementById('countBadge').textContent = `${list.length} series`;
  const el = document.getElementById('watchlist');
  if (!list.length) {
    el.innerHTML = `<div class="empty"><div class="kaomoji">( ´_ゝ｀)</div><p>No anime in watchlist yet.<br>Search for a title above — AniWatcher will automatically grab<br>new episodes from nyaa.si and organize them for Jellyfin.</p></div>`;
    return;
  }
  el.innerHTML = list.map(e => {
    const grabbed   = (e.episodes_grabbed || []).filter(g => g.ep !== 'batch').length;
    const total     = e.total_episodes;
    const isDone    = e.all_grabbed;
    const pct       = total ? Math.min(100, Math.round(grabbed / total * 100)) : 0;
    const cardClass = !e.active ? 'paused' : isDone ? 'done' : '';
    const last      = (e.episodes_grabbed || []).slice(-1)[0];

    const progressHtml = total ? `
      <div class="progress-row">
        <div class="progress-bar-wrap"><div class="progress-bar ${isDone ? 'done' : ''}" style="width:${pct}%"></div></div>
        <span class="progress-label">${grabbed}/${total} eps${isDone ? ' ✓' : ''}</span>
      </div>` : '';

    const airingBadge = e.airing_status
      ? `<span style="color:${statusColor(e.airing_status)}">${statusLabel(e.airing_status)}</span>`
      : '';
    const modeLabel = e.mode === 'complete'
      ? `<span style="color:var(--yellow)">⬇ Full Season</span>`
      : `<span style="color:var(--green)">⟳ Ongoing</span>`;

    const startEpHtml = e.start_episode
      ? `<span style="color:var(--yellow);cursor:pointer" title="Start episode — click to change" onclick="editStartEp(${e.id},${e.start_episode})">▶ from Ep ${e.start_episode}</span>`
      : `<span style="color:var(--muted);cursor:pointer;font-size:.72rem" title="Set start episode (skip older eps)" onclick="editStartEp(${e.id},null)">+ start ep</span>`;

    return `
    <div class="anime-card ${cardClass}" id="card-${e.id}">
      <div class="card-top">
        <div class="status-dot"></div>
        <div class="card-body">
          <div class="card-title">${escHtml(e.title)}</div>
          <div class="card-meta">
            <span>Season ${e.season}</span>
            ${airingBadge}
            ${modeLabel}
            ${last && last.ep !== 'batch' ? `<span>Last: Ep ${last.ep ?? '?'}</span>` : ''}
            ${e.search_title && e.search_title !== e.title ? `<span style="color:var(--muted)">🔍 ${escHtml(e.search_title)}</span>` : ''}
            ${startEpHtml}
            ${isDone ? `<span style="color:var(--green)">✓ All grabbed</span>` : ''}
          </div>
        </div>
        <div class="ep-pill" title="Click to override episode count" style="cursor:pointer" onclick="editEpCount(${e.id}, ${total || 'null'})">${grabbed}${total ? '/' + total : ''} eps</div>
        <div class="card-actions">
          <button class="btn-icon" title="Inspect MKV metadata" onclick="openMetaInspector(${e.id})" style="font-size:.75rem">🔍 Meta</button>
          <button class="btn-icon season" id="fs-${e.id}" title="Backfill full season" onclick="fullSeason(${e.id})">⬇ Full</button>
          <button class="btn-icon ${e.manual_pick ? 'manual-on' : ''}" title="${e.manual_pick ? 'Manual pick ON' : 'Manual pick OFF'}" onclick="toggleManualPick(${e.id})" style="font-size:.7rem;padding:0 .5rem">🎯${e.manual_pick ? 'ON' : 'OFF'}</button>
          <button class="btn-icon ${liveScanIds.has(e.id) ? 'active-scan' : ''}" id="ls-${e.id}" title="Toggle live disk scan (every 60s)" onclick="toggleLiveScan(${e.id})" style="${liveScanIds.has(e.id) ? 'color:var(--green);border-color:var(--green)' : ''}">⟳ Live</button>
          <button class="btn-icon" title="Scan disk and update episode count" onclick="scanDisk(${e.id})" style="color:var(--muted)">⟳</button>
          <button class="btn-icon" title="Reset download history (re-grab missing eps)" onclick="resetHistory(${e.id})" style="color:var(--muted)">↺</button>
          <button class="btn-icon" title="${e.active ? 'Pause' : 'Resume'}" onclick="toggleAnime(${e.id})">${e.active ? '⏸' : '▶'}</button>
          <button class="btn-icon danger" title="Remove" onclick="deleteAnime(${e.id})">✕</button>
        </div>
      </div>
      ${progressHtml}
    </div>`;
  }).join('');
}

// CRUD actions
async function addAnime() {
  const title      = document.getElementById('titleInput').value.trim();
  const season     = getSelectedSeason();
  if (!title) return;
  const startEpRaw = document.getElementById('startEpInput').value.trim();
  const startEp    = startEpRaw ? parseInt(startEpRaw) : null;

  const res = await api.watchlist.add({
    title,
    season,
    mode:          selectedMode,
    search_title:  document.getElementById('searchTitleInput').value.trim() || title,
    start_episode: startEp,
  });
  if (res.ok) {
    const entry = await res.json();
    document.getElementById('titleInput').value      = '';
    document.getElementById('searchTitleInput').value = '';
    document.getElementById('startEpInput').value    = '';
    document.getElementById('seasonInput').value     = '1';
    document.getElementById('seasonCustom').style.display = 'none';
    setMode('ongoing');
    hideSearch();
    let addMsg = `Added "${title}"${entry.total_episodes ? ' — ' + entry.total_episodes + ' eps' : ''}`;
    if (entry.search_title && entry.search_title !== title) addMsg += ` · Nyaa: "${entry.search_title}"`;
    toast(addMsg, 'success');
    loadWatchlist();
    loadStatus();
    setTimeout(() => scanDisk(entry.id), 500);
    if (selectedMode === 'complete') setTimeout(() => fullSeason(entry.id), 1500);
  } else {
    const err = await res.json();
    toast(err.error || 'Error adding anime', 'error');
  }
}

async function toggleAnime(id) {
  await api.watchlist.patch(id, {});
  loadWatchlist();
}

async function deleteAnime(id) {
  await api.watchlist.remove(id);
  loadWatchlist();
  loadStatus();
}

async function editEpCount(id, current) {
  const val = prompt('Set total episode count (leave blank to use MAL data):', current || '');
  if (val === null) return;
  const total = val.trim() === '' ? null : parseInt(val);
  if (val.trim() !== '' && isNaN(total)) { toast('Invalid number', 'error'); return; }
  await api.watchlist.patch(id, { total_episodes: total });
  toast(`Episode count set to ${total || 'auto'}`, 'success');
  loadWatchlist();
}

async function editStartEp(id, current) {
  const val = prompt('Download only episodes from this number onwards\n(leave blank to download all):', current || '');
  if (val === null) return;
  const ep = val.trim() === '' ? null : parseInt(val);
  if (val.trim() !== '' && (isNaN(ep) || ep < 1)) { toast('Invalid episode number', 'error'); return; }
  await api.watchlist.patch(id, { start_episode: ep });
  toast(ep ? `Will only grab episodes from Ep ${ep} onwards` : 'Start episode cleared — all episodes eligible', 'success');
  loadWatchlist();
}

async function scanDisk(id) {
  const data = await api.watchlist.scan(id);
  if (data.ok) {
    toast(`Scanned disk: found ${data.found} episodes (${data.new} new)`, 'success');
    loadWatchlist();
  } else {
    toast(data.error || 'Scan failed', 'error');
  }
}

async function resetHistory(id) {
  if (!confirm('Clear download history for this entry? It will re-grab any missing episodes on next poll.')) return;
  const data = await api.watchlist.reset(id);
  if (data.ok) {
    toast(`Reset "${data.title}" — removed ${data.removed} URLs. Click Full or wait for next poll.`, 'success');
    loadWatchlist();
  } else {
    toast(data.error || 'Reset failed', 'error');
  }
}

async function manualPoll() {
  const btn = document.getElementById('pollBtn');
  btn.classList.add('active');
  btn.textContent = '⟳ Polling…';
  await api.poll();
  toast('Poll triggered', 'success');
  setTimeout(() => {
    btn.classList.remove('active');
    btn.textContent = '⟳ Poll Now';
    loadWatchlist();
    loadStatus();
  }, 4000);
}

// Live scan
function toggleLiveScan(id) {
  if (liveScanIds.has(id)) {
    liveScanIds.delete(id);
    clearInterval(liveScanTimers[id]);
    delete liveScanTimers[id];
    toast('Live scan stopped', 'success');
  } else {
    liveScanIds.add(id);
    scanDisk(id);
    liveScanTimers[id] = setInterval(() => scanDisk(id), 60000);
    toast('Live scan enabled — scanning every 60s', 'success');
  }
  loadWatchlist();
}
