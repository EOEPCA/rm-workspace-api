import type {Bucket} from 'src/models/models'

/** sorting */
export function sortByGrantDesc(a: Bucket, b: Bucket) {
  return (b.grant_timestamp ?? '').localeCompare(a.grant_timestamp ?? '')
}

export function sortByRequestDesc(a: Bucket, b: Bucket) {
  return (b.request_timestamp ?? '').localeCompare(a.request_timestamp ?? '')
}

export function sortByRequestThenGrantDesc(a: Bucket, b: Bucket) {
  const g = sortByRequestDesc(a, b)
  return g !== 0 ? g : sortByGrantDesc(a, b)
}

export function sortByBucketNameAsc(a: Bucket, b: Bucket) {
  return (a.bucket ?? '').localeCompare(b.bucket ?? '')
}
