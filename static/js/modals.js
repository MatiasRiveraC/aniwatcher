// ── Manual torrent picker + Completed files modal ─────────────────────────────

let _pickEntryId   = null;
let _pickCandidates = [];

async function toggleManualPick(id) {
  const res = await api.watchlist.toggleManual(id);
  toast(
    res.manual_pick
      ? '🎯 Manual pick ON — click ⬇ Full to choose torrent'
      : 'Manual pick OFF — auto mode',
    res.manual_pick ? 'warn' : 'success'
  );
  loadWatchlist();
}

async function fullSeason(id) {
  const btn = document.getElementById(`fs-${id}`);
  if (btn) { btn.classList.add('spinning'); btn.textContent = '⟳ Searching…'; }
  const res = await api.watchlist.fullSeason(id);
  if (res.manual) {
    _pickEntryId = id;
    openPicker(res.candidates);
  } else {
    toast(res.ok ? 'Full season queued — check your torrent client' : (res.error || 'Error'), res.ok ? 'warn' : 'error');
  }
  setTimeout(() => { loadWatchlist(); loadStatus(); }, 2000);
}

function openPicker(candidates) {
  _pickCandidates = candidates;
  document.getElementById('pickSubtitle').textContent = `${candidates.length} results — pick one to download`;
  document.getElementById('pickOverlay').classList.add('open');
  const body = document.getElementById('pickBody');
  if (!candidates.length) {
    body.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--muted)">No results found on nyaa</div>';
    return;
  }
  body.innerHTML = candidates.map((r, i) => {
    const audioLabel = r.audio_score === 3 ? '★ preferred' : r.audio_score === 0 ? '⚠ dub' : 'subbed';
    const res1080    = r.title.match(/1080p/i) ? '1080p' : r.title.match(/720p/i) ? '720p' : '';
    return `
    <div class="pick-item" onclick="pickTorrent(${i})">
      <div class="pick-item-info">
        <div class="pick-item-title" title="${escHtml(r.title)}">${escHtml(r.title)}</div>
        <div class="pick-item-meta">
          <span class="pick-item-size">📦 ${r.size || '?'}</span>
          <span class="pick-item-seeds">▲ ${r.seeders}</span>
          ${res1080 ? `<span>${res1080}</span>` : ''}
          <span>${audioLabel}</span>
        </div>
      </div>
      <button class="pick-btn" onclick="event.stopPropagation();pickTorrent(${i})">↓ Get</button>
    </div>`;
  }).join('');
}

async function pickTorrent(idx) {
  const r = _pickCandidates[idx];
  if (!r || !_pickEntryId) return;
  const res = await api.watchlist.manualDownload(_pickEntryId, { url: r.link, title: r.title });
  toast(res.ok ? 'Sent to torrent client ✓' : (res.error || 'Error'), res.ok ? 'success' : 'error');
  if (res.ok) { closePicker(); loadWatchlist(); }
}

function closePicker() {
  document.getElementById('pickOverlay').classList.remove('open');
  _pickEntryId = null;
}

// Completed files modal
async function openCompletedModal() {
  document.getElementById('completedModal').classList.add('open');
  document.getElementById('completedBody').innerHTML = '<div class="modal-empty">Scanning…</div>';
  await _refreshCompletedModal();
}

async function _refreshCompletedModal() {
  const data = await api.completedFiles.list();
  document.getElementById('completedPath').textContent = data.path;
  const body = document.getElementById('completedBody');
  let html = '';

  if (data.dirs.length) {
    html += '<div class="modal-section-title">Folders</div>';
    html += data.dirs.map(d => `
      <div class="completed-dir" id="cdir-${_cid(d.path)}">
        <div class="completed-dir-row">
          <span class="completed-toggle" onclick="toggleCompletedDir('${escHtml(d.path)}')">▶</span>
          <span class="modal-item-icon">📁</span>
          <span class="modal-item-name" style="cursor:pointer" onclick="toggleCompletedDir('${escHtml(d.path)}')">${escHtml(d.name)}</span>
          <span class="modal-item-meta">${d.files} files · ${d.size_mb} MB</span>
          <button class="completed-del-btn" title="Delete folder" onclick="deleteCompleted('${escHtml(d.path)}', true)">🗑</button>
        </div>
        <div class="completed-dir-children" id="cdirch-${_cid(d.path)}" style="display:none"></div>
      </div>`).join('');
  }

  if (data.files.length) {
    html += '<div class="modal-section-title">Files</div>';
    html += data.files.map(f => `
      <div class="modal-item">
        <span class="modal-item-icon">🎬</span>
        <span class="modal-item-name">${escHtml(f.name)}</span>
        <span class="modal-item-meta">${f.size_mb} MB</span>
        <button class="completed-del-btn" title="Delete file" onclick="deleteCompleted('${escHtml(f.path)}', false)">🗑</button>
      </div>`).join('');
  }

  if (!data.dirs.length && !data.files.length) {
    html = '<div class="modal-empty">✓ Completed folder is empty</div>';
  }

  body.innerHTML = html;
}

async function toggleCompletedDir(path) {
  const id       = _cid(path);
  const children = document.getElementById('cdirch-' + id);
  const arrow    = document.querySelector(`#cdir-${id} .completed-toggle`);
  if (!children) return;

  if (children.style.display !== 'none') {
    children.style.display = 'none';
    arrow.textContent = '▶';
    return;
  }

  arrow.textContent = '⏳';
  const data = await api.completedFiles.dirContents(path);
  arrow.textContent = '▼';
  children.style.display = 'block';

  if (!data.items || !data.items.length) {
    children.innerHTML = '<div class="completed-dir-empty">Empty</div>';
    return;
  }

  children.innerHTML = data.items.map(f => `
    <div class="completed-file-row" id="cfile-${_cid(f.path)}">
      <span class="modal-item-icon" style="font-size:.8rem">${_fileIcon(f.ext)}</span>
      <span class="completed-file-name">${escHtml(f.name)}</span>
      <span class="modal-item-meta">${f.size_mb} MB</span>
      <button class="completed-del-btn" title="Delete file" onclick="deleteCompleted('${escHtml(f.path)}', false)">🗑</button>
    </div>`).join('');
}

async function deleteCompleted(path, isDir) {
  const label = isDir ? 'folder and all its contents' : 'file';
  if (!confirm(`Delete this ${label}?\n\n${path}`)) return;
  const res = await api.completedFiles.delete(path);
  if (res.ok) {
    showToast('Deleted', 'success');
    await _refreshCompletedModal();
  } else {
    showToast(res.error || 'Delete failed', 'error');
  }
}

function _cid(path) {
  return path.replace(/[^a-zA-Z0-9]/g, '_');
}

function _fileIcon(ext) {
  if (['.mkv','.mp4','.avi','.m4v','.mov','.wmv'].includes(ext)) return '🎬';
  if (ext === '.torrent') return '🧲';
  return '📄';
}

function closeCompletedModal() {
  document.getElementById('completedModal').classList.remove('open');
}
