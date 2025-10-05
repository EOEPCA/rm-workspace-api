export const workspaceData =
{
  "name": "s-jeff",
  "creation_timestamp": "2025-10-03T06:52:00Z",
  "version": "5091112489",
  "status": "ready",
  "storage": {
    "buckets": [
      "s-jeff",
      "s-jeff-shared"
    ],
    "credentials": {
      "bucketname": "s-jeff",
      "access": "REDACTED",
      "secret": "REDACTED",
      "endpoint": "https://endpoint-kalpha",
      "region": "region-kalpha"
    },
    "bucket_access_requests": [
      {
        "workspace": "s-jeff",
        "bucket": "s-joe",
        "permission": "ReadWrite",
        "request_timestamp": "2025-09-29T10:05:00Z",
        "grant_timestamp": "2025-09-29T10:05:00Z"
      },
      {
        "workspace": "s-joe",
        "bucket": "s-jeff-shared",
        "permission": "ReadWrite",
        "request_timestamp": "2025-09-29T10:15:00Z",
        "grant_timestamp": "2025-09-29T10:15:00Z"
      },
      {
        "workspace": "s-jeff",
        "bucket": "s-john",
        "permission": "ReadWrite"
      }
    ]
  },
  "datalab": {
    "memberships": [
      {
        "member": "jeff",
        "role": "owner",
        "creation_timestamp": "2025-10-03T12:36:54.879107Z"
      },
      {
        "member": "jim",
        "role": "contributor",
        "creation_timestamp": "2025-10-03T12:36:54.879107Z"
      }
    ],
    "status": "AlwaysOn"
  }
}

export const endpointsData = []
