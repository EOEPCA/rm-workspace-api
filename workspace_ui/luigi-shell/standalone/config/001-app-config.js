export const workspaceData =
{
  "name": "s-joe",
  "creation_timestamp": "2025-10-03T06:52:00Z",
  "version": "5091113180",
  "status": "ready",
  "storage": {
    "buckets": [
      "s-joe"
    ],
    "credentials": {
      "bucketname": "s-joe",
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
        "workspace": "s-john",
        "bucket": "s-joe",
        "permission": "ReadWrite",
        "request_timestamp": "2025-09-29T10:25:00Z"
      },
      {
        "workspace": "s-joe",
        "bucket": "s-john",
        "permission": "ReadWrite"
      }
    ]
  },
  "datalab": {
    "memberships": [
      {
        "member": "joe",
        "role": "owner",
        "creation_timestamp": "2025-10-03T12:36:13.232155Z"
      }
    ],
    "status": "Disabled"
  }
}

export const endpointsData = []
