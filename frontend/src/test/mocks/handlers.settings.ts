import { http, HttpResponse } from 'msw'

const baseSnapshot = {
  runtime_config_path: '/home/test/.config/fmriflow/settings.json',
  values: {
    FMRIFLOW_HOME: { env: null, persisted: null, effective: '', source: 'default' },
    FMRIFLOW_DATA: { env: null, persisted: null, effective: '', source: 'default' },
    FS_LICENSE: { env: null, persisted: null, effective: '', source: 'default' },
    FMRIFLOW_SINGULARITY_BIN: {
      env: null, persisted: null, effective: '', source: 'default',
    },
  },
  resolved: {
    FMRIFLOW_HOME: '/home/test/projects/fmriflow',
    FMRIFLOW_DATA: '/home/test/projects/fmriflow/data',
    builtin: '/usr/local/lib/python3.11/site-packages/fmriflow/builtin',
  },
  license_file_exists: false,
  subjects_db_exists: false,
}

export const settingsHandlers = [
  http.get('/api/settings', () => HttpResponse.json(baseSnapshot)),
  http.post('/api/settings', () =>
    HttpResponse.json({ ...baseSnapshot, restart_required: true }),
  ),
]
