// Development configuration data for standalone frontend development
// Workspace s-john
// including a user object
export const workspaceData = {
    'name': 's-john',
    'creation_timestamp': '2025-10-03T06:52:01Z',
    'version': '5091101099',
    'status': 'ready',
    'storage': {
        'buckets': [
            's-john'
        ],
        'credentials': {
            'bucketname': 's-john',
            'access': 'REDACTED',
            'secret': 'REDACTED',
            'endpoint': 'https://endpoint-kalpha',
            'region': 'region-kalpha'
        },
        'bucket_access_requests': [
            {
                'workspace': 's-jane',
                'bucket': 's-john',
                'permission': 'WriteOnly',
                'request_timestamp': '2025-09-29T10:28:00Z',
                'denied_timestamp': '2025-09-29T10:28:00Z'
            },
            {
                'workspace': 's-jeff',
                'bucket': 's-john',
                'permission': 'ReadWrite',
                'request_timestamp': '2025-09-29T10:28:00Z'
            },
            {
                'workspace': 's-john',
                'bucket': 's-joe',
                'permission': 'ReadWrite',
                'request_timestamp': '2025-09-29T10:25:00Z'
            },
            {
                'workspace': 's-john',
                'bucket': 's-jeff',
                'permission': 'ReadWrite',
                'request_timestamp': '2025-09-29T10:26:00Z'
            },
            {
                'workspace': 's-john',
                'bucket': 's-jane',
                'permission': 'ReadWrite',
                'request_timestamp': '2025-09-29T10:27:00Z'
            },
            {
                'workspace': 's-john',
                'bucket': 's-jeff-shared',
                'permission': 'ReadWrite'
            }
        ]
    },
    'datalab': {
        'memberships': [
            {
                'member': 'john',
                'role': 'owner',
                'creation_timestamp': '2025-10-03T12:37:30.134696Z'
            },
            {
                'member': 'alice',
                'role': 'user',
                'creation_timestamp': '2025-12-21T19:04:26.764528Z'
            }
        ],
        'status': 'AlwaysOn'
    },
    'user': {
        'name': 'alice',
        'permissions': [
            'VIEW_BUCKETS',
            'VIEW_BUCKET_CREDENTIALS',
            'VIEW_MEMBERS',
        ]
    }
}

export const endpointsData = []
