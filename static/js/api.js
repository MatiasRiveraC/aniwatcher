// ── Centralized API layer ─────────────────────────────────────────────────────

const api = {
  _get:   url        => fetch(url).then(r => r.json()),
  _post:  (url, body) => fetch(url, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body:    body ? JSON.stringify(body) : undefined,
  }),
  _patch: (url, body) => fetch(url, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }),
  _del: url => fetch(url, { method: 'DELETE' }),

  watchlist: {
    list:           ()      => api._get('/api/watchlist'),
    add:            body    => api._post('/api/watchlist', body),
    patch:          (id, b) => api._patch(`/api/watchlist/${id}`, b),
    remove:         id      => api._del(`/api/watchlist/${id}`),
    fullSeason:     id      => api._post(`/api/watchlist/${id}/full-season`).then(r => r.json()),
    manualDownload: (id, b) => api._post(`/api/watchlist/${id}/manual-download`, b).then(r => r.json()),
    toggleManual:   id      => api._post(`/api/watchlist/${id}/toggle-manual`).then(r => r.json()),
    scan:            id      => api._post(`/api/watchlist/${id}/scan`).then(r => r.json()),
    reset:           id      => api._post(`/api/watchlist/${id}/reset`).then(r => r.json()),
    inspectMetadata: id      => api._get(`/api/watchlist/${id}/inspect-metadata`),
    cleanFile:       (id, path) => api._post(`/api/watchlist/${id}/clean-file`, { path }).then(r => r.json()),
  },

  search:  q    => api._get(`/api/search?q=${encodeURIComponent(q)}`),
  poll:    ()   => api._post('/api/poll'),
  status:  ()   => api._get('/api/status'),

  notifications: {
    list:     () => api._get('/api/notifications'),
    markRead: () => api._post('/api/notifications/read'),
  },

  downloaded: {
    list:   ()     => api._get('/api/downloaded'),
    delete: urls   => api._post('/api/downloaded/delete', { urls }).then(r => r.json()),
  },

  completedFiles: {
    list:       ()     => api._get('/api/completed-files'),
    dirContents:(path) => api._get('/api/completed-files/dir?path=' + encodeURIComponent(path)),
    delete:     (path) => api._post('/api/completed-files/delete', { path }).then(r => r.json()),
  },

  settings: {
    get:  ()    => api._get('/api/settings'),
    save: body  => api._post('/api/settings', body).then(r => r.json()),
  },

  cleanMetadata: {
    run:    () => api._post('/api/clean-metadata').then(r => r.json()),
    status: () => api._get('/api/clean-metadata/status'),
  },

  library: {
    browse:      (path) => api._get('/api/browse-library' + (path ? '?path=' + encodeURIComponent(path) : '')),
    inspectFile: (path) => api._get('/api/inspect-file?path=' + encodeURIComponent(path)),
    cleanFile:   (path) => api._post('/api/clean-file', { path }).then(r => r.json()),
  },
};
