<template>
  <div class="row items-center q-gutter-sm">
    <div class="text-body1 q-mb-sm">Stores</div>
    <q-space/>
    <q-btn
      color="primary"
      flat
      no-caps
      class="q-mt-sm"
      @click="addStoreRow"
      :disable="!canManageStores || !datalabAvailable || availableStoreTypes.length === 0"
    >
      <q-icon name="add" class="q-mr-sm" />
      Add Store
    </q-btn>
  </div>

  <q-banner v-if="!datalabAvailable" class="bg-orange-1 text-orange-10 q-mb-md" dense>
    Provider Datalab is not installed for this cluster.
  </q-banner>

  <q-banner v-else-if="availableStoreTypes.length === 0" class="bg-orange-1 text-orange-10 q-mb-md" dense>
    Stores are disabled for this cluster.
  </q-banner>

  <q-table
    ref="storeTable"
    class="my-sticky-header-table"
    style="height: calc(100vh - 330px)"
    :rows="myStores"
    :columns="columns"
    row-key="id"
    flat
    bordered
    :pagination="initialPagination"
    :rows-per-page-options="[0]"
  >

    <template v-slot:body-cell-type="props">
      <q-td :props="props">
        <q-select
          v-if="props.row.isNew"
          v-model="props.row.type"
          :options="availableStoreTypeOptions"
          emit-value
          map-options
          outlined
          dense
          hide-bottom-space
        />
        <span v-else>
          {{ storeTypeLabel(props.row.type) }}
        </span>
      </q-td>
    </template>

    <template v-slot:body-cell-name="props">
      <q-td :props="props">
        <q-input
          v-if="props.row.isNew"
          v-model="props.row.name"
          outlined
          dense
          hide-bottom-space
          placeholder="Store name"
          :error="!!rowErrors[props.row.id]?.name"
          @update:model-value="() => clearNameError(props.row.id)"
          @blur="() => validateStoreNamesUnique(myStores, { mode: 'row', rowId: props.row.id })"
        >
          <q-tooltip v-if="rowErrors[props.row.id]?.name" anchor="bottom middle">
            {{ rowErrors[props.row.id]?.name }}
          </q-tooltip>
          <!--
          <template v-slot:append>
            <q-btn dense flat icon="save" color="green"
                   @click="addMember">
              <q-tooltip>Save added member</q-tooltip>
            </q-btn>
          </template>
          -->
        </q-input>
        <span v-else>
          {{ props.row.name }}
        </span>
      </q-td>
    </template>

    <template v-slot:body-cell-storage="props">
      <q-td :props="props">
        <q-input
          v-if="props.row.isNew"
          v-model="props.row.storage"
          outlined
          dense
          hide-bottom-space
          placeholder="1Gi"
        />
        <span v-else>
          {{ props.row.storage || defaultStorageForType(props.row.type) }}
        </span>
      </q-td>
    </template>

    <template v-slot:body-cell-backup_storage="props">
      <q-td :props="props">
        <q-input
          v-if="props.row.isNew && props.row.type === 'database'"
          v-model="props.row.backup_storage"
          outlined
          dense
          hide-bottom-space
          placeholder="10Gi"
        />
        <span v-else-if="props.row.type === 'database'">
          {{ props.row.backup_storage || '10Gi' }}
        </span>
      </q-td>
    </template>

    <template v-slot:body-cell-actions="props">
      <q-td :props="props">
        <q-btn v-if="props.row.isNew" dense flat icon="delete" color="negative"
               @click="myStores.splice(props.rowIndex, 1)">
          <q-tooltip>Remove store</q-tooltip>
        </q-btn>
      </q-td>
    </template>

    <!--
    <template v-slot:bottom="">
      <div class="row items-center q-gutter-sm">
        <div>
          <q-btn color="primary" no-caps label="Create Members" @click="createMembers"/>
        </div>
        <q-space/>
        <div>{{ myStores.length }}</div>
      </div>
    </template>
    -->

  </q-table>

  <q-btn color="primary" no-caps label="Save" @click="createStores" style="margin-top: 5px" :disable="!canManageStores || !datalabAvailable || availableStoreTypes.length === 0 || !hasChanged" />

</template>

<script setup lang="ts">
import {computed, reactive, ref, watch} from 'vue'
import type {QTable, QTableColumn} from 'quasar'
import {useQuasar} from 'quasar'
import type {Store, StoreType} from 'src/models/models'
import {scrollToAndFocusLastRow} from 'src/services/common'
import {saveStores} from 'src/services/api'
import {useUserStore} from 'stores/userStore'

/** v-model */
const props = defineProps<{
  workspaceName: string,
  stores: Store[]
  datalabAvailable: boolean
  availableStoreTypes: StoreType[]
}>()

const $q = useQuasar()
const userStore = useUserStore()

const myStores = ref<Store[]>([])
const initialStores = ref<Store[]>([])
watch(
  () => props.stores,
  (v) => {
    const cloned = v.map(m => ({ ...m }))
    myStores.value = cloned
    initialStores.value = cloned.map(m => ({ ...m }))
  },
  {immediate: true}
)

const storeTypeOptions: { label: string, value: StoreType }[] = [
  { label: 'Database (Postgres)', value: 'database' },
  { label: 'Vector store (Qdrant)', value: 'vector' },
  { label: 'Cache (Redis)', value: 'cache' },
  { label: 'Document store (MongoDB)', value: 'document' },
]

const availableStoreTypeOptions = computed(() =>
  storeTypeOptions.filter(option => props.availableStoreTypes.includes(option.value))
)

function storeTypeLabel(type: StoreType) {
  return storeTypeOptions.find(option => option.value === type)?.label ?? type
}

function defaultStorageForType(type: StoreType) {
  return type === 'document' ? '10Gi' : '1Gi'
}

function normalizeStores(list: Store[]): string[] {
  // Create a stable, order-independent representation
  return list
    .map(m => `${m.type}:${m.name}:${m.storage ?? ''}:${m.backup_storage ?? ''}`)
    .sort()
}

const hasChanged = computed(() => {
  const a = normalizeStores(myStores.value)
  const b = normalizeStores(initialStores.value)

  if (a.length !== b.length) return true

  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return true
  }
  return false
})

const storeTable = ref<QTable | null>(null)

const columns: QTableColumn<Store>[] = [
  {
    name: 'type',
    label: 'Type',
    field: 'type',
    align: 'left'
  },
  {
    name: 'name',
    label: 'Name',
    field: 'name',
    align: 'left'
  },
  {
    name: 'storage',
    label: 'Storage',
    field: 'storage',
    align: 'left'
  },
  {
    name: 'backup_storage',
    label: 'Backup',
    field: 'backup_storage',
    align: 'left'
  },
  {
    name: 'actions',
    label: '',
    field: 'name',
    align: 'center'
  }
]

const initialPagination = {
  sortBy: '',
  descending: false,
  page: 0,
  rowsPerPage: 0
}

const canManageStores = computed(() => userStore.canManageStores)

function addStoreRow() {
  const defaultType = props.availableStoreTypes[0]
  if (!defaultType) {
    return
  }

  const newRow = {
    id: crypto.randomUUID(),
    name: '',
    type: defaultType,
    storage: defaultStorageForType(defaultType),
    backup_storage: defaultType === 'database' ? '10Gi' : undefined,
    isNew: true
  } as Store & { id: string }

  const idxNewStore = myStores.value.findIndex((m) => !m.name)
  if (idxNewStore < 0) {
    myStores.value.push(newRow)
  }

  scrollToAndFocusLastRow(storeTable.value)
}

type RowId = string
type RowErrors = { name?: string }

const rowErrors = reactive<Record<RowId, RowErrors>>({})

function setNameError(rowId: RowId, message: string) {
  rowErrors[rowId] = { ...(rowErrors[rowId] ?? {}), name: message }
}

function clearNameError(rowId: RowId) {
  const err = rowErrors[rowId]
  if (!err) return

  delete err.name
  if (Object.keys(err).length === 0) delete rowErrors[rowId]
}

function clearAllNameErrors() {
  for (const k of Object.keys(rowErrors)) {
    const id = k as unknown as RowId
    clearNameError(id)
  }
}

const hasAnyNameErrors = computed(() =>
  Object.values(rowErrors).some(e => !!e.name)
)

function normalizeName(v: string) {
  return (v ?? '').trim().toLowerCase()
}


/**
 * Validates unique store names within each store type.
 * - mode "row": validates only the given row (for blur)
 * - mode "all": validates all rows (for save)
 *
 * Returns true if validation passes for the requested scope.
 */
function validateStoreNamesUnique(
  rows: Store[],
  opts:
    | { mode: 'row', rowId: RowId}
    | { mode: 'all' }
): boolean {
  const byId = new Map<RowId, Store>(rows.map(r => [r.id, r]))

  const validateOneLocal = (row: Store): boolean => {
    clearNameError(row.id)

    const key = normalizeName(row.name)
    if (!key) return true

    const duplicate = rows.some(r => r.id !== row.id && r.type === row.type && normalizeName(r.name) === key)
    if (duplicate) {
      setNameError(row.id, 'Store name must be unique for this type.')
      return false
    }
    return true
  }

  // Uniqueness check
  if (opts.mode === 'row') {
    const row = byId.get(opts.rowId)
    if (!row) return true

    const okLocal = validateOneLocal(row)
    return okLocal;
  }

  // mode === "all"
  clearAllNameErrors()

  let okLocal = true
  for (const row of rows) {
    const ok = validateOneLocal(row)
    if (!ok) okLocal = false
  }
  if (!okLocal) return false

  return !hasAnyNameErrors.value
}



function createStores() {
  if (!canManageStores.value || !props.datalabAvailable || props.availableStoreTypes.length === 0) {
    return
  }

  const ok = validateStoreNamesUnique(myStores.value,  {mode: 'all'})
  if (!ok) {
    return
  }

  const nowIso = new Date().toISOString()

  const stores = myStores.value
    .filter(m => !!m.name && props.availableStoreTypes.includes(m.type))
    .map(m => ({
      id: m.id,
      name: m.name.trim(),
      type: m.type,
      storage: m.storage?.trim() || defaultStorageForType(m.type),
      backup_storage: m.type === 'database' ? (m.backup_storage?.trim() || '10Gi') : undefined,
      creation_timestamp: m.creation_timestamp ?? nowIso,
    }))

  saveStores(props.workspaceName, stores)
    .then(() => {
        myStores.value.forEach((store: Store) => {
          if (store.isNew) {
            store.isPending = true
          }
          store.isNew = false
        })
        initialStores.value = myStores.value.map(m => ({ ...m }))

        $q.notify({
          type: 'positive',
          message: 'Stores were successfully submitted!'
        })
      }
    )
    .catch((err) => {
      const msg = err instanceof Error ? err.message : String(err)
      $q.notify({
        type: 'negative',
        message: `Error creating stores: ${msg}`
      })
    })
}


</script>
