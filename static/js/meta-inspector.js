// ── MKV Metadata Inspector ────────────────────────────────────────────────────

let _metaEntryId = null;

async function openMetaInspector(entryId) {
  _metaEntryId = entryId;
  const overlay = document.getElementById('metaModal');
  const body    = document.getElementById('metaModalBody');
  const pathEl  = document.getElementById('metaModalPath');

  body.innerHTML    = '<div class="modal-empty">Scanning files…</div>';
  pathEl.textContent = '';
  overlay.classList.add('open');

  try {
    const data = await api.watchlist.inspectMetadata(entryId);

    if (!data.path_found) {
      body.innerHTML = `
        <div class="modal-empty">
          No files found.<br>
          <small style="color:var(--muted)">Check that <b>Anime Library Path</b> in Settings is correct.</small>
        </div>`;
      return;
    }

    pathEl.textContent = data.path_found;

    if (!data.files.length) {
      body.innerHTML = '<div class="modal-empty">No MKV files found in this season folder.</div>';
      return;
    }

    const dirtyCount = data.files.filter(f => f.is_dirty).length;
    const summary = dirtyCount === 0
      ? `<div class="meta-summary ok">✓ All ${data.files.length} files are clean</div>`
      : `<div class="meta-summary dirty">⚠ ${dirtyCount} of ${data.files.length} files have embedded metadata — click Clean to fix</div>`;

    const rows = data.files.map(f => {
      const segTitle   = f.segment_title || '';
      const trackNames = f.track_names.filter(t => t.name).map(t =>
        `<span class="meta-track-badge">${escHtml(t.type[0].toUpperCase())}: ${escHtml(t.name)}</span>`
      ).join('');

      const statusBadge = f.is_dirty
        ? `<span class="meta-status dirty">dirty</span>`
        : `<span class="meta-status clean">clean</span>`;

      const cleanBtn = f.is_dirty
        ? `<button class="btn-meta-clean" onclick="cleanSingleFile(${_metaEntryId}, '${escHtml(f.path)}', this)">Clean</button>`
        : '';

      return `
        <div class="meta-row ${f.is_dirty ? 'dirty' : ''}">
          <div class="meta-filename">${escHtml(f.filename)}</div>
          <div class="meta-tags">
            ${segTitle ? `<span class="meta-seg-title">Title: ${escHtml(segTitle)}</span>` : ''}
            ${trackNames}
            ${!segTitle && !trackNames ? '<span style="color:var(--muted);font-size:.75rem">no embedded titles</span>' : ''}
          </div>
          <div class="meta-row-right">
            ${statusBadge}
            ${cleanBtn}
          </div>
        </div>`;
    }).join('');

    body.innerHTML = summary + `<div class="meta-list">${rows}</div>`;

    if (dirtyCount > 0) {
      body.innerHTML += `
        <div style="margin-top:1rem;display:flex;justify-content:flex-end">
          <button class="btn-settings-save" onclick="cleanAllVisible(${entryId})">
            🧹 Clean All ${dirtyCount} dirty files
          </button>
        </div>`;
    }

  } catch (e) {
    body.innerHTML = '<div class="modal-empty">Failed to load metadata.</div>';
  }
}

function closeMetaModal() {
  document.getElementById('metaModal').classList.remove('open');
  _metaEntryId = null;
}

async function cleanSingleFile(entryId, path, btn) {
  btn.disabled    = true;
  btn.textContent = '…';
  const res = await api.watchlist.cleanFile(entryId, path);
  if (res.ok) {
    // Refresh the row
    const row = btn.closest('.meta-row');
    row.classList.remove('dirty');
    row.querySelector('.meta-status').className   = 'meta-status clean';
    row.querySelector('.meta-status').textContent = 'clean';
    row.querySelector('.meta-tags').innerHTML     = '<span style="color:var(--muted);font-size:.75rem">no embedded titles</span>';
    btn.remove();
    showToast('File cleaned', 'success');
  } else {
    btn.disabled    = false;
    btn.textContent = 'Clean';
    showToast('Clean failed', 'error');
  }
}

async function cleanAllVisible(entryId) {
  const btns = document.querySelectorAll('.btn-meta-clean');
  for (const btn of btns) {
    await cleanSingleFile(entryId, btn.closest('.meta-row').querySelector('.meta-filename').textContent, btn);
  }
  // Refresh the whole modal to update summary
  openMetaInspector(entryId);
}
