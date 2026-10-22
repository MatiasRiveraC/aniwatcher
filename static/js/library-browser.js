// ── Library Tree Browser ──────────────────────────────────────────────────────

let _libSelectedPath = null;

async function initLibraryTree() {
  const tree   = document.getElementById('libTree');
  const rootLbl = document.getElementById('libTreeRoot');
  tree.innerHTML = '<div class="lib-loading">Loading…</div>';
  clearLibDetail();

  try {
    const data = await api.library.browse();
    if (data.error) {
      tree.innerHTML = `<div class="lib-error">${escHtml(data.error)}<br><small>Check Anime Library Path in Settings.</small></div>`;
      return;
    }
    rootLbl.textContent = data.path;
    tree.innerHTML = '';
    if (!data.items.length) {
      tree.innerHTML = '<div class="lib-empty">No folders found.</div>';
      return;
    }
    for (const item of data.items) {
      tree.appendChild(_makeNode(item, 0));
    }
  } catch (e) {
    tree.innerHTML = '<div class="lib-error">Failed to load library.</div>';
  }
}

function _makeNode(item, depth) {
  const node = document.createElement('div');
  node.className = 'tree-node';
  node.dataset.path = item.path;
  node.dataset.type = item.type;

  const row = document.createElement('div');
  row.className = 'tree-row';
  row.style.paddingLeft = (depth * 16 + 8) + 'px';

  if (item.type === 'dir') {
    row.innerHTML = `
      <span class="tree-arrow">▶</span>
      <span class="tree-icon">📁</span>
      <span class="tree-label">${escHtml(item.name)}</span>`;
    row.addEventListener('click', () => _toggleDir(node, item.path, depth));
  } else {
    row.innerHTML = `
      <span class="tree-arrow" style="visibility:hidden">▶</span>
      <span class="tree-icon">🎬</span>
      <span class="tree-label file">${escHtml(item.name)}</span>
      <span class="tree-file-badge" id="badge-${_pathId(item.path)}"></span>`;
    row.addEventListener('click', () => _selectFile(item.path, row));
    // Lazy-check dirty status
    _checkFileDirty(item.path, node);
  }

  node.appendChild(row);
  return node;
}

async function _toggleDir(node, path, depth) {
  const row      = node.querySelector('.tree-row');
  const arrow    = row.querySelector('.tree-arrow');
  const children = node.querySelector('.tree-children');

  if (children) {
    // Collapse
    children.remove();
    arrow.textContent = '▶';
    row.classList.remove('expanded');
    return;
  }

  arrow.textContent = '⏳';
  row.classList.add('expanded');

  try {
    const data = await api.library.browse(path);
    arrow.textContent = '▼';

    const childContainer = document.createElement('div');
    childContainer.className = 'tree-children';

    if (!data.items || !data.items.length) {
      const empty = document.createElement('div');
      empty.className = 'tree-empty';
      empty.style.paddingLeft = ((depth + 1) * 16 + 8) + 'px';
      empty.textContent = 'Empty';
      childContainer.appendChild(empty);
    } else {
      for (const item of data.items) {
        childContainer.appendChild(_makeNode(item, depth + 1));
      }
    }
    node.appendChild(childContainer);
  } catch {
    arrow.textContent = '▶';
    row.classList.remove('expanded');
  }
}

async function _checkFileDirty(path, node) {
  try {
    const info  = await api.library.inspectFile(path);
    const badge = document.getElementById('badge-' + _pathId(path));
    if (!badge) return;
    if (info.is_dirty) {
      badge.textContent = 'dirty';
      badge.className   = 'tree-file-badge dirty';
      node.querySelector('.tree-row').classList.add('file-dirty');
    } else {
      badge.textContent = 'clean';
      badge.className   = 'tree-file-badge clean';
    }
  } catch {}
}

async function _selectFile(path, row) {
  // Highlight selected row
  document.querySelectorAll('.tree-row.selected').forEach(r => r.classList.remove('selected'));
  row.classList.add('selected');
  _libSelectedPath = path;

  const detail = document.getElementById('libDetail');
  detail.innerHTML = '<div class="lib-detail-empty">Loading…</div>';

  try {
    const info = await api.library.inspectFile(path);
    _renderDetail(info);
  } catch {
    detail.innerHTML = '<div class="lib-detail-empty">Failed to load metadata.</div>';
  }
}

function _renderDetail(info) {
  const detail = document.getElementById('libDetail');

  const segTitle   = info.segment_title || '';
  const dirtyTracks = (info.track_names || []).filter(t => t.name);

  const segHtml = segTitle
    ? `<div class="detail-tag-row"><span class="detail-tag-label">Segment title</span><span class="meta-seg-title">${escHtml(segTitle)}</span></div>`
    : '';

  const tracksHtml = dirtyTracks.length
    ? dirtyTracks.map(t => `
        <div class="detail-tag-row">
          <span class="detail-tag-label">Track ${t.id} (${escHtml(t.type)})</span>
          <span class="meta-track-badge">${escHtml(t.name)}</span>
        </div>`).join('')
    : '';

  const allTracksHtml = (info.track_names || []).map(t => `
    <div class="detail-track-row">
      <span class="detail-track-id">#${t.id}</span>
      <span class="detail-track-type">${escHtml(t.type)}</span>
      <span class="detail-track-name ${t.name ? 'has-name' : ''}">${t.name ? escHtml(t.name) : '<span style="color:var(--muted)">—</span>'}</span>
    </div>`).join('');

  const statusClass = info.is_dirty ? 'dirty' : 'clean';
  const statusText  = info.is_dirty ? '⚠ Dirty — has embedded metadata' : '✓ Clean';

  detail.innerHTML = `
    <div class="detail-filename">${escHtml(info.filename)}</div>
    <div class="meta-status ${statusClass}" style="display:inline-block;margin:.5rem 0 1rem">${statusText}</div>

    ${info.is_dirty ? `
      <div class="detail-section-title">Dirty fields</div>
      <div class="detail-tags">${segHtml}${tracksHtml}</div>
    ` : ''}

    <div class="detail-section-title" style="margin-top:1rem">All tracks</div>
    <div class="detail-tracks-table">
      <div class="detail-track-row header">
        <span class="detail-track-id">#</span>
        <span class="detail-track-type">Type</span>
        <span class="detail-track-name">Name tag</span>
      </div>
      ${allTracksHtml || '<div style="color:var(--muted);font-size:.8rem;padding:.5rem 0">No tracks found</div>'}
    </div>

    ${info.is_dirty ? `
      <button class="btn-settings-save" style="margin-top:1.25rem;width:100%" id="libCleanBtn"
              onclick="cleanLibFile('${escHtml(info.path)}')">
        🧹 Clean this file
      </button>
    ` : ''}
  `;
}

async function cleanLibFile(path) {
  const btn = document.getElementById('libCleanBtn');
  btn.disabled = true;
  btn.textContent = '⏳ Cleaning…';

  const res = await api.library.cleanFile(path);
  if (res.ok) {
    showToast('File cleaned', 'success');
    // Refresh detail panel and update badge
    const info = await api.library.inspectFile(path);
    _renderDetail(info);
    const badge = document.getElementById('badge-' + _pathId(path));
    if (badge) {
      badge.textContent = 'clean';
      badge.className   = 'tree-file-badge clean';
      const row = badge.closest('.tree-row');
      if (row) row.classList.remove('file-dirty');
    }
  } else {
    btn.disabled    = false;
    btn.textContent = '🧹 Clean this file';
    showToast('Clean failed', 'error');
  }
}

function clearLibDetail() {
  document.getElementById('libDetail').innerHTML =
    '<div class="lib-detail-empty">Select an MKV file to inspect its metadata</div>';
}

function _pathId(path) {
  // Safe CSS id from a path
  return path.replace(/[^a-zA-Z0-9]/g, '_');
}

// Auto-init when Settings tab opens (hook into the existing DOMContentLoaded listener)
document.addEventListener('DOMContentLoaded', () => {
  const tabBtns = document.querySelectorAll('.tab-btn');
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      if (btn.textContent.trim() === 'Settings') initLibraryTree();
    });
  });
});
