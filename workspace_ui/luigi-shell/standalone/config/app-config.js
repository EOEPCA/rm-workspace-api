// Dummy configuration data for standalone frontend development
export const workspaceData = {
  "name": "ws-bob",
  "creation_timestamp": "2025-06-19T15:00:36Z",
  "version": "919190705",
  "status": "ready",
  "storage": {
    "credentials": {
      "bucketname": "ws-bob",
      "access": "ws-bob",
      "secret": "secret",
      "endpoint": "https://minio.develop.eoepca.org",
      "region": "eoepca-demo"
    },
    "buckets": [
      "ws-bob",
      "ws-bob-new",
      "ws-eric-shared"
    ]
  },
  "cluster": {
    "kubeconfig": "**********",
    "status": "active"
  },
  "members": [
    "example-user-1",
    "test"
  ]
};

export const endpointsData = [
  {
    "id": "vcluster",
    "url": "ws-bob.ngx.develop.eoepca.org",
    "creation_timestamp": "2025-06-19T15:00:37Z"
  },
  {
    "id": "code-server",
    "url": "code-server-ws-bob.develop.eoepca.org",
    "creation_timestamp": "2025-07-02T13:39:14Z"
  },
  {
    "id": "workspace",
    "url": "ws-bob.develop.eoepca.org",
    "creation_timestamp": "2025-06-19T15:00:38Z"
  }
];

window.membershipsData = [
    {
      "member": "bob",
      "role": "owner",
      "creation_timestamp": "2025-06-19T15:00:37Z"
    },
{
  "member": "example-user-1",
  "role": "contributor",
  "creation_timestamp": "2025-06-19T15:00:37Z"
},
{
  "member": "test",
  "role": "contributor",
  "creation_timestamp": "2025-06-19T15:00:37Z"
},
{
  "member": "xy",
  "role": "contributor",
  "creation_timestamp": "2025-06-19T15:00:37Z"
}
];

window.bucketAccessRequestsData = [
  {
    "workspace": "ws-bob",
    "bucket": "ws-eric-shared",
    "permission": "readwrite",
    "request_timestamp": "2025-06-19T15:00:36Z",
    "grant_timestamp": "2025-07-03T12:34:11Z"
  },
  {
    "workspace": "ws-eric",
    "bucket": "ws-bob-new",
    "permission": "readwrite",
    "request_timestamp": "2025-06-19T15:00:36Z",
    "grant_timestamp": "2025-09-08T12:50:22Z"
  },
  {
    "workspace": "ws-bob",
    "bucket": "ws-eoepcauser-shared",
    "permission": "readwrite"
  },
  {
    "workspace": "ws-bob",
    "bucket": "ws-testui-1-shared",
    "permission": "readwrite"
  },
  {
    "workspace": "ws-bob",
    "bucket": "ws-testui-1-shared2",
    "permission": "readwrite"
  }
];
