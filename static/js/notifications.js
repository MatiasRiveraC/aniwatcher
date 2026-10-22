// ── Notifications ─────────────────────────────────────────────────────────────

function toggleNotifs() {
  const panel = document.getElementById('notifPanel');
  panel.classList.toggle('open');
  if (panel.classList.contains('open')) loadNotifs();
}

async function loadNotifs() {
  const list = await api.notifications.list();
  const el   = document.getElementById('notifList');
  if (!list.length) {
    el.innerHTML = '<div class="notif-empty">No notifications yet</div>';
    return;
  }
  el.innerHTML = list.slice().reverse().map(n => `
    <div class="notif-item ${n.kind || 'info'}">
      ${escHtml(n.message)}
      <div class="notif-time">${new Date(n.time).toLocaleString()}</div>
    </div>`).join('');
}

async function markRead() {
  await api.notifications.markRead();
  document.getElementById('bellBadge').style.display = 'none';
  loadNotifs();
}
