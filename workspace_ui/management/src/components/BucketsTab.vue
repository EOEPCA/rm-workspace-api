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

    <template v-slot:body-cell-lifecycle_rules="props">
      <q-td :props="props">
        <div class="lifecycle-cell">
          <q-chip
            v-for="rule in props.row.lifecycle_rules || []"
            :key="rule.target"
            dense
            square
            color="primary"
            text-color="white"
          >
            {{ formatLifecycleRule(rule) }}
            <q-tooltip>{{ lifecycleRuleTooltip(rule) }}</q-tooltip>
          </q-chip>
          <q-btn
            dense
            flat
            round
            icon="playlist_add"
            :disable="!canManageBuckets"
            @click="openLifecycleDialog(props.row)"
          >
            <q-tooltip>Lifecycle rules</q-tooltip>
          </q-btn>
        </div>
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

  <q-dialog v-model="lifecycleDialogOpen">
    <q-card class="lifecycle-dialog">
      <q-card-section class="row items-center q-pb-sm">
        <div class="text-subtitle1">{{ editingBucket?.bucket }}</div>
        <q-space/>
        <q-btn flat round dense icon="close" v-close-popup>
          <q-tooltip>Close</q-tooltip>
        </q-btn>
      </q-card-section>
      <q-separator/>
      <q-card-section class="q-gutter-sm">
        <div
          v-for="rule in editingLifecycleRules"
          :key="rule.id"
          class="lifecycle-rule-row"
        >
          <q-input
            v-model="rule.target"
            dense
            outlined
            hide-bottom-space
            label="Target"
            placeholder="tmp/*"
          />
          <q-select
            v-model="rule.mode"
            dense
            outlined
            emit-value
            map-options
            :options="lifecycleModeOptions"
            label="Mode"
          />
          <q-btn-toggle
            v-model="rule.condition"
            dense
            flat
            spread
            no-caps
            toggle-color="primary"
            :options="lifecycleConditionOptions"
          />
          <q-input
            v-if="rule.condition === 'min_age'"
            v-model="rule.min_age"
            dense
            outlined
            hide-bottom-space
            label="Min age"
            placeholder="30d"
            @update:model-value="rule.at = undefined"
          />
          <q-input
            v-else
            v-model="rule.at"
            dense
            outlined
            hide-bottom-space
            label="At"
            placeholder="2026-05-05T20:00:00Z"
            @update:model-value="rule.min_age = undefined"
          />
          <q-btn dense flat round icon="delete" color="negative" @click="deleteLifecycleRule(rule.id)">
            <q-tooltip>Delete rule</q-tooltip>
          </q-btn>
        </div>
        <q-btn flat no-caps icon="add" label="Add rule" @click="addLifecycleRule" />
        <div v-if="lifecycleValidationMessage" class="text-negative text-caption">
          {{ lifecycleValidationMessage }}
        </div>
      </q-card-section>
      <q-separator/>
      <q-card-actions align="right">
        <q-btn flat no-caps label="Cancel" v-close-popup/>
        <q-btn
          color="primary"
          no-caps
          label="Apply"
          :disable="!!lifecycleValidationMessage"
          @click="applyLifecycleRules"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>

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
import type {Bucket, BucketLifecycleRule, BucketNew, BucketUI} from 'src/models/models'
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

type LifecycleCondition = 'min_age' | 'at'
type EditableLifecycleRule = BucketLifecycleRule & {
  id: string
  condition: LifecycleCondition
}

const lifecycleModeOptions = [
  {label: 'Delete', value: 'Delete'},
  {label: 'Notify', value: 'Notify'}
]

const lifecycleConditionOptions = [
  {label: 'Min age', value: 'min_age'},
  {label: 'At', value: 'at'}
]

/** local proxies for v-model */

const myBuckets = ref<BucketUI[]>([])
const initialBuckets = ref<BucketUI[]>([])
watch(
  () => props.buckets,
  (v) => {
    const cloned = cloneBuckets(v)
    myBuckets.value = cloned
    initialBuckets.value = cloneBuckets(cloned)
  },
  { immediate: true }
)

function cloneLifecycleRules(rules: BucketLifecycleRule[] | undefined): BucketLifecycleRule[] {
  return (rules ?? []).map(rule => ({ ...rule }))
}

function cloneBuckets(buckets: BucketUI[]): BucketUI[] {
  return buckets.map(bucket => ({
    ...bucket,
    lifecycle_rules: cloneLifecycleRules(bucket.lifecycle_rules)
  }))
}

function normalizeLifecycleRulesForCompare(rules: BucketLifecycleRule[] | undefined): string {
  return (rules ?? [])
    .map(rule => `${rule.target.trim()}|${rule.mode}|${rule.min_age ?? ''}|${rule.at ?? ''}`)
    .sort()
    .join(',')
}

function normalizeBuckets(list: BucketUI[]): string[] {
  return (list || [])
    .filter(b => !!b.bucket)
    .map(b => `${(b.bucket || '').trim()}|${b.discoverable ? '1' : '0'}|${normalizeLifecycleRulesForCompare(b.lifecycle_rules)}`)
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
    name: 'lifecycle_rules',
    label: 'Lifecycle rules',
    field: 'lifecycle_rules',
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
  const top = 55* Math.min(newBucketsCount.value, 5)
  return {
    height: `calc(100vh - ${top}px - 500px)`
  }
})

const canManageBuckets = computed(() => userStore.canManageBuckets)

const lifecycleDialogOpen = ref(false)
const editingBucket = ref<BucketUI | null>(null)
const editingLifecycleRules = ref<EditableLifecycleRule[]>([])

function editableLifecycleRule(rule?: BucketLifecycleRule): EditableLifecycleRule {
  return {
    id: rule?.id ?? crypto.randomUUID(),
    target: rule?.target ?? '',
    mode: rule?.mode ?? 'Delete',
    min_age: rule?.min_age,
    at: rule?.at,
    condition: rule?.at ? 'at' : 'min_age'
  }
}

function cleanLifecycleRule(rule: EditableLifecycleRule): BucketLifecycleRule {
  const target = rule.target.trim()
  const mode = rule.mode

  if (rule.condition === 'at') {
    return {
      target,
      mode,
      at: rule.at ? new Date(rule.at).toISOString() : undefined
    }
  }

  return {
    target,
    mode,
    min_age: rule.min_age?.trim()
  }
}

const lifecycleValidationMessage = computed(() => {
  const seen = new Set<string>()
  const targetPattern = /^(\*|[^*]+(\*)?)$/
  const minAgePattern = /^\+?[0-9]+[smhdw]$/

  for (const [idx, rule] of editingLifecycleRules.value.entries()) {
    const target = rule.target.trim()
    if (!target) return `Rule ${idx + 1}: target is required.`
    if (!targetPattern.test(target)) return `Rule ${idx + 1}: target must be * or end with *.`
    if (seen.has(target)) return `Rule ${idx + 1}: target must be unique.`
    seen.add(target)

    if (rule.mode !== 'Delete' && rule.mode !== 'Notify') return `Rule ${idx + 1}: mode is required.`

    if (rule.condition === 'min_age') {
      const minAge = rule.min_age?.trim() ?? ''
      if (!minAgePattern.test(minAge)) return `Rule ${idx + 1}: min age must look like 30d.`
    } else {
      const at = rule.at?.trim() ?? ''
      if (!at || Number.isNaN(Date.parse(at))) return `Rule ${idx + 1}: at must be a date-time.`
    }
  }

  return ''
})

function formatLifecycleRule(rule: BucketLifecycleRule) {
  const condition = rule.min_age ? rule.min_age : rule.at
  return `${rule.mode} ${rule.target} ${condition ?? ''}`.trim()
}

function lifecycleRuleTooltip(rule: BucketLifecycleRule) {
  if (rule.min_age) {
    return `${rule.mode} ${rule.target} after ${rule.min_age}`
  }
  return `${rule.mode} ${rule.target} at ${rule.at}`
}

function openLifecycleDialog(row: BucketUI) {
  if (!canManageBuckets.value) {
    return
  }

  editingBucket.value = row
  editingLifecycleRules.value = (row.lifecycle_rules ?? []).map(editableLifecycleRule)
  lifecycleDialogOpen.value = true
}

function addLifecycleRule() {
  editingLifecycleRules.value.push(editableLifecycleRule())
}

function deleteLifecycleRule(id: string) {
  editingLifecycleRules.value = editingLifecycleRules.value.filter(rule => rule.id !== id)
}

function applyLifecycleRules() {
  if (!editingBucket.value || lifecycleValidationMessage.value) {
    return
  }

  editingBucket.value.lifecycle_rules = editingLifecycleRules.value.map(cleanLifecycleRule)
  lifecycleDialogOpen.value = false
}

function addBucket() {
  if (!canManageBuckets.value) {
    return
  }

  const idxNew = myBuckets.value.findIndex((b) => !b.bucket || b.isNew)
  if (idxNew < 0) {
    myBuckets.value.push({
      bucket: props.workspaceName + '-',
      discoverable: false,
      lifecycle_rules: [],
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
        discoverable: !!b.discoverable,
        lifecycle_rules: cloneLifecycleRules(b.lifecycle_rules)
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
      initialBuckets.value = cloneBuckets(myBuckets.value)

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

<style scoped lang="sass">
.lifecycle-cell
  display: flex
  flex-wrap: wrap
  align-items: center
  gap: 4px
  min-width: 14rem

.lifecycle-dialog
  width: min(920px, 95vw)
  max-width: 95vw

.lifecycle-rule-row
  display: grid
  grid-template-columns: minmax(140px, 1.4fr) minmax(110px, 0.8fr) minmax(150px, 1fr) minmax(180px, 1.2fr) 36px
  gap: 8px
  align-items: start

@media (max-width: 760px)
  .lifecycle-rule-row
    grid-template-columns: 1fr
</style>
