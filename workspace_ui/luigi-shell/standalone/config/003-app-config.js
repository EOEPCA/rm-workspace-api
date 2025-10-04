export const workspaceData =
{
  "name": "s-jane",
  "creation_timestamp": "2025-10-03T06:52:00Z",
  "version": "5091111869",
  "status": "ready",
  "storage": {
    "buckets": [],
    "credentials": {
      "bucketname": "",
      "access": "REDACTED",
      "secret": "REDACTED",
      "endpoint": "https://endpoint-kalpha",
      "region": "region-kalpha"
    },
    "bucket_access_requests": [
      {
        "workspace": "s-jane",
        "bucket": "s-john",
        "permission": "WriteOnly",
        "request_timestamp": "2025-09-29T10:28:00Z",
        "denied_timestamp": "2025-09-29T10:28:00Z"
      },
      {
        "workspace": "s-jane",
        "bucket": "s-jeff-shared",
        "permission": "ReadWrite"
      },
      {
        "workspace": "s-jane",
        "bucket": "s-joe",
        "permission": "ReadWrite"
      }
    ]
  },
  "datalab": {
    "memberships": [
      {
        "member": "jane",
        "role": "owner",
        "creation_timestamp": "2025-10-03T12:37:10.130716Z"
      }
    ],
    "status": "AlwaysOn"
  }
}

export const endpointsData = []
