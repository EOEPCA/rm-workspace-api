<template>
  <!-- Buckets -->
  <div class="row items-center q-gutter-sm">
    <div class="text-body1 q-mb-sm">Own Buckets</div>
    <q-space/>
    <q-btn
      ref="btnAddBucket"
      color="primary"
      flat
      no-caps
      class="q-mt-sm q-mb-lg"
      @click="addBucket"
      :disable="!canManageBuckets"
    >
      <q-icon name="add" class="q-mr-sm"/>
      Add Bucket
    </q-btn>
  </div>

  <q-table
    ref="bucketTable"
    class="my-sticky-header-table"
    style="max-height: calc(350px)"
    :rows="myBuckets"
    :columns="bucketsColumns"
    row-key="id"
    flat
    bordered
    :pagination="bucketInitialPagination"
    :rows-per-page-options="[0]"
  >

    <template v-slot:body-cell-bucket="props">
      <q-td :props="props">
        <q-input
          ref="newBucket"
          v-if="props.row.isNew"
          v-model="props.row.bucket"
          outlined
          dense
          hide-bottom-space
          placeholder="Bucket name"
          :rules="[val => !!val || 'Name is required',
            val => val.startsWith(workspaceName) || 'Name must start with ' + workspaceName,
            val => (val !== workspaceName && val != workspaceName + '-') || 'Name must be different from ' + workspaceName]"
        >
        </q-input>
        <span v-else>
          {{ props.row.bucket }}
        </span>
      </q-td>
    </template>

    <template v-slot:body-cell-discoverable="props">
      <q-td :props="props" class="text-center">
        <q-toggle
          v-model="props.row.discoverable"
          dense
          :disable="!props.row.isNew || !canManageBuckets"
        />
      </q-td>
    </template>

    <template v-slot:body-cell-actions="props">
      <q-td :props="props">
        <q-btn v-if="props.row.isNew" dense flat icon="delete" color="negative" @click="deleteBucket(props.row)">
          <q-tooltip>Delete bucket</q-tooltip>
        </q-btn>
      </q-td>
    </template>

  </q-table>

  <q-btn color="primary" no-caps label="Save" @click="createBuckets" style="margin-top: 5px" :disable="!canManageBuckets || !hasChanged" />

  <q-separator class="q-my-md"/>

  <!-- Linked Buckets -->
  <div class="row">
    <div class="text-body1 q-mb-sm">Linked Buckets</div>
    <q-space/>
    <q-toggle
      v-model="allAvailableBuckets"
      label="Show all available buckets"
    />
  </div>
  <q-table
    class="my-sticky-header-table"
    :style="linkedBucketStyle"
    :rows="myLinkedBuckets"
    :columns="linkedColumns"
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
        <q-badge v-else-if="props.row.denied_timestamp" color="negative" outline>
          Denied · {{ formatDate(props.row.denied_timestamp) }}
        </q-badge>
        <q-badge v-else-if="props.row.request_timestamp" color="warning" outline>
          Requested · {{ formatDate(props.row.request_timestamp) }}
        </q-badge>
      </q-td>
    </template>
    <template #body-cell-actions="props">
      <q-td :props="props" class="q-gutter-xs">
        <q-btn v-if="!props.row.request_timestamp" dense flat icon="key" :disable="!!props.row.request_timestamp"
               @click="requestBucket(props.row)">
          <q-tooltip>Request bucket access</q-tooltip>
        </q-btn>
      </q-td>
    </template>
  </q-table>

</template>

<script setup lang="ts">
import {computed, ref, watch} from 'vue'
import type {QTableColumn} from 'quasar'
import {QTable, useQuasar} from 'quasar'
import type {Bucket, BucketNew, BucketUI} from 'src/models/models'
import {formatDate, scrollToAndFocusLastRow} from 'src/services/common'
import {sortByBucketNameAsc} from 'src/services/sorting'
import {saveBuckets, saveRequestedBuckets} from 'src/services/api'
import {useUserStore} from 'stores/userStore'

const props = defineProps<{
  workspaceName: string
  buckets: BucketUI[]
  linkedBuckets: Bucket[]
}>()

const $q = useQuasar()
const userStore = useUserStore()

const allAvailableBuckets = ref<boolean>(false)

/** local proxies for v-model */

const myBuckets = ref<BucketUI[]>([])
const initialBuckets = ref<BucketUI[]>([])
watch(
  () => props.buckets,
  (v) => {
    const cloned = v.map(x => ({ ...x }))
    myBuckets.value = cloned
    initialBuckets.value = cloned.map(x => ({ ...x }))
  },
  { immediate: true }
)

function normalizeBuckets(list: BucketUI[]): string[] {
  return (list || [])
    .filter(b => !!b.bucket)
    .map(b => `${(b.bucket || '').trim()}|${b.discoverable ? '1' : '0'}`)
    .sort()
}

const hasChanged = computed(() => {
  const a = normalizeBuckets(myBuckets.value)
  const b = normalizeBuckets(initialBuckets.value)

  if (a.length !== b.length) return true

  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return true
  }
  return false
})

const myLinkedBuckets = computed(() =>
  props.linkedBuckets
    .filter(r => r.workspace === props.workspaceName && (allAvailableBuckets.value || !!r.request_timestamp))
    // .sort(sortByRequestThenGrantDesc)
    .sort(sortByBucketNameAsc)
)

const bucketTable = ref<QTable | null>(null)
const newBucketsCount = ref(0)
const btnAddBucket = ref()
const newBucket = ref()

const bucketsColumns: QTableColumn<BucketUI>[] = [
  {
    name: 'bucket',
    label: 'Bucket',
    field: 'bucket',
    align: 'left'
  },
  {
    name: 'discoverable',
    label: 'Discoverable',
    field: 'discoverable',
    align: 'center'
  },
  {
    name: 'requests',
    label: 'Requests',
    field: 'requests',
    align: 'right'
  },
  {
    name: 'grants',
    label: 'Grants',
    field: 'grants',
    align: 'right'
  },
  {
    name: 'status',
    label: 'Status',
    field: (row) => row.isPending ? 'Pending' : '',
    align: 'center'
  },
  {
    name: 'actions',
    label: 'Actions',
    field: 'bucket',
    align: 'center'
  }
]

const linkedColumns: QTableColumn<Bucket>[] = [
  {name: 'bucket', label: 'Bucket', field: 'bucket', align: 'left', sortable: true},
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

const bucketInitialPagination = {
  sortBy: '',
  descending: false,
  page: 0,
  rowsPerPage: 0
}

const linkedBucketStyle = computed(() => {
  const top = 55* Math.min(newBucketsCount.value, 5)
  return {
    height: `calc(100vh - ${top}px - 500px)`
  }
})

const canManageBuckets = computed(() => userStore.canManageBuckets)
function addBucket() {
  if (!canManageBuckets.value) {
    return
  }

  const idxNew = myBuckets.value.findIndex((b) => !b.bucket || b.isNew)
  if (idxNew < 0) {
    myBuckets.value.push({
      bucket: props.workspaceName + '-',
      discoverable: false,
      requests: 0,
      grants: 0,
      isNew: true
    } as BucketUI)
    newBucketsCount.value++
  }

  scrollToAndFocusLastRow(bucketTable.value)
}

function deleteBucket(row: BucketUI) {
  if (!canManageBuckets.value) {
    return
  }

  const index = myBuckets.value.findIndex(b => b.bucket === row.bucket)
  if (index !== -1) {
    myBuckets.value.splice(index, 1)
    newBucketsCount.value--
  }
}

function createBuckets() {
  if (!canManageBuckets.value) {
    return
  }

  newBucket.value?.validate?.()
  if (newBucket.value?.hasError) {
    return
  }

  const nowIso = new Date().toISOString()

  const buckets: BucketNew[] = myBuckets.value
    .filter(b => !!b.bucket)
    .map(b => {
      const out: BucketNew = {
        name: (b.bucket || '').trim(),
        discoverable: !!b.discoverable
      }
      if (b.isNew) {
        out.creation_timestamp = nowIso
      }
      return out
    })

  saveBuckets(props.workspaceName, buckets)
    .then(() => {
      myBuckets.value.forEach( (bucket: BucketUI) => {
        if (bucket.isNew) {
          bucket.isPending = true
        }
        bucket.isNew = false
      })
      initialBuckets.value = myBuckets.value.map(b => ({ ...b }))

      $q.notify({
        type: 'positive',
        message: 'Buckets were successfully submitted!'
      })
    })
    .catch((err) => {
      const msg = err instanceof Error ? err.message : String(err)
      $q.notify({
        type: 'negative',
        message: `Error creating Buckets: ${msg}`
      })
    })
}

function requestBucket(row: Bucket) {
  row.request_timestamp = new Date().toISOString()
  const requestedBuckets = [row]
  saveRequestedBuckets(props.workspaceName, requestedBuckets)
    .then(() => {
      $q.notify({
        type: 'positive',
        message: 'Request for Bucket access was successfully submitted!'
      })
    })
    .catch((err) => {
      row.request_timestamp = undefined
      const msg = err instanceof Error ? err.message : String(err)
      $q.notify({
        type: 'negative',
        message: `Error requesting Bucket access: ${msg}`
      })
    })
}

</script>
