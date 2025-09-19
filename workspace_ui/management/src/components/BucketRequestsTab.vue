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
        <q-badge v-if="props.row.grant_timestamp" color="positive" outline>
          Granted · {{ formatDate(props.row.grant_timestamp) }}
        </q-badge>
        <q-badge v-else color="warning" outline>
          Requested · {{ formatDate(props.row.request_timestamp) }}
        </q-badge>
      </q-td>
    </template>
    <template #body-cell-actions="props">
      <q-td :props="props" class="q-gutter-xs">
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
      </q-td>
    </template>
  </q-table>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { QTableColumn} from 'quasar';
import {QTable} from 'quasar'
import type { Bucket } from 'src/models/models'
import {formatDate} from 'src/services/common'
import {sortByRequestThenGrantDesc} from 'src/services/sorting'

const props = defineProps<{
  workspaceName: string
  linkedBuckets: Bucket[]
}>()

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
  {name: 'status', label: 'Status', field: (row) => row.grant_timestamp ? 'Granted' : 'Requested', align: 'left'},
  {name: 'actions', label: 'Actions', field: 'bucket', align: 'right'}
]

function grantBucket(row: Bucket) {
  // POST /bucket-access-requests/:id/grant
  row.grant_timestamp = new Date().toISOString()
}

function revokeBucket(row: Bucket) {
  // POST /bucket-access-requests/:id/deny (or delete)
  row.grant_timestamp = ''
}

function denyBucket(row: Bucket) {
  console.log('Deny ', row)
  // POST /bucket-access-requests/:id/deny (or delete)
/*
  const idx = linkedBuckets.value.findIndex(r => r.bucket === row.bucket && r.workspace === row.workspace)
  if (idx >= 0) linkedBuckets.value.splice(idx, 1)

 */
}

</script>
