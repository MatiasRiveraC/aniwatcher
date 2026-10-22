// ── Nyaa live search ──────────────────────────────────────────────────────────

let searchTimer = null;
let searchCache = [];

function onTitleInput() {
  clearTimeout(searchTimer);
  const q = document.getElementById('titleInput').value.trim();
  if (q.length < 3) { hideSearch(); return; }
  searchTimer = setTimeout(() => liveSearch(q), 500);
}

async function liveSearch(q) {
  const results = await api.search(q);
  const el = document.getElementById('searchResults');
  if (!results.length) { hideSearch(); return; }
  searchCache = results.slice(0, 8);
  el.style.display = 'block';
  el.innerHTML = searchCache.map((r, i) => `
    <div class="sr-item" data-idx="${i}">
      <span class="sr-title">${escHtml(r.title)}</span>
      <span class="sr-meta">
        <span class="sr-size">${escHtml(r.size)}</span>
        <span class="sr-seeds">▲ ${r.seeders}</span>
      </span>
    </div>`).join('');
  el.querySelectorAll('.sr-item').forEach(item => {
    item.addEventListener('mousedown', e => {
      e.preventDefault();
      selectResult(searchCache[parseInt(item.dataset.idx)].title);
    });
  });
}

function selectResult(t) {
  document.getElementById('titleInput').value = t;
  hideSearch();
}

function hideSearch() {
  const el = document.getElementById('searchResults');
  el.style.display = 'none';
  el.innerHTML = '';
  searchCache = [];
}
