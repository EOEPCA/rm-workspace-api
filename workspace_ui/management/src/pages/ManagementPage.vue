<template>
  <div class="q-pa-md" style="min-width: 1000px; max-width: calc(80vw); margin: 0 auto;">
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
            <q-tab name="bucketRequests" label="Requested Buckets"/>
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
                style="height: calc(100vh - 330px)"
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
              <q-table
                ref="extraBucketTable"
                class="my-sticky-header-table"
                style="max-height: calc(400px)"
                :rows="form.extra_buckets"
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
                      v-if="props.row.isNew"
                      v-model="props.row.bucket"
                      outlined
                      dense
                      hide-bottom-space
                      placeholder="Bucket name"
                    />
                    <span v-else>
                      {{ props.row.bucket }}
                    </span>
                  </q-td>
                </template>

                <template v-slot:body-cell-actions="props">
                  <q-td :props="props">
                    <q-btn dense flat icon="delete" color="negative" @click="deleteExtraBucket(props.row)">
                      <q-tooltip>Delete bucket</q-tooltip>
                    </q-btn>
                  </q-td>
                </template>
              </q-table>

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
                :rows="linkedBuckets"
                :columns="linkedColumns"
                row-key="id"
                bordered
                flat
                :loading="loading"
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
                    <q-btn dense flat icon="key" :disable="!!props.row.request_timestamp"
                           @click="requestBucket(props.row)">
                      <q-tooltip>Request bucket access</q-tooltip>
                    </q-btn>
                    <q-btn dense flat icon="open_in_new" @click="openBucket(props.row.bucket)">
                      <q-tooltip>Open bucket</q-tooltip>
                    </q-btn>
                    <!--
                    <q-btn dense flat icon="link_off" color="negative" @click="unlink(props.row)">
                      <q-tooltip>Unlink</q-tooltip>
                    </q-btn>
                    -->
                  </q-td>
                </template>
              </q-table>

            </q-tab-panel>

            <q-tab-panel name="bucketRequests">
              <!-- Requested Buckets -->
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
                :loading="loading"
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
                    <!--
                    <q-btn dense flat icon="open_in_new" @click="openBucket(props.row.bucket)">
                      <q-tooltip>Open bucket</q-tooltip>
                    </q-btn>
                    -->
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
import type {Bucket, ExtraBucketUI, Membership, WorkspaceEdit, WorkspaceEditUI} from 'src/models/models'
import {useLuigiWorkspace} from 'src/composables/useLuigi'
import {QTable, useQuasar} from 'quasar'
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

const allAvailableBuckets = ref<boolean>(false)

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

/*
function sortByBucketNameAsc(a: Bucket, b: Bucket) {
  return (a.bucket ?? '').localeCompare(b.bucket ?? '')
}
*/

function sortByGrantDesc(a: Bucket, b: Bucket) {
  return (b.grant_timestamp ?? '').localeCompare(a.grant_timestamp ?? '')
}

function sortByRequestDesc(a: Bucket, b: Bucket) {
  return (b.request_timestamp ?? '').localeCompare(a.request_timestamp ?? '')
}

function sortByRequestThenGrantDesc(a: Bucket, b: Bucket) {
  const g = sortByRequestDesc(a, b)
  if (g !== 0) return g
  return sortByGrantDesc(a, b)
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
            ws.storage?.buckets?.filter((b) => b !== ws.name && b.startsWith(ws.name)).map(b => ({
              bucket: b,
              requests: 0,
              grants: 0
            } as ExtraBucketUI)) ?? [],
          // linked_buckets: ws.storage?.buckets?.filter((b) => !b.startsWith(ws.name)) ?? [],
          linked_buckets: ctx.bucketAccessRequests ?? []
        }
        let i = 0
        form.value.linked_buckets.forEach((b: Bucket) => {

          if (b.workspace !== ws.name) {
            // TODO remove
            if (i % 2 === 0) {
              b.grant_timestamp = ''
            }
            i++
            const extraBucket = form.value.extra_buckets.find((ex => ex.bucket === b.bucket))
            if (extraBucket) {
              if (b.request_timestamp) {
                extraBucket.requests++
              }
              if (b.grant_timestamp) {
                extraBucket.grants++
              }
            }
          }
        })
      } else {
        message.value = 'Workspace Data not provided.'
      }
    }
  }
})

function scrollToAndFocusLastRow(tableRef: QTable) {
  // Wait for DOM update, then scroll to the new row
  nextTick().then(() => {
    const tableEl = tableRef?.$el as HTMLElement | undefined
    if (tableEl) {
      const rows = tableEl.querySelectorAll('tbody tr')
      const lastRow = rows[rows.length - 1] as HTMLElement | undefined
      if (!lastRow) {
        return
      }
      lastRow.scrollIntoView({behavior: 'smooth', block: 'nearest'})

      // Focus the q-input inside that row (robust selector)
      const inputEl =
        (lastRow.querySelector<HTMLInputElement>('.q-field__native input')) ||
        (lastRow.querySelector<HTMLInputElement>('input, textarea'))

      if (inputEl) {
        // Small micro-delay helps if the field is still animating
        requestAnimationFrame(() => {
          inputEl.focus()
          inputEl.select()
        })
      }
    }
  }).catch(err => {
    console.error('nextTick failed:', err)
  })

}

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
  }
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
  rowsPerPage: 0
}

function addMember() {
  const newRow = {
    id: crypto.randomUUID(),
    member: '',
    role: 'contributor',
    isNew: true
  } as Membership & { id: string }

  const idxNewMember = form.value.memberships.findIndex((m) => !m.member)
  if (idxNewMember < 0) {
    form.value.memberships.push(newRow)
  }

  scrollToAndFocusLastRow(memberTable.value)
}

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
    name: 'actions',
    label: 'Actions',
    field: 'bucket',
    align: 'center'
  }
]

const extraBucketTable = ref()
const btnAddExtraBucket = ref()

function addExtraBucket() {
  console.log('add bucket')
  const idxNew = form.value.extra_buckets.findIndex((b) => !b.bucket)
  if (idxNew < 0) {
    form.value.extra_buckets.push({isNew: true} as ExtraBucketUI)
  }

  scrollToAndFocusLastRow(extraBucketTable.value)
}

function deleteExtraBucket(row: ExtraBucketUI) {
  console.log('delete bucket', row.bucket)
  const index = form.value.extra_buckets.findIndex(b => b.bucket === row.bucket)
  if (index !== -1) {
    form.value.extra_buckets.splice(index, 1)
  }
}


const bucketInitialPagination = {
  sortBy: '',
  descending: false,
  page: 0,
  rowsPerPage: 0
}

const linkedBucketStyle = computed(() => {
  if (btnAddExtraBucket.value) {
    const el = btnAddExtraBucket.value?.$el
    const top = el.getBoundingClientRect().top
    console.log(top)
  }
  return {
    // height: `${state.table1Height}px`,
    height: `calc(100vh - 600px)`
//  overflow: 'auto'
  }
})

const linkedBuckets = computed(() =>
  form.value.linked_buckets
    .filter(r => r.workspace === form.value.name && (allAvailableBuckets.value || !!r.request_timestamp))
    .sort(sortByRequestThenGrantDesc)
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

/*
function unlink(row: Bucket) {
  // DELETE /bucket-access-requests/:id or appropriate endpoint
  // allAccess.value = allAccess.value.filter(r => r.id !== row.id)
  console.log('unlink', row)
}
 */

function requestBucket(row: Bucket) {
  console.log('request bucket', row.bucket)
  row.request_timestamp = new Date().toISOString()
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

const requestedBuckets = computed(() =>
  form.value.linked_buckets
    .filter(r => r.workspace !== form.value.name)
    .sort(sortByRequestThenGrantDesc)
)

function grantBucket(row: Bucket) {
  // POST /bucket-access-requests/:id/grant
  row.grant_timestamp = new Date().toISOString()
}

function revokeBucket(row: Bucket) {
  // POST /bucket-access-requests/:id/deny (or delete)
  row.grant_timestamp = new Date().toISOString()
}

function denyBucket(row: Bucket) {
  console.log('Deny ', row)
  // POST /bucket-access-requests/:id/deny (or delete)
}

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
    (b) => b.bucket === workspaceName || !b.bucket.startsWith(workspaceName)
  ).map((b) => b.bucket)

  if (invalidBuckets.length > 0) {
    message.value = `Error: The following bucket names must start with '${workspaceName}': ${invalidBuckets.join(', ')}`
    activeTab.value = 'buckets'
    return
  }

  const workspaceEdit = {
    name: workspaceName,
    members: (form.value.memberships ?? []).filter(m => !!m.member).map(m => m.member),
    extra_buckets: form.value.extra_buckets.map(b => b.bucket),
    linked_buckets: form.value.linked_buckets.filter(r => !!r.request_timestamp).map(r => r.bucket)
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
  --hdr1: 48px

  .q-table__top,
  .q-table__bottom,
  thead tr th
    background-color: white

  thead tr th
    position: sticky
    z-index: 2

  thead tr:first-child th
    top: 0
    z-index: 3

  &.q-table--loading thead tr:last-child th
    top: calc(var(--hdr1))

  tbody
    scroll-margin-top: calc(var(--hdr1))
</style>
