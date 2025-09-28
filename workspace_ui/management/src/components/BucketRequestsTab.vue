<template>
  <div class="row">
    <div class="text-body1 q-mb-sm">Bucket requests</div>
  </div>
  <q-table
    class="my-sticky-header-table"
    style="height: calc(100vh - 350px)"
    :rows="requestedBuckets"
    :columns="requestedBucketsColumns"
    row-key="id"
    bordered
    flat
    :rows-per-page-options="[0]"
    :pagination="bucketInitialPagination"
  >
    <template #body-cell-status="props">
      <q-td :props="props">
        <q-badge v-if="props.row.isPending" color="warning" outline>
          Pending
        </q-badge>
        <q-badge v-if="props.row.grant_timestamp && props.row.denied_timestamp" color="negative" outline>
          Revoked · {{ formatDate(props.row.denied_timestamp) }}
        </q-badge>
        <q-badge v-else-if="props.row.grant_timestamp" color="positive" outline>
          Granted · {{ formatDate(props.row.grant_timestamp) }}
        </q-badge>
        <q-badge v-else-if="props.row.denied_timestamp" color="negative" outline>
          Denied · {{ formatDate(props.row.denied_timestamp) }}
        </q-badge>
        <q-badge v-else color="warning" outline>
          Requested · {{ formatDate(props.row.request_timestamp) }}
        </q-badge>
      </q-td>
    </template>
    <template #body-cell-actions="props">
      <q-td :props="props" class="q-gutter-xs">
        <span v-if="!props.row.isPending">
          <span v-if="!props.row.grant_timestamp">
            <q-btn dense flat icon="key" color="positive" @click="grantBucket(props.row)">
              <q-tooltip>Grant bucket access</q-tooltip>
            </q-btn>
            <q-btn dense flat icon="key_off" color="negative" @click="denyBucket(props.row)">
              <q-tooltip>Deny bucket access</q-tooltip>
            </q-btn>
          </span>
          <q-btn v-else dense flat icon="key_off" color="negative" @click="revokeBucket(props.row)">
            <q-tooltip>Revoke bucket access</q-tooltip>
          </q-btn>
          </span>
      </q-td>
    </template>
  </q-table>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type {QTableColumn} from 'quasar';
import { useQuasar} from 'quasar'
import {QTable} from 'quasar'
import type { Bucket } from 'src/models/models'
import {formatDate} from 'src/services/common'
import {sortByRequestThenGrantDesc} from 'src/services/sorting'
import {saveBucketGrants} from 'src/services/api'

const props = defineProps<{
  workspaceName: string
  linkedBuckets: Bucket[]
}>()

const $q = useQuasar()

/*
const emit = defineEmits<{
  (e: 'update:linked-buckets', v: Bucket[]): void
}>()

 */

/*
const linkedBuckets = computed({
  get: () => props.linkedBuckets,
  set: (v) => emit('update:linked-buckets', v)
})
 */

const requestedBuckets = computed(() =>
  props.linkedBuckets
    .filter(r => r.workspace !== props.workspaceName)
    .sort(sortByRequestThenGrantDesc)
)

const bucketInitialPagination = {
  sortBy: '',
  descending: false,
  page: 0,
  rowsPerPage: 0
}

const requestedBucketsColumns: QTableColumn<Bucket>[] = [
  {name: 'bucket', label: 'Bucket', field: 'bucket', align: 'left', sortable: true},
  {name: 'workspace', label: 'Workspace', field: 'workspace', align: 'left', sortable: true},
  {name: 'permission', label: 'Permission', field: 'permission', align: 'left', sortable: true},
  {
    name: 'requested',
    label: 'Requested',
    field: 'request_timestamp',
    align: 'left',
    sortable: true,
    format: (val) => formatDate(val as string | null)   // (val, row) möglich, row hier nicht gebraucht
  },
  {
    name: 'granted',
    label: 'Granted',
    field: 'grant_timestamp',
    align: 'left',
    sortable: true,
    format: (val) => formatDate(val as string | null)
  },
  {name: 'status', label: 'Status', field: (row) => {
      if (row.grant_timestamp && row.denied_timestamp) {
        return 'Revoked'
      }
      if (row.grant_timestamp) {
        return 'Granted'
      }
      if (row.denied_timestamp) {
        return 'Denied'
      }
      return 'Requested'
    },
    align: 'left',
    },
  {name: 'actions', label: 'Actions', field: 'bucket', align: 'right'}
]

function grantBucket(row: Bucket) {
  // POST /bucket-access-requests/:id/grant
  row.grant_timestamp = new Date().toISOString()
  row.denied_timestamp = undefined
  row.isPending = true
  const bucketGrants = [row]
  saveBucketGrants(props.workspaceName, bucketGrants)
    .then(() => {
        row.request_timestamp = new Date().toISOString()
        $q.notify({
          type: 'positive',
          message: 'Bucket grant was successfully submitted!'
        })
      }
    )
    .catch((err) => {
      const msg = err instanceof Error ? err.message : String(err)
      $q.notify({
        type: 'negative',
        message: `Error granting Bucket access: ${msg}`
      })
    })

}

function revokeBucket(row: Bucket) {
  // keep row.grant_timestamp unchanged
  row.denied_timestamp = new Date().toISOString()
  row.isPending = true
  const bucketGrants = [row]
  saveBucketGrants(props.workspaceName, bucketGrants)
    .then(() => {
        row.request_timestamp = new Date().toISOString()
        $q.notify({
          type: 'positive',
          message: 'Bucket revoke was successfully submitted!'
        })
      }
    )
    .catch((err) => {
      const msg = err instanceof Error ? err.message : String(err)
      $q.notify({
        type: 'negative',
        message: `Error revoking Bucket access: ${msg}`
      })
    })
}

function denyBucket(row: Bucket) {
  row.grant_timestamp = undefined
  row.denied_timestamp = new Date().toISOString()
  row.isPending = true
  const bucketGrants = [row]
  saveBucketGrants(props.workspaceName, bucketGrants)
    .then(() => {
        row.request_timestamp = new Date().toISOString()
        $q.notify({
          type: 'positive',
          message: 'Bucket grant deny was successfully submitted!'
        })
      }
    )
    .catch((err) => {
      const msg = err instanceof Error ? err.message : String(err)
      $q.notify({
        type: 'negative',
        message: `Error grant denying Bucket access: ${msg}`
      })
    })
}

</script>
