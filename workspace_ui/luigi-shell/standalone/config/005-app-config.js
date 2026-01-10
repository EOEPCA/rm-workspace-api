// Development configuration data for standalone frontend development
// Workspace ws-bob
// including a user object
export const workspaceData = {
    'name': 'ws-bob',
    'creation_timestamp': '2025-10-20T11:58:48Z',
    'version': '1099881806',
    'status': 'ready',
    'storage': {
        'buckets': [
            'ws-bob'
        ],
        'credentials': {
            'bucketname': 'ws-bob',
            'access': 'bob',
            'secret': 'REDACTED',
            'endpoint': 'https://minio.develop.eoepca.org',
            'region': 'eoepca-demo'
        },
        'bucket_access_requests': [
            {
                'workspace': 'ws-bob',
                'bucket': 'ws-frank-stagein',
                'permission': 'ReadWrite',
                'request_timestamp': '2025-10-21T09:01:54.137000Z',
                'grant_timestamp': '2025-10-21T09:01:54.137000Z'
            },
            {
                'workspace': 'ws-bob',
                'bucket': 'ws-frank',
                'permission': 'ReadWrite',
                'request_timestamp': '2025-10-21T09:01:57.324000Z',
                'denied_timestamp': '2025-10-21T09:01:57.324000Z'
            },
            {
                'workspace': 'ws-bob',
                'bucket': 'ws-alice',
                'permission': 'ReadWrite',
                'request_timestamp': '2025-10-21T09:01:57.324000Z',
            },
            {
                'workspace': 'ws-bob',
                'bucket': 'ws-alice-2',
                'permission': 'ReadWrite'
            },
            {
                'workspace': 'ws-bob',
                'bucket': 'ws-alice-3',
                'permission': 'ReadWrite'
            },
            {
                'workspace': 'ws-bob',
                'bucket': 'ws-eric',
                'permission': 'ReadWrite'
            },
            {
                'workspace': 'ws-bob',
                'bucket': 'ws-eric-shared',
                'permission': 'ReadWrite'
            }
        ]
    },
    'datalab': {
        'memberships': [
            {
                'member': 'bob',
                'role': 'owner',
                'creation_timestamp': '2025-12-21T19:04:26.764528Z'
            },
            {
                'member': 'alice',
                'role': 'user',
                'creation_timestamp': '2025-12-21T19:04:26.764528Z'
            }
        ]
    },
    'user': {
        'name': 'alice',
        'permissions': [
            'VIEW_BUCKETS',
            'VIEW_BUCKET_CREDENTIALS',
            'VIEW_MEMBERS',
            'xMANAGE_MEMBERS',
            'VIEW_DATABASES',
            'MANAGE_DATABASES',
        ]
    },
    'databases': [
        {
            name: 'prod',
            storage: '10Gi'
        },
        {
            name: 'dev',
            storage: '1Gi'
        }
    ],

}

export const endpointsData = []
