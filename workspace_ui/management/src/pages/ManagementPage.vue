<template>
  <div class="q-pa-md" style="max-width: 1000px; margin: 0 auto;">
    <q-card>
      <q-card-section>

        <!-- Message -->
        <q-banner
          v-if="message"
          :class="isError ? 'bg-red-1 text-negative' : 'bg-green-1 text-positive'"
          dense
          rounded
          class="q-mb-md"
        >
          <div class="row items-center no-wrap">
            <q-icon :name="isError ? 'error' : 'check_circle'" class="q-mr-sm"/>
            <div class="col">{{ displayMessage }}</div>
          </div>
        </q-banner>

        <!-- Loading -->
        <div v-if="loading" class="row justify-center q-my-md">
          <q-spinner size="28px"/>
        </div>

        <!-- Form -->
        <q-form v-if="!loading && form.name" @submit.prevent="submit">
          <!-- Tabs header -->
          <q-tabs
            v-model="activeTab"
            class="text-primary q-mb-md"
            align="justify"
            dense
            outside-arrows
            mobile-arrows
          >
            <q-tab name="members" label="Members" :alert="form.memberships.length === 0"/>
            <q-tab name="buckets" label="Buckets"/>
          </q-tabs>

          <q-separator/>

          <!-- Tabs content -->
          <q-tab-panels v-model="activeTab" animated>
            <!-- MEMBERS TAB -->
            <q-tab-panel name="members">
              <!--
              <div class="text-body1 q-mb-sm">Members</div>
              -->

              <q-table
                ref="memberTable"
                class="my-sticky-header-table"
                :rows="form.memberships"
                :columns="memberColumns"
                row-key="id"
                flat
                bordered
                :pagination="memberInitialPagination"
                :rows-per-page-options="[0]"
              >

                <template v-slot:body-cell-member="props">
                  <q-td :props="props">
                    <q-input
                      v-if="props.row.isNew"
                      v-model="props.row.member"
                      outlined
                      dense
                      hide-bottom-space
                      placeholder="Member name"
                    />
                    <span v-else>
                      {{ props.row.member }}
                    </span>
                  </q-td>
                </template>

                <!--
                <template v-slot:body-cell-actions="props">
                  <q-td :props="props">
                    <q-btn v-if="props.row.role !== 'owner'" dense flat icon="delete" color="negative" @click="form.memberships.splice(props.rowIndex, 1)">
                      <q-tooltip>Remove member</q-tooltip>
                    </q-btn>
                  </q-td>
                </template>
                -->
              </q-table>

              <q-btn
                color="primary"
                flat
                no-caps
                class="q-mt-sm"
                @click="addMember"
              >
                <q-icon name="add" class="q-mr-sm"/>
                Add Member
              </q-btn>
            </q-tab-panel>

            <!-- BUCKETS TAB -->
            <q-tab-panel name="buckets">
              <!-- Extra Buckets -->
              <div class="text-body1 q-mb-sm">Extra Buckets</div>
              <div
                v-for="(bucket, index) in form.extra_buckets"
                :key="'extra-bucket-' + index"
                class="row items-center q-col-gutter-sm q-mb-xs"
              >
                <div class="col">
                  <q-input
                    v-model="form.extra_buckets[index]"
                    outlined
                    dense
                    hide-bottom-space
                    placeholder="workspace-name-extra"
                  />
                </div>
                <div class="col-auto">
                  <q-btn
                    flat
                    round
                    dense
                    icon="delete"
                    color="negative"
                    @click="form.extra_buckets.splice(index, 1)"
                  />
                </div>
              </div>
              <q-btn
                color="primary"
                flat
                no-caps
                class="q-mt-sm q-mb-lg"
                @click="form.extra_buckets.push('')"
              >
                <q-icon name="add" class="q-mr-sm"/>
                Add Extra Bucket
              </q-btn>

              <q-separator class="q-my-md"/>

              <!-- Linked Buckets -->
              <div class="text-body1 q-mb-sm">Linked Buckets</div>
              <q-table
                :rows="linkedRows"
                :columns="linkedColumns"
                row-key="id"
                flat
                :loading="loading"
                :rows-per-page-options="[10,25,50]"
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
                    <q-btn dense flat icon="open_in_new" @click="openBucket(props.row.bucket)">
                      <q-tooltip>Open bucket</q-tooltip>
                    </q-btn>
                    <q-btn dense flat icon="link_off" color="negative" @click="unlink(props.row)">
                      <q-tooltip>Unlink</q-tooltip>
                    </q-btn>
                  </q-td>
                </template>
              </q-table>

            </q-tab-panel>
          </q-tab-panels>

          <q-separator class="q-my-md"/>

          <q-btn type="submit" color="primary" unelevated no-caps label="Save Changes"/>
        </q-form>
      </q-card-section>
    </q-card>
  </div>
</template>

<script setup lang="ts">
import {computed, ref, nextTick} from 'vue'
import axios from 'axios'
import type {Bucket, Membership, WorkspaceEdit, WorkspaceEditUI} from 'src/models/models'
import {useLuigiWorkspace} from 'src/composables/useLuigi'
import {useQuasar} from 'quasar'
import type {QTableColumn} from 'quasar'
// import formatDate = date.formatDate
const $q = useQuasar()

/** ---- State ---- */
const message = ref<string>('')

const form = ref<WorkspaceEditUI>({
  name: '',
  memberships: [],
  extra_buckets: [],
  linked_buckets: []
})

/** Tabs */
const activeTab = ref<'members' | 'buckets'>('members')

/** ---- UI helpers ---- */
const isError = computed(() => message.value.startsWith('Error:'))
const displayMessage = computed(() =>
  isError.value ? message.value.substring(7) : message.value
)

function formatDate(iso?: string | null): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    return d.toLocaleString()
  } catch {
    return iso ?? '—'
  }
}

function sortByGrantDesc(a: Bucket, b: Bucket) {
  return (b.grant_timestamp ?? '').localeCompare(a.grant_timestamp ?? '')
}

function sortByRequestDesc(a: Bucket, b: Bucket) {
  return (b.request_timestamp ?? '').localeCompare(a.request_timestamp ?? '')
}

function sortByGrantThenRequestDesc(a: Bucket, b: Bucket) {
  const g = sortByGrantDesc(a, b)
  if (g !== 0) return g
  return sortByRequestDesc(a, b)
}

const {loading} = useLuigiWorkspace({
  onReady: (ctx) => {
    if (ctx && ctx.workspace) {
      const ws = ctx.workspace
      if (ws.name) {
        message.value = `Using pre-loaded data for workspace: ${ws.name} (${ws.version})`
        form.value = {
          name: ws.name,
          memberships: (ctx.memberships ?? []).map(m => ({...m, id: crypto.randomUUID(), isNew: false})),
          extra_buckets:
            ws.storage?.buckets?.filter((b) => b !== ws.name && b.startsWith(ws.name)) ?? [],
          // linked_buckets: ws.storage?.buckets?.filter((b) => !b.startsWith(ws.name)) ?? [],
          linked_buckets: ctx.bucketAccessRequests ?? []
        }
      } else {
        message.value = 'Workspace Data not provided.'
      }
    }
  }
})

const memberColumns: QTableColumn<Membership>[] = [
  {
    name: 'member',
    label: 'Member',
    field: 'member',
    align: 'left'
  },
  {
    name: 'role',
    label: 'Role',
    field: 'role',
    align: 'left'
  },
  {
    name: 'creation_timestamp',
    label: 'Created',
    field: 'creation_timestamp',
    align: 'left',
    format: (val) => formatDate(val as string | null)
  },
  /*
  {
    name: 'actions',
    label: '',
    field: 'role',
    align: 'center'
  }

   */
]

const memberTable = ref()

const memberInitialPagination = {
  sortBy: '',
  descending: false,
  page: 0,
  rowsPerPage: 0,
}

function addMember() {
  const newRow = {
    id: crypto.randomUUID(),
    member: '',
    role: 'contributor',
    isNew: true
  } as Membership & { id: string }

  form.value.memberships.push(newRow)

  // Wait for DOM update, then scroll to the new row
  nextTick().then(() => {
    const tableEl = memberTable.value?.$el as HTMLElement | undefined
    if (tableEl) {
      const rows = tableEl.querySelectorAll('tbody tr')
      const lastRow = rows[rows.length - 1] as HTMLElement | undefined
      lastRow?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }).catch(err => {
    console.error('nextTick failed:', err)
  })
}


const linkedRows = computed(() =>
  form.value.linked_buckets
    .filter(r => r.workspace === form.value.name)
    .sort(sortByGrantThenRequestDesc)
)

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

function unlink(row: Bucket) {
  // DELETE /bucket-access-requests/:id or appropriate endpoint
  // allAccess.value = allAccess.value.filter(r => r.id !== row.id)
  console.log('unlink', row)
}

/*
function grant (row: BucketAccess) {
  // POST /bucket-access-requests/:id/grant
  row.grant_timestamp = new Date().toISOString()
}
function deny (row: BucketAccess) {
  // POST /bucket-access-requests/:id/deny (or delete)
  allAccess.value = allAccess.value.filter(r => r.id !== row.id)
}

 */
function openBucket(bucketName: string) {
  // navigate to bucket detail view
  console.log('Open bucket', bucketName)
}

/** ---- Submit ---- */
const submit = async () => {
  const workspaceName = form.value.name
  if (!workspaceName) {
    message.value = 'Error: Workspace name is missing. Cannot save.'
    return
  }

  const invalidBuckets = form.value.extra_buckets.filter(
    (b) => b === workspaceName || !b.startsWith(workspaceName)
  )

  if (invalidBuckets.length > 0) {
    message.value = `Error: The following bucket names must start with '${workspaceName}': ${invalidBuckets.join(', ')}`
    activeTab.value = 'buckets'
    return
  }

  const workspaceEdit = {
    name: workspaceName,
    members: (form.value.memberships ?? []).filter(m => !!m.member).map(m => m.member),
    extra_buckets: form.value.extra_buckets
//    linked_buckets: form.value.linked_buckets,
  } as WorkspaceEdit

  try {
    await axios.put(`/workspaces/${encodeURIComponent(workspaceName)}`, workspaceEdit)
    $q.notify({
      type: 'positive',
      message: 'Workspace updated successfully!'
    })
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    $q.notify({
      type: 'negative',
      message: `Error saving workspace: ${msg}`
    })
  }
}
</script>

<style lang="sass">
.my-sticky-header-table
  --hdr1: 48px    /* normale Header-Zeile */

  height: calc(100vh - 350px)

  .q-table__top,
  .q-table__bottom,
  thead tr th
    background-color: white

  /* beide Header-Zeilen sticky machen */
  thead tr th
    position: sticky
    z-index: 2

  /* 1. Zeile (Standard-Header) ganz oben */
  thead tr:first-child th
    top: 0
    z-index: 3

  &.q-table--loading thead tr:last-child th
    top: calc(var(--hdr1))

  tbody
    scroll-margin-top: calc(var(--hdr1))
</style>

<style lang="sass" scoped>
.q-page
  display: flex
  flex-direction: column

.toolbar
  padding: 0px

.showAll
  background-color: gray /* Example pressed background color */
  box-shadow: inset 0 3px 5px rgba(0, 0, 0, 0.2) /* Simulate pressed effect */
  transform: translateY(2px) /* Slight move down to mimic a pressed state */

.textField
  max-width: 300px
</style>
