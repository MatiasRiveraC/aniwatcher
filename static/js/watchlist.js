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

// Folder watcher (moves completed downloads into the library), as of the last status fetch
let watcherState = null;
let watcherRefetch = null;

async function loadStatus() {
  try {
    const d = await api.status();
    document.getElementById('headerStats').innerHTML =
      `<span><b>${d.downloaded}</b> grabbed</span><span><b>${d.renamed}</b> renamed</span>` +
      `<span id="watcherNext"></span>`;
    // offset = server clock - this browser's clock, so the countdown matches the server
    watcherState = { ...d.watcher, offset: d.watcher.now - Date.now() / 1000 };
    renderWatcher();
    const badge = document.getElementById('bellBadge');
    if (d.unread_notifications > 0) {
      badge.style.display = 'flex';
      badge.textContent   = d.unread_notifications;
    } else {
      badge.style.display = 'none';
    }
  } catch {}
}

// Called every second: counts down to the watcher's next pass
function renderWatcher() {
  const el = document.getElementById('watcherNext');
  if (!el || !watcherState) return;
  const w = watcherState;
  el.title = 'Moves finished downloads into the library' +
    (w.last_run ? ` · last run ${new Date((w.last_run - w.offset) * 1000).toLocaleTimeString()}` : '');
  const left = w.next_run ? Math.round(w.next_run - (Date.now() / 1000 + w.offset)) : 0;
  if (w.running || left <= 0) {
    el.innerHTML = '<b>moving files…</b>';
    // Fetch again shortly to pick up the next run time once the pass is done
    if (!watcherRefetch) watcherRefetch = setTimeout(() => { watcherRefetch = null; loadStatus(); }, 2000);
    return;
  }
  const m = Math.floor(left / 60), s = String(left % 60).padStart(2, '0');
  el.innerHTML = `next move in <b>${m}:${s}</b>`;
}

let watchlistById = {};

function renderWatchlist(list) {
  watchlistById = Object.fromEntries(list.map(e => [e.id, e]));
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

    const searches   = searchTitlesOf(e);
    const searchHtml = searches.length > 1 || searches[0] !== e.title
      ? `<span style="color:var(--muted);cursor:pointer" title="Nyaa searches, tried in order:\n${escHtml(searches.join('\n'))}\n\nClick to edit" onclick="openSearchEditor(${e.id})">🔍 ${escHtml(searches[0])}${searches.length > 1 ? ` <b>+${searches.length - 1}</b>` : ''}</span>`
      : '';

    const menuOpen = openCardMenuId === e.id;

    return `
    <div class="anime-card ${cardClass} ${menuOpen ? 'menu-open' : ''}" id="card-${e.id}">
      <div class="card-top">
        <div class="status-dot"></div>
        <div class="card-title" title="${escHtml(e.title)}">${escHtml(e.title)}</div>
        <div class="ep-pill" title="Click to override episode count" style="cursor:pointer" onclick="editEpCount(${e.id}, ${total || 'null'})">${grabbed}${total ? '/' + total : ''} eps</div>
      </div>
      <div class="card-meta">
        <span>Season ${e.season}</span>
        ${airingBadge}
        ${modeLabel}
        ${last && last.ep !== 'batch' ? `<span>Last: Ep ${last.ep ?? '?'}</span>` : ''}
        ${searchHtml}
        ${startEpHtml}
        ${isDone ? `<span style="color:var(--green)">✓ All grabbed</span>` : ''}
      </div>
      ${progressHtml}
      <div class="card-actions">
        <button class="btn-icon" title="${e.active ? 'Pause' : 'Resume'}" onclick="toggleAnime(${e.id})">${e.active ? '⏸' : '▶'}</button>
        <button class="btn-icon ${liveScanIds.has(e.id) ? 'active-scan' : ''}" id="ls-${e.id}" title="Toggle live disk scan (every 60s)" onclick="toggleLiveScan(${e.id})" style="${liveScanIds.has(e.id) ? 'color:var(--green);border-color:var(--green)' : ''}">⟳ Live</button>
        <button class="btn-icon ${e.manual_pick ? 'manual-on' : ''}" title="${e.manual_pick ? 'Manual pick ON' : 'Manual pick OFF'}" onclick="toggleManualPick(${e.id})" style="font-size:.7rem;padding:0 .5rem">🎯${e.manual_pick ? 'ON' : 'OFF'}</button>
        <div class="card-menu ${menuOpen ? 'open' : ''}">
          <button class="btn-icon" title="More actions" aria-haspopup="menu" aria-expanded="${menuOpen}" onclick="toggleCardMenu(event, ${e.id})">⋯ More ▾</button>
          <div class="card-menu-list" role="menu">
            <button role="menuitem" title="See what a poll would find and grab right now (grabs nothing)" onclick="closeCardMenu();openPollPreview(${e.id})">👁 Test poll</button>
            <button role="menuitem" title="The nyaa searches a poll tries, in order" onclick="closeCardMenu();openSearchEditor(${e.id})">🔍 Nyaa searches…</button>
            <button role="menuitem" onclick="closeCardMenu();openMetaInspector(${e.id})">🔍 Inspect MKV metadata</button>
            <button role="menuitem" id="fs-${e.id}" onclick="closeCardMenu();fullSeason(${e.id})">⬇ Backfill full season</button>
            <button role="menuitem" onclick="closeCardMenu();scanDisk(${e.id})">⟳ Scan disk</button>
            <button role="menuitem" onclick="closeCardMenu();resetHistory(${e.id})">↺ Reset download history</button>
          </div>
        </div>
        <button class="btn-icon danger push-right" title="Remove" onclick="deleteAnime(${e.id})">✕</button>
      </div>
    </div>`;
  }).join('');
}

// "More" dropdown on a card. Its id is kept so the 30s auto-refresh doesn't close it.
let openCardMenuId = null;

function toggleCardMenu(event, id) {
  event.stopPropagation();
  const wasOpen = openCardMenuId === id;
  closeCardMenu();
  if (wasOpen) return;
  openCardMenuId = id;
  const card = document.getElementById(`card-${id}`);
  card.classList.add('menu-open');
  card.querySelector('.card-menu').classList.add('open');
  card.querySelector('.card-menu > .btn-icon').setAttribute('aria-expanded', 'true');
}

function closeCardMenu() {
  openCardMenuId = null;
  document.querySelectorAll('.anime-card.menu-open').forEach(card => {
    card.classList.remove('menu-open');
    card.querySelector('.card-menu').classList.remove('open');
    card.querySelector('.card-menu > .btn-icon').setAttribute('aria-expanded', 'false');
  });
}

document.addEventListener('click', e => { if (!e.target.closest('.card-menu')) closeCardMenu(); });

// Nyaa searches: tried top to bottom, the next only when the ones above find nothing to grab.
// Older entries only have search_title.
function searchTitlesOf(e) {
  return e.search_titles?.length ? e.search_titles : [e.search_title || e.title];
}

let _searchEditId = null;

function openSearchEditor(id) {
  const e = watchlistById[id];
  if (!e) return;
  _searchEditId = id;
  document.getElementById('searchModalTitle').textContent = `${e.title} · Season ${e.season}`;
  renderSearchRows(searchTitlesOf(e));
  document.getElementById('searchModal').classList.add('open');
}

function closeSearchEditor() {
  document.getElementById('searchModal').classList.remove('open');
  _searchEditId = null;
}

function currentSearchRows() {
  return [...document.querySelectorAll('#searchRows input')].map(i => i.value);
}

function renderSearchRows(titles) {
  const last = titles.length - 1;
  document.getElementById('searchRows').innerHTML = titles.map((t, i) => `
    <div class="search-row">
      <span class="search-num">${i + 1}</span>
      <input type="text" value="${escHtml(t)}" placeholder="nyaa search text" autocomplete="off"
             onkeydown="if(event.key==='Enter') saveSearches()"/>
      <button class="btn-icon" title="Try earlier" onclick="moveSearchRow(${i}, -1)" ${i === 0 ? 'disabled' : ''}>↑</button>
      <button class="btn-icon" title="Try later" onclick="moveSearchRow(${i}, 1)" ${i === last ? 'disabled' : ''}>↓</button>
      <button class="btn-icon danger" title="Remove" onclick="removeSearchRow(${i})">✕</button>
    </div>`).join('');
}

function addSearchRow() {
  renderSearchRows([...currentSearchRows(), '']);
  const inputs = document.querySelectorAll('#searchRows input');
  inputs[inputs.length - 1].focus();
}

function moveSearchRow(i, delta) {
  const t = currentSearchRows();
  [t[i], t[i + delta]] = [t[i + delta], t[i]];
  renderSearchRows(t);
}

function removeSearchRow(i) {
  const t = currentSearchRows();
  t.splice(i, 1);
  renderSearchRows(t.length ? t : ['']);
}

async function saveSearches() {
  if (!_searchEditId) return;
  const res = await api.watchlist.patch(_searchEditId, { search_titles: currentSearchRows() });
  if (!res.ok) { toast('Could not save searches', 'error'); return; }
  const e = await res.json();
  toast(`Saved ${e.search_titles.length} search${e.search_titles.length === 1 ? '' : 'es'}`, 'success');
  closeSearchEditor();
  loadWatchlist();
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeCardMenu(); });

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
    // Several searches can be typed separated by |; the server drops blanks and falls back to the title
    search_titles: document.getElementById('searchTitleInput').value.split('|'),
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
    const searches = searchTitlesOf(entry);
    if (searches.length > 1 || searches[0] !== title) addMsg += ` · Nyaa: "${searches.join('", "')}"`;
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
