<template>
  <!-- Extra Buckets -->
  <div class="row items-center q-gutter-sm">
    <div class="text-body1 q-mb-sm">Extra Buckets</div>
    <q-space/>
    <q-btn
      ref="btnAddExtraBucket"
      color="primary"
      flat
      no-caps
      class="q-mt-sm q-mb-lg"
      @click="addExtraBucket"
    >
      <q-icon name="add" class="q-mr-sm"/>
      Add Extra Bucket
    </q-btn>
  </div>

  <q-table
    ref="extraBucketTable"
    class="my-sticky-header-table"
    style="max-height: calc(350px)"
    :rows="myExtraBuckets"
    :columns="extraBucketsColumns"
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
        <template v-slot:append>
          <q-btn dense flat icon="save" color="green"
                 @click="createExtraBucket">
            <q-tooltip>Save added Extra Bucket</q-tooltip>
          </q-btn>
        </template>
        </q-input>
          <span v-else>
          {{ props.row.bucket }}
        </span>
      </q-td>
    </template>

    <template v-slot:body-cell-actions="props">
      <q-td :props="props">
        <q-btn v-if="props.row.isNew" dense flat icon="delete" color="negative" @click="deleteExtraBucket(props.row)">
          <q-tooltip>Delete bucket</q-tooltip>
        </q-btn>
      </q-td>
    </template>
  </q-table>

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
        <!--
        <q-btn dense flat icon="open_in_new" @click="openBucket(props.row.bucket)">
          <q-tooltip>Open bucket</q-tooltip>
        </q-btn>
        <q-btn dense flat icon="link_off" color="negative" @click="unlink(props.row)">
          <q-tooltip>Unlink</q-tooltip>
        </q-btn>
        -->
      </q-td>
    </template>
  </q-table>

</template>

<script setup lang="ts">
import {computed, ref, watch} from 'vue'
import type {QTableColumn} from 'quasar'
import {QTable, useQuasar} from 'quasar'
import type {Bucket, ExtraBucketUI} from 'src/models/models'
import {formatDate, scrollToAndFocusLastRow} from 'src/services/common'
import {sortByBucketNameAsc} from 'src/services/sorting'
import {saveExtraBuckets, saveRequestedBuckets} from 'src/services/api'

const props = defineProps<{
  workspaceName: string
  extraBuckets: ExtraBucketUI[]
  linkedBuckets: Bucket[]
}>()

/*
const emit = defineEmits<{
  (e: 'update:extra-buckets', v: ExtraBucketUI[]): void
  (e: 'update:linked-buckets', v: Bucket[]): void
  (e: 'update:show', v: boolean): void
  (e: 'update:show-all', v: boolean): void
}>()
 */

const $q = useQuasar()

const allAvailableBuckets = ref<boolean>(false)

/** local proxies for v-model */
/*
const extraBuckets = computed({
  get: () => props.extraBuckets,
  set: (v) => emit('update:extra-buckets', v)
})
const linkedBuckets = computed({
  get: () => props.linkedBuckets,
  set: (v) => emit('update:linked-buckets', v)
})
 */

const myExtraBuckets = ref<ExtraBucketUI[]>([])
watch(
  () => props.extraBuckets,
  (v) => { myExtraBuckets.value = v.map(x => ({ ...x })) },
  { immediate: true }
)

/*
const myLinkedBuckets = ref<Bucket[]>([])
watch(
  () => props.linkedBuckets,
  (v) => { myLinkedBuckets.value = v.map(x => ({ ...x })) },
  { immediate: true }
)
 */

const myLinkedBuckets = computed(() =>
  props.linkedBuckets
    .filter(r => r.workspace === props.workspaceName && (allAvailableBuckets.value || !!r.request_timestamp))
    // .sort(sortByRequestThenGrantDesc)
    .sort(sortByBucketNameAsc)
)

const extraBucketTable = ref<QTable | null>(null)
const newExtraBucketsCount = ref(0)
const btnAddExtraBucket = ref()
const newBucket = ref()

const extraBucketsColumns: QTableColumn<ExtraBucketUI>[] = [
  {
    name: 'bucket',
    label: 'Bucket',
    field: 'bucket',
    align: 'left'
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
  /*
  let top
  if (btnAddExtraBucket.value) {
    const el = btnAddExtraBucket.value?.$el
    top = el.getBoundingClientRect().top
  } else {
    top = 300
  }

   */
  const top = 55* Math.min(newExtraBucketsCount.value, 5)
//  console.log(top)
  return {
    // height: `${state.table1Height}px`,
    height: `calc(100vh - ${top}px - 500px)`
//  overflow: 'auto'
  }
})


function addExtraBucket() {
  console.log('add extra bucket')
  const idxNew = myExtraBuckets.value.findIndex((b) => !b.bucket || b.isNew)
  if (idxNew < 0) {
    myExtraBuckets.value.push({bucket: props.workspaceName + '-', isNew: true} as ExtraBucketUI)
    newExtraBucketsCount.value++
  }

  scrollToAndFocusLastRow(extraBucketTable.value)
}

function deleteExtraBucket(row: ExtraBucketUI) {
  const index = myExtraBuckets.value.findIndex(b => b.bucket === row.bucket)
  if (index !== -1) {
    myExtraBuckets.value.splice(index, 1)
    newExtraBucketsCount.value--
  }
}

function createExtraBucket() {

  newBucket.value.validate()

  if (newBucket.value.hasError) {
    return
  }

  const buckets = myExtraBuckets.value.filter(b => !!b.bucket).map(b => b.bucket)
  saveExtraBuckets(props.workspaceName, buckets)
    .then(() => {
      myExtraBuckets.value.forEach( (bucket: ExtraBucketUI) => {
          if (bucket.isNew) {
            bucket.isPending = true
          }
        bucket.isNew = false
        })
        $q.notify({
          type: 'positive',
          message: 'Extra Bucket was successfully submitted!'
        })
      }
    )
    .catch((err) => {
      const msg = err instanceof Error ? err.message : String(err)
      $q.notify({
        type: 'negative',
        message: `Error creating Extra Buckets: ${msg}`
      })
    })
}



/*
function unlink(row: Bucket) {
  // DELETE /bucket-access-requests/:id or appropriate endpoint
  // allAccess.value = allAccess.value.filter(r => r.id !== row.id)
  console.log('unlink', row)
}
 */

/*
function openBucket(bucketName: string) {
  // navigate to bucket detail view
  console.log('Open bucket', bucketName)
}
 */

function requestBucket(row: Bucket) {
  console.log('request bucket', row.bucket)
  const requestedBuckets = [row.bucket]
  saveRequestedBuckets(props.workspaceName, requestedBuckets)
    .then(() => {
        row.request_timestamp = new Date().toISOString()
        $q.notify({
          type: 'positive',
          message: 'Request for Bucket access was successfully submitted!'
        })
      }
    )
    .catch((err) => {
      const msg = err instanceof Error ? err.message : String(err)
      $q.notify({
        type: 'negative',
        message: `Error requesting Bucket access: ${msg}`
      })
    })
}

</script>
