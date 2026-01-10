<template>
  <div class="row items-center q-gutter-sm">
    <div class="text-body1 q-mb-sm">Databases</div>
    <q-space/>
    <q-btn
      color="primary"
      flat
      no-caps
      class="q-mt-sm"
      @click="addDatabaseRow"
      :disable="!canManageDatabases"
    >
      <q-icon name="add" class="q-mr-sm" />
      Add Database
    </q-btn>
  </div>

  <q-table
    ref="databaseTable"
    class="my-sticky-header-table"
    style="height: calc(100vh - 330px)"
    :rows="myDatabases"
    :columns="columns"
    row-key="id"
    flat
    bordered
    :pagination="initialPagination"
    :rows-per-page-options="[0]"
  >

    <template v-slot:body-cell-name="props">
      <q-td :props="props">
        <q-input
          v-if="props.row.isNew"
          v-model="props.row.name"
          outlined
          dense
          hide-bottom-space
          placeholder="Database name"
          :error="!!rowErrors[props.row.id]?.name"
          @update:model-value="() => clearNameError(props.row.id)"
          @blur="() => validateDatabaseNamesUnique(myDatabases, { mode: 'row', rowId: props.row.id })"
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
          v-if="canManageDatabases"
          v-model="props.row.storage"
          outlined
          dense
          hide-bottom-space
          placeholder="Database size, e.g. 1Gi"
          style="max-width: 200px"
        >
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
          {{ props.row.storage }}
        </span>
      </q-td>
    </template>

    <template v-slot:body-cell-actions="props">
      <q-td :props="props">
        <q-btn v-if="props.row.isNew" dense flat icon="delete" color="negative"
               @click="myDatabases.splice(props.rowIndex, 1)">
          <q-tooltip>Remove database</q-tooltip>
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
        <div>{{ myDatabases.length }}</div>
      </div>
    </template>
    -->

  </q-table>

  <q-btn color="primary" no-caps label="Save Members" @click="createDatabases" style="margin-top: 5px" :disable="!canManageDatabases || !hasChanged" />

</template>

<script setup lang="ts">
import {computed, reactive, ref, watch} from 'vue'
import type {QTable, QTableColumn} from 'quasar'
import {useQuasar} from 'quasar'
import type {Database} from 'src/models/models'
import {scrollToAndFocusLastRow} from 'src/services/common'
import {saveDatabases} from 'src/services/api'
import {useUserStore} from 'stores/userStore'

/** v-model */
const props = defineProps<{
  workspaceName: string,
  databases: Database[]
}>()

const $q = useQuasar()
const userStore = useUserStore()

const myDatabases = ref<Database[]>([])
const initialDatabases = ref<Database[]>([])
watch(
  () => props.databases,
  (v) => {
    const cloned = v.map(m => ({ ...m }))
    myDatabases.value = cloned
    initialDatabases.value = cloned.map(m => ({ ...m }))
  },
  {immediate: true}
)

function normalizeDatabases(list: Database[]): string[] {
  // Create a stable, order-independent representation
  return list
    .map(m => `${m.name}::${m.storage}`) // key per Database
    .sort()
}

const hasChanged = computed(() => {
  const a = normalizeDatabases(myDatabases.value)
  const b = normalizeDatabases(initialDatabases.value)

  if (a.length !== b.length) return true

  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return true
  }
  return false
})

const databaseTable = ref<QTable | null>(null)

const columns: QTableColumn<Database>[] = [
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

const canManageDatabases = computed(() => userStore.canManageDatabases)

function addDatabaseRow() {
  const newRow = {
    id: crypto.randomUUID(),
    name: '',
    storage: '',
    isNew: true
  } as Database & { id: string }

  const idxNewDatabase = myDatabases.value.findIndex((m) => !m.name)
  if (idxNewDatabase < 0) {
    myDatabases.value.push(newRow)
  }

  scrollToAndFocusLastRow(databaseTable.value)
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
 * Validates unique database names.
 * - mode "row": validates only the given row (for blur)
 * - mode "all": validates all rows (for save)
 *
 * Returns true if validation passes for the requested scope.
 */
function validateDatabaseNamesUnique(
  rows: Database[],
  opts:
    | { mode: 'row', rowId: RowId}
    | { mode: 'all' }
): boolean {
  const byId = new Map<RowId, Database>(rows.map(r => [r.id, r]))

  const validateOneLocal = (row: Database): boolean => {
    clearNameError(row.id)

    const key = normalizeName(row.name)
    if (!key) return true

    const duplicate = rows.some(r => r.id !== row.id && normalizeName(r.name) === key)
    if (duplicate) {
      setNameError(row.id, 'Database name must be unique.')
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



function createDatabases() {
  if (!canManageDatabases.value) {
    return
  }

  const ok = validateDatabaseNamesUnique(myDatabases.value,  {mode: 'all'})
  if (!ok) {
    return
  }

  const databases = myDatabases.value.filter(m => !!m.name)
  saveDatabases(props.workspaceName, databases)
    .then(() => {
        myDatabases.value.forEach((member: Database) => {
          if (member.isNew) {
            member.isPending = true
          }
          member.isNew = false
        })
        // reset initialDatabases
        initialDatabases.value = myDatabases.value.map(m => ({ ...m }))

        $q.notify({
          type: 'positive',
          message: 'Databases were successfully submitted!'
        })
      }
    )
    .catch((err) => {
      const msg = err instanceof Error ? err.message : String(err)
      $q.notify({
        type: 'negative',
        message: `Error creating databases: ${msg}`
      })
    })
}


</script>
