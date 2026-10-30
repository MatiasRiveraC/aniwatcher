// ── Manual torrent picker + Completed files modal ─────────────────────────────

let _pickEntryId   = null;
let _pickCandidates = [];
let _pickTotal      = null;

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
    openPicker(res.candidates, res.total_episodes);
  } else {
    toast(res.ok ? 'Full season queued — check your torrent client' : (res.error || 'Error'), res.ok ? 'warn' : 'error');
  }
  setTimeout(() => { loadWatchlist(); loadStatus(); }, 2000);
}

function pad2(n) { return String(n).padStart(2, '0'); }

// What a batch holds, against the season's episode count.
function coverageHtml(r, total) {
  if (r.coverage === 'complete') return `<span class="pick-item-cov complete">${pad2(r.range[0])}–${pad2(r.range[1])} ✓ complete</span>`;
  if (r.coverage === 'partial')  return `<span class="pick-item-cov partial">${pad2(r.range[0])}–${pad2(r.range[1])} of ${total} ⚠ partial</span>`;
  return '<span class="pick-item-cov">episodes not in the name</span>';
}

function openPicker(candidates, total) {
  _pickCandidates = candidates;
  _pickTotal      = total || null;
  const nb = candidates.filter(r => r.batch).length;
  document.getElementById('pickSubtitle').textContent =
    `${nb} batches · ${candidates.length - nb} single episodes${total ? ` · ${total} in the season` : ''} — pick one to download`;
  document.getElementById('pickOverlay').classList.add('open');
  const body = document.getElementById('pickBody');
  if (!candidates.length) {
    body.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--muted)">No results found on nyaa</div>';
    return;
  }
  body.innerHTML = candidates.map((r, i) => {
    const section = (r.batch && i === 0) ? '<div class="pick-section">Batches</div>'
      : (!r.batch && (i === 0 || candidates[i - 1].batch)) ? '<div class="pick-section">Single episodes</div>' : '';
    const kind = r.batch ? coverageHtml(r, total) : `<span class="pick-item-kind">Ep ${pad2(r.ep_num)}</span>`;
    const audioLabel = r.audio_score === 3 ? '★ preferred' : r.audio_score === 0 ? '⚠ dub' : 'subbed';
    const res1080    = r.title.match(/1080p/i) ? '1080p' : r.title.match(/720p/i) ? '720p' : '';
    // Clicking the row opens what the release page says; only ↓ Get downloads.
    return `${section}
    <div class="pick-row">
      <div class="pick-item" onclick="toggleDetails(${i})">
        <div class="pick-item-info">
          <div class="pick-item-title" title="${escHtml(r.title)}">${escHtml(r.title)}</div>
          <div class="pick-item-meta">
            <span class="pick-item-size">📦 ${r.size || '?'}</span>
            ${kind}
            <span class="pick-item-seeds ${r.seeders ? '' : 'dead'}">▲ ${r.seeders}</span>
            ${res1080 ? `<span>${res1080}</span>` : ''}
            <span>${audioLabel}</span>
          </div>
        </div>
        ${r.view_id ? `<button class="pick-more" id="pm-${i}" onclick="event.stopPropagation();toggleDetails(${i})">ⓘ Details</button>` : ''}
        <button class="pick-btn" onclick="event.stopPropagation();pickTorrent(${i})">↓ Get</button>
      </div>
      <div class="pick-details" id="pd-${i}" hidden></div>
    </div>`;
  }).join('');
}

// ── Release details (description, files, comments from the nyaa page) ────────

async function toggleDetails(idx) {
  const r  = _pickCandidates[idx];
  const el = document.getElementById(`pd-${idx}`);
  if (!r || !r.view_id || !el) return;
  const btn = document.getElementById(`pm-${idx}`);
  if (!el.hidden) { el.hidden = true; if (btn) btn.textContent = 'ⓘ Details'; return; }
  el.hidden = false;
  if (btn) btn.textContent = '▴ Hide';
  if (el.dataset.loaded) return;
  el.innerHTML = '<div class="pd-note">Reading the nyaa page…</div>';
  const d = await api.nyaaDetails(r.view_id).catch(() => ({ error: 'Could not reach AniWatcher' }));
  if (d.error) { el.innerHTML = `<div class="pd-note bad">${escHtml(d.error)}</div>`; return; }
  el.dataset.loaded = '1';
  el.innerHTML = detailsHtml(d, r);
}

// Which of the season's episodes a release holds, from its real file list.
function filesSummaryHtml(d, r) {
  const eps = d.episodes;
  const parts = [];
  if (eps.length) {
    let line = `${eps.length} episode${eps.length === 1 ? '' : 's'} (${pad2(eps[0])}–${pad2(eps[eps.length - 1])})`;
    if (_pickTotal && r.batch) {
      const have = new Set(eps);
      const missing = [];
      for (let e = 1; e <= _pickTotal; e++) if (!have.has(e)) missing.push(pad2(e));
      line += missing.length
        ? ` <span class="pd-warn">⚠ missing ${missing.length > 8 ? missing.length + ' of ' + _pickTotal : missing.join(', ')}</span>`
        : ' <span class="pd-good">✓ all ' + _pickTotal + '</span>';
    }
    parts.push(line);
  } else if (d.files.length) {
    parts.push('<span class="pd-warn">no episode numbers in the file names</span>');
  }
  if (d.extras)      parts.push(`${d.extras} extra${d.extras === 1 ? '' : 's'} (OP/ED, previews…)`);
  if (d.other_files) parts.push(`${d.other_files} other file${d.other_files === 1 ? '' : 's'}`);
  parts.push(`${d.files.length} files`);
  return parts.join(' · ');
}

function detailsHtml(d, r) {
  const files = d.files.map(f => {
    const name = f.path.split('/').pop();
    const cls  = !f.video ? 'other' : f.extra ? 'extra' : '';
    const tag  = f.episode != null ? `<b>${pad2(f.episode)}</b>` : f.extra ? '<i>extra</i>' : !f.video ? '<i>file</i>' : '<i>?</i>';
    return `<li class="${cls}"><span class="pd-ep">${tag}</span><span class="pd-name" title="${escHtml(f.path)}">${escHtml(name)}</span><span class="pd-size">${escHtml(f.size)}</span></li>`;
  }).join('');
  const comments = d.comments.map(c =>
    `<div class="pd-comment"><b>${escHtml(c.user || 'anonymous')}</b><div>${renderMarkdown(c.text)}</div></div>`).join('');
  return `
    <div class="pd-summary">${filesSummaryHtml(d, r)}</div>
    <details class="pd-files" ${d.files.length <= 30 ? 'open' : ''}><summary>Files</summary><ul>${files}</ul></details>
    ${d.description ? `<div class="pd-desc">${renderMarkdown(d.description)}</div>` : '<div class="pd-note">No description.</div>'}
    ${d.comment_count ? `<details class="pd-comments"><summary>${d.comment_count} comment${d.comment_count === 1 ? '' : 's'}</summary>${comments}</details>` : ''}
    <div class="pd-links">
      <a href="${escHtml(d.url)}" target="_blank" rel="noopener noreferrer">Open on nyaa ↗</a>
      ${d.info_url ? `<a href="${escHtml(d.info_url)}" target="_blank" rel="noopener noreferrer nofollow">Group site ↗</a>` : ''}
      ${d.submitter ? `<span>uploaded by ${escHtml(d.submitter)}</span>` : ''}
    </div>`;
}

// A small markdown renderer for nyaa descriptions. The text is HTML-escaped
// first, and the only tags added are the ones below, with http(s) URLs only —
// a description can never inject markup or script.
function renderMarkdown(src) {
  const safeUrl = u => /^https?:\/\//i.test(u) ? u : null;
  const inline = s => s
    .replace(/!\[([^\]]*)\]\(([^)\s]+)[^)]*\)/g, (m, alt, u) =>
      safeUrl(u) ? `<img src="${u}" alt="${alt}" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">` : m)
    .replace(/\[((?:<img[^>]*>|[^\]])+)\]\(([^)\s]+)[^)]*\)/g, (m, text, u) =>
      safeUrl(u) ? `<a href="${u}" target="_blank" rel="noopener noreferrer nofollow">${text}</a>` : m)
    .replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2" target="_blank" rel="noopener noreferrer nofollow">$2</a>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*|__([^_]+)__/g, (m, a, b) => `<strong>${a || b}</strong>`)
    .replace(/(^|[^\w*])\*([^*\n]+)\*(?!\w)/g, '$1<em>$2</em>');

  const out = [];
  let list = false, code = false, codeBuf = [];
  for (const raw of escHtml(src).replace(/\r/g, '').split('\n')) {
    if (/^\s*```/.test(raw)) {
      if (code) { out.push(`<pre>${codeBuf.join('\n')}</pre>`); codeBuf = []; }
      code = !code; continue;
    }
    if (code) { codeBuf.push(raw); continue; }
    let line = raw.replace(/^\s*(?:&gt;\s*)+/, '');            // blockquotes → plain
    const item = /^\s*[-*+]\s+(.*)/.exec(line) || /^\s*\d+\.\s+(.*)/.exec(line);
    if (item) { if (!list) { out.push('<ul>'); list = true; } out.push(`<li>${inline(item[1])}</li>`); continue; }
    if (list) { out.push('</ul>'); list = false; }
    const h = /^(#{1,6})\s+(.*)/.exec(line);
    if (h) { out.push(`<div class="md-h">${inline(h[2])}</div>`); continue; }
    if (/^\s*(?:[-_*]\s*){3,}$/.test(line)) { out.push('<hr>'); continue; }
    if (/^\s*\|?\s*:?-{3,}/.test(line)) continue;                 // table rule rows
    out.push(line.trim() ? `<div>${inline(line.replace(/^\s*\||\|\s*$/g, '').replace(/\s*\|\s*/g, ' · '))}</div>` : '<div class="md-gap"></div>');
  }
  if (list) out.push('</ul>');
  if (code) out.push(`<pre>${codeBuf.join('\n')}</pre>`);
  return out.join('');
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
