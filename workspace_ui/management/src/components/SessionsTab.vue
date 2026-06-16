<template>
  <div class="row items-center q-gutter-sm">
    <div class="text-body1 q-mb-sm">Sessions</div>
    <q-space/>
    <q-btn
      color="primary"
      flat
      no-caps
      class="q-mt-sm"
      @click="addSessionRow"
      :disable="!canManageSessions || !datalabAvailable || sessionLimitReached"
    >
      <q-icon name="add" class="q-mr-sm" />
      Add Session
    </q-btn>
  </div>

  <q-banner v-if="!datalabAvailable" class="bg-orange-1 text-orange-10 q-mb-md" dense>
    Provider Datalab is not installed for this cluster.
  </q-banner>

  <q-banner v-else-if="sessionLimitReached" class="bg-blue-grey-1 text-blue-grey-9 q-mb-md" dense>
    Maximum sessions reached ({{ mySessions.length }}/{{ normalizedMaxSessions }}).
  </q-banner>

  <q-table
    ref="sessionTable"
    class="my-sticky-header-table"
    style="height: calc(100vh - 330px)"
    :rows="mySessions"
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
          placeholder="session-name"
          :error="!!rowErrors[props.row.id]?.name"
          @update:model-value="() => clearNameError(props.row.id)"
          @blur="() => validateSessionNames(mySessions, {mode: 'row', rowId: props.row.id})"
        >
          <q-tooltip v-if="rowErrors[props.row.id]?.name" anchor="bottom middle">
            {{ rowErrors[props.row.id]?.name }}
          </q-tooltip>
        </q-input>
        <span v-else>
          {{ props.row.name }}
        </span>
      </q-td>
    </template>

    <template v-slot:body-cell-state="props">
      <q-td :props="props">
        <q-badge :color="props.row.state === 'started' ? 'green' : 'grey-7'">
          {{ props.row.state }}
        </q-badge>
      </q-td>
    </template>

    <template v-slot:body-cell-url="props">
      <q-td :props="props">
        <a v-if="props.row.url" :href="props.row.url" target="_blank" rel="noopener noreferrer">
          {{ props.row.url }}
        </a>
        <span v-else class="text-grey-7">-</span>
      </q-td>
    </template>

    <template v-slot:body-cell-actions="props">
      <q-td :props="props">
        <q-btn
          v-if="!props.row.isNew"
          dense
          flat
          icon="open_in_new"
          :href="sessionOpenUrl(workspaceName, props.row.name)"
          target="_blank"
          :disable="props.row.state !== 'started' || isBusy(props.row)"
        >
          <q-tooltip>Open session</q-tooltip>
        </q-btn>
        <q-btn
          v-if="!props.row.isNew && props.row.state !== 'started'"
          dense
          flat
          icon="play_arrow"
          color="positive"
          :loading="isBusy(props.row)"
          :disable="!canManageSessions || !datalabAvailable"
          @click="setState(props.row, 'started')"
        >
          <q-tooltip>Start session</q-tooltip>
        </q-btn>
        <q-btn
          v-if="!props.row.isNew && props.row.state === 'started'"
          dense
          flat
          icon="stop"
          color="warning"
          :loading="isBusy(props.row)"
          :disable="!canManageSessions || !datalabAvailable"
          @click="setState(props.row, 'stopped')"
        >
          <q-tooltip>Stop session</q-tooltip>
        </q-btn>
        <q-btn
          dense
          flat
          icon="delete"
          color="negative"
          :disable="(!props.row.isNew && (!canManageSessions || !datalabAvailable)) || isBusy(props.row)"
          @click="removeSession(props.row)"
        >
          <q-tooltip>Remove session</q-tooltip>
        </q-btn>
      </q-td>
    </template>
  </q-table>

  <q-btn
    color="primary"
    no-caps
    label="Save"
    @click="createSessions"
    style="margin-top: 5px"
    :disable="!canManageSessions || !datalabAvailable || !hasNewSessions || exceedsSessionLimit"
  />

  <q-dialog v-model="removeDialogOpen" persistent>
    <q-card style="width: min(480px, 92vw)">
      <q-card-section>
        <div class="text-h6">Remove session</div>
      </q-card-section>

      <q-card-section class="q-pt-none">
        <p class="q-mt-none">
          Data associated with this session will be lost.
        </p>
        <q-input
          v-model="removeConfirmationName"
          outlined
          dense
          autofocus
          label="Session name"
          :hint="`Type ${pendingRemovalSession?.name ?? ''} to confirm removal.`"
          @keyup.enter="confirmRemoveSession"
        />
      </q-card-section>

      <q-card-actions align="right">
        <q-btn flat label="Cancel" color="primary" @click="cancelRemoveSession" />
        <q-btn
          unelevated
          label="Remove"
          color="negative"
          :disable="!removeConfirmationMatches"
          :loading="!!pendingRemovalSession && isBusy(pendingRemovalSession)"
          @click="confirmRemoveSession"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import {computed, reactive, ref, watch} from 'vue'
import type {QTable, QTableColumn} from 'quasar'
import {useQuasar} from 'quasar'
import type {SessionState, WorkspaceSession} from 'src/models/models'
import {createSession, deleteSession, sessionOpenUrl, updateSessionState} from 'src/services/api'
import {scrollToAndFocusLastRow} from 'src/services/common'
import {useUserStore} from 'stores/userStore'

type SessionRow = WorkspaceSession & { id: string }
type RowErrors = { name?: string }

const props = defineProps<{
  workspaceName: string
  sessions: WorkspaceSession[]
  datalabAvailable: boolean
  maxSessions: number
}>()

const emit = defineEmits<{
  'update:sessions': [sessions: WorkspaceSession[]]
}>()

const $q = useQuasar()
const userStore = useUserStore()

const mySessions = ref<SessionRow[]>([])
const sessionTable = ref<QTable | null>(null)
const rowErrors = reactive<Record<string, RowErrors>>({})
const busyRowIds = ref<string[]>([])
const removeDialogOpen = ref(false)
const pendingRemovalSession = ref<SessionRow | null>(null)
const removeConfirmationName = ref('')

watch(
  () => props.sessions,
  (v) => {
    mySessions.value = v.map(s => ({
      ...s,
      id: s.id ?? crypto.randomUUID(),
      state: s.state ?? 'stopped'
    }))
  },
  {immediate: true}
)

const columns: QTableColumn<SessionRow>[] = [
  {
    name: 'name',
    label: 'Name',
    field: 'name',
    align: 'left'
  },
  {
    name: 'state',
    label: 'State',
    field: 'state',
    align: 'left'
  },
  {
    name: 'url',
    label: 'URL',
    field: 'url',
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

const sessionNamePattern = /^[a-z0-9]([-a-z0-9]*[a-z0-9])?$/
const canManageSessions = computed(() => userStore.canManageSessions)
const hasNewSessions = computed(() => mySessions.value.some(session => session.isNew))
const normalizedMaxSessions = computed(() => Math.max(0, props.maxSessions ?? 3))
const sessionLimitReached = computed(() => mySessions.value.length >= normalizedMaxSessions.value)
const exceedsSessionLimit = computed(() => mySessions.value.length > normalizedMaxSessions.value)
const removeConfirmationMatches = computed(() => removeConfirmationName.value === pendingRemovalSession.value?.name)

function normalizeName(v: string) {
  return (v ?? '').trim().toLowerCase()
}

function clearNameError(rowId: string) {
  const err = rowErrors[rowId]
  if (!err) return

  delete err.name
  if (Object.keys(err).length === 0) delete rowErrors[rowId]
}

function setNameError(rowId: string, message: string) {
  rowErrors[rowId] = {...(rowErrors[rowId] ?? {}), name: message}
}

function clearAllNameErrors() {
  for (const rowId of Object.keys(rowErrors)) {
    clearNameError(rowId)
  }
}

function validateOne(row: SessionRow, rows: SessionRow[]) {
  clearNameError(row.id)

  const name = normalizeName(row.name)
  if (!name) {
    setNameError(row.id, 'Session name is required.')
    return false
  }
  if (!sessionNamePattern.test(name)) {
    setNameError(row.id, 'Use lowercase letters, numbers, and hyphens.')
    return false
  }
  if (rows.some(r => r.id !== row.id && normalizeName(r.name) === name)) {
    setNameError(row.id, 'Session name must be unique.')
    return false
  }

  return true
}

function validateSessionNames(
  rows: SessionRow[],
  opts:
    | { mode: 'row', rowId: string }
    | { mode: 'all' }
) {
  if (opts.mode === 'row') {
    const row = rows.find(r => r.id === opts.rowId)
    return row ? validateOne(row, rows) : true
  }

  clearAllNameErrors()
  return rows.every(row => validateOne(row, rows))
}

function emitSessions() {
  emit('update:sessions', mySessions.value.map(session => ({...session})))
}

function addSessionRow() {
  if (!canManageSessions.value || !props.datalabAvailable || sessionLimitReached.value) {
    return
  }

  const idxNewSession = mySessions.value.findIndex(session => session.isNew && !session.name)
  if (idxNewSession < 0) {
    mySessions.value.push({
      id: crypto.randomUUID(),
      name: '',
      state: 'stopped',
      ready: false,
      isNew: true
    })
  }

  scrollToAndFocusLastRow(sessionTable.value)
}

function isBusy(row: SessionRow) {
  return busyRowIds.value.includes(row.id)
}

function setBusy(row: SessionRow, busy: boolean) {
  if (busy) {
    busyRowIds.value = Array.from(new Set([...busyRowIds.value, row.id]))
    return
  }
  busyRowIds.value = busyRowIds.value.filter(rowId => rowId !== row.id)
}

function createSessions() {
  if (!canManageSessions.value || !props.datalabAvailable || exceedsSessionLimit.value) {
    return
  }

  const rowsToCreate = mySessions.value.filter(session => session.isNew)
  if (rowsToCreate.length === 0 || !validateSessionNames(mySessions.value, {mode: 'all'})) {
    return
  }

  Promise.all(
    rowsToCreate.map(row => createSession(props.workspaceName, {
      name: normalizeName(row.name),
      state: row.state
    }).then(created => {
      Object.assign(row, {
        ...created,
        id: row.id,
        isNew: false,
        isPending: true
      })
    }))
  )
    .then(() => {
      emitSessions()
      $q.notify({
        type: 'positive',
        message: 'Sessions were successfully submitted!'
      })
    })
    .catch((err) => {
      const msg = err instanceof Error ? err.message : String(err)
      $q.notify({
        type: 'negative',
        message: `Error creating sessions: ${msg}`
      })
    })
}

function setState(row: SessionRow, state: SessionState) {
  if (!canManageSessions.value || !props.datalabAvailable || row.isNew) {
    return
  }

  setBusy(row, true)
  updateSessionState(props.workspaceName, row.name, state)
    .then(updated => {
      Object.assign(row, {
        ...updated,
        id: row.id,
        isNew: false,
        isPending: true,
        url: state === 'stopped' ? undefined : updated.url
      })
      emitSessions()
      $q.notify({
        type: 'positive',
        message: state === 'started' ? 'Session start was submitted!' : 'Session stop was submitted!'
      })
    })
    .catch((err) => {
      const msg = err instanceof Error ? err.message : String(err)
      $q.notify({
        type: 'negative',
        message: `Error updating session: ${msg}`
      })
    })
    .finally(() => {
      setBusy(row, false)
    })
}

function removeSession(row: SessionRow) {
  if (row.isNew) {
    mySessions.value = mySessions.value.filter(session => session.id !== row.id)
    clearNameError(row.id)
    return
  }

  if (!canManageSessions.value || !props.datalabAvailable) {
    return
  }

  pendingRemovalSession.value = row
  removeConfirmationName.value = ''
  removeDialogOpen.value = true
}

function cancelRemoveSession() {
  if (pendingRemovalSession.value && isBusy(pendingRemovalSession.value)) {
    return
  }

  removeDialogOpen.value = false
  pendingRemovalSession.value = null
  removeConfirmationName.value = ''
}

function confirmRemoveSession() {
  const row = pendingRemovalSession.value
  if (!row || !removeConfirmationMatches.value) {
    return
  }

  setBusy(row, true)
  deleteSession(props.workspaceName, row.name)
    .then(() => {
      mySessions.value = mySessions.value.filter(session => session.id !== row.id)
      emitSessions()
      removeDialogOpen.value = false
      pendingRemovalSession.value = null
      removeConfirmationName.value = ''
      $q.notify({
        type: 'positive',
        message: 'Session was removed!'
      })
    })
    .catch((err) => {
      const msg = err instanceof Error ? err.message : String(err)
      $q.notify({
        type: 'negative',
        message: `Error removing session: ${msg}`
      })
    })
    .finally(() => {
      setBusy(row, false)
    })
}
</script>
