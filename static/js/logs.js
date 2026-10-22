// ── Log streaming (SSE) ───────────────────────────────────────────────────────

window._logStarted = false;

function startLogStream() {
  window._logStarted = true;
  const es = new EventSource('/api/logs');
  es.onopen  = () => { document.getElementById('logStatus').textContent = 'Live'; };
  es.onerror = () => { document.getElementById('logStatus').textContent = 'Reconnecting…'; };
  es.onmessage = e => {
    if (!e.data.trim()) return;
    const viewer = document.getElementById('logViewer');
    const div    = document.createElement('div');
    div.className  = 'log-line ' + (
      e.data.includes(' ERROR ')   ? 'ERROR'   :
      e.data.includes(' WARNING ') ? 'WARNING' : 'INFO'
    );
    div.textContent = e.data;
    viewer.appendChild(div);
    while (viewer.children.length > 1000) viewer.removeChild(viewer.firstChild);
    if (document.getElementById('autoScroll').checked) viewer.scrollTop = viewer.scrollHeight;
  };
}

function clearLogs() {
  document.getElementById('logViewer').innerHTML = '';
}
