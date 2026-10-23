// ── Settings tab ──────────────────────────────────────────────────────────────

function showClientFields(client) {
  document.querySelectorAll('.qbit-only').forEach(el => {
    el.style.display = client === 'qbittorrent' ? '' : 'none';
  });
  document.querySelectorAll('.deluge-only').forEach(el => {
    el.style.display = client === 'qbittorrent' ? 'none' : '';
  });
}

function populateSettings(s) {
  const fields = [
    'preferred_resolution', 'preferred_groups',
    'poll_interval', 'watch_interval',
    'anime_base', 'torrent_done', 'torrent_incoming',
    'torrent_client',
    'deluge_host', 'deluge_port', 'deluge_user', 'deluge_pass',
    'qbit_url', 'qbit_user', 'qbit_pass', 'qbit_category',
    'mal_client_id',
  ];
  for (const key of fields) {
    const el = document.getElementById('s_' + key);
    if (el && s[key] !== undefined) el.value = s[key];
  }
  // Passwords never come back from the server; say whether one is saved.
  for (const key of ['deluge_pass', 'qbit_pass']) {
    const el = document.getElementById('s_' + key);
    if (el) el.placeholder = (s._secrets_set || []).includes(key)
      ? '(saved — leave blank to keep)' : '(not set)';
  }
  // Folders fixed by the server are shown but not editable.
  const locked = s._locked || [];
  for (const key of ['anime_base', 'torrent_done', 'torrent_incoming']) {
    const el = document.getElementById('s_' + key);
    if (el) el.readOnly = locked.includes(key);
  }
  const hint = document.getElementById('lockedPathsHint');
  if (hint) hint.style.display = locked.length ? '' : 'none';
  showClientFields(s.torrent_client || 'deluge');
  // Checkboxes
  const chk = document.getElementById('s_auto_clean_metadata');
  if (chk) chk.checked = s['auto_clean_metadata'] !== false;
}

async function loadSettingsTab() {
  try {
    const s = await api.settings.get();
    populateSettings(s);
  } catch (e) {
    showToast('Failed to load settings', 'error');
  }
}

async function saveSettings(event) {
  event.preventDefault();
  const btn = document.getElementById('settingsSaveBtn');
  btn.disabled = true;
  btn.textContent = 'Saving…';

  const form = document.getElementById('settingsForm');
  const body = {};
  for (const el of form.querySelectorAll('[name]')) {
    if (el.type === 'checkbox') {
      body[el.name] = el.checked;
    } else {
      body[el.name] = el.value;
    }
  }

  try {
    const res = await api.settings.save(body);
    if (res.ok) {
      showToast('Settings saved', 'success');
      populateSettings(res.settings);
    } else {
      showToast('Save failed', 'error');
    }
  } catch (e) {
    showToast('Save failed', 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Save Changes';
  }
}

async function resetSettings() {
  if (!confirm('Reset all settings to their defaults?')) return;
  try {
    // Fetch defaults by posting an empty object — the backend fills in defaults
    const res = await api.settings.save({});
    // Re-fetch clean state
    const s = await api.settings.get();
    populateSettings(s);
    showToast('Settings reset to defaults', 'success');
  } catch (e) {
    showToast('Reset failed', 'error');
  }
}

let _cleanPollTimer = null;

async function runCleanMetadata() {
  const btn    = document.getElementById('cleanMetaBtn');
  const result = document.getElementById('cleanMetaResult');

  btn.disabled    = true;
  btn.textContent = '⏳ Running…';
  result.style.display = 'none';

  try {
    const res = await api.cleanMetadata.run();
    if (!res.ok) {
      result.textContent    = `Error: ${res.error}`;
      result.className      = 'settings-tool-result error';
      result.style.display  = 'block';
      btn.disabled          = false;
      btn.textContent       = '🧹 Clean Now';
      return;
    }
    // Poll for completion
    _cleanPollTimer = setInterval(async () => {
      try {
        const st = await api.cleanMetadata.status();
        if (!st.running) {
          clearInterval(_cleanPollTimer);
          btn.disabled    = false;
          btn.textContent = '🧹 Clean Now';
          if (st.last) {
            const { cleaned, failed, total } = st.last;
            result.textContent   = `Done — ${cleaned} file${cleaned !== 1 ? 's' : ''} cleaned` +
              (failed ? `, ${failed} failed` : '') + ` (${total} MKVs scanned)`;
            result.className     = failed ? 'settings-tool-result warn' : 'settings-tool-result ok';
            result.style.display = 'block';
          }
        }
      } catch (_) {}
    }, 2000);
  } catch (e) {
    btn.disabled    = false;
    btn.textContent = '🧹 Clean Now';
    showToast('Clean failed', 'error');
  }
}

// Load settings when the tab becomes active
document.addEventListener('DOMContentLoaded', () => {
  const tabBtns = document.querySelectorAll('.tab-btn');
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      if (btn.textContent.trim() === 'Settings') loadSettingsTab();
    });
  });
});
