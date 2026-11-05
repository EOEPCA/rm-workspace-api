const s3 = {
  name: 'primary', type: 's3', ready: true,
  secret_ref: { name: 'ws-alice-s3', namespace: 'workspace' },
  endpoint: 'https://s3.example.org', region: 'demo',
  credentials: { AWS_ACCESS_KEY_ID: 'demo-access-key', AWS_SECRET_ACCESS_KEY: 'demo-secret-key' },
};

export const workspaceData = {
  name: 'ws-alice', version: '1', status: 'ready',
  storage: {
    available: true,
    buckets: [{ name: 'ws-alice', discoverable: true, lifecycle_rules: [] }],
    bucket_access_requests: [],
  },
  datalab: {
    available: true,
    available_store_types: ['database', 'document', 'cache'],
    memberships: [{ member: 'alice', role: 'owner' }],
    stores: [{ name: 'analytics', type: 'database', instance: 'pg0', storage: '1Gi' }],
    sessions: [{ name: 'default', state: 'started', ready: true, url: 'https://session.example.org' }],
    max_sessions: 3,
    connections: [s3, {
      name: 'pg0', type: 'postgres', ready: true,
      secret_ref: { name: 'ws-alice-postgres', namespace: 'workspace' },
      endpoint: 'postgres.example.org:5432',
      credentials: { user: 'demo', password: 'demo-password' },
    }],
    oauth2: [],
  },
  user: {
    name: 'alice',
    permissions: [
      'VIEW_BUCKETS', 'VIEW_CONNECTION_CREDENTIALS', 'VIEW_OAUTH2_CREDENTIALS',
      'VIEW_MEMBERS', 'VIEW_STORES', 'VIEW_SESSIONS',
      'MANAGE_BUCKETS', 'MANAGE_MEMBERS', 'MANAGE_STORES', 'MANAGE_SESSIONS',
    ],
  },
};

export const endpointsData = [{ id: 'Datalab (default)', url: workspaceData.datalab.sessions[0].url }];
