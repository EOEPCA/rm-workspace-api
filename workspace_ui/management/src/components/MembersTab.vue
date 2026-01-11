<template>
  <div class="row items-center q-gutter-sm">
    <div class="text-body1 q-mb-sm">Members</div>
    <q-space/>
    <q-btn
      color="primary"
      flat
      no-caps
      class="q-mt-sm"
      @click="addMemberRow"
      :disable="!canManageMembers"
    >
      <q-icon name="add" class="q-mr-sm" />
      Add Member
    </q-btn>
  </div>

  <q-table
    ref="memberTable"
    class="my-sticky-header-table"
    style="height: calc(100vh - 330px)"
    :rows="myMemberships"
    :columns="memberColumns"
    row-key="id"
    flat
    bordered
    :pagination="initialPagination"
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
          {{ props.row.member }}
        </span>
      </q-td>
    </template>

    <template v-slot:body-cell-role="props">
      <q-td :props="props">
        <q-select
          v-if="canManageMembers && props.row.role !== 'owner'"
          v-model="props.row.role"
          :options="roleOptions"
          outlined
          dense
          emit-value
          map-options
          hide-bottom-space
          style="min-width: 160px"
        />
        <span v-else>
          {{ props.row.role }}
        </span>
      </q-td>
    </template>

    <template v-slot:body-cell-actions="props">
      <q-td :props="props">
        <q-btn v-if="props.row.role !== 'owner' && props.row.isNew" dense flat icon="delete" color="negative"
               @click="myMemberships.splice(props.rowIndex, 1)">
          <q-tooltip>Remove member</q-tooltip>
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
        <div>{{ myMemberships.length }}</div>
      </div>
    </template>
    -->

  </q-table>

  <q-btn color="primary" no-caps label="Save" @click="createMembers" style="margin-top: 5px" :disable="!canManageMembers || !hasChanged" />

</template>

<script setup lang="ts">
import {computed, ref, watch} from 'vue'
import type {QTable, QTableColumn} from 'quasar'
import {useQuasar} from 'quasar'
import type {Membership} from 'src/models/models'
import {formatDate, scrollToAndFocusLastRow} from 'src/services/common'
import {saveMembers} from 'src/services/api'
import {useUserStore} from 'stores/userStore'

/** v-model */
const props = defineProps<{
  workspaceName: string,
  memberships: Membership[]
}>()

/*
const emit = defineEmits<{
  (e: 'update:memberships', v: (Membership & { id?: string; isNew?: boolean })[]): void
  (e: 'requestFocusLast'): void
}>()
 */

const $q = useQuasar()
const userStore = useUserStore()

const myMemberships = ref<Membership[]>([])
const initialMemberships = ref<Membership[]>([])
watch(
  () => props.memberships,
  (v) => {
    const cloned = v.map(m => ({ ...m }))
    myMemberships.value = cloned
    initialMemberships.value = cloned.map(m => ({ ...m }))
  },
  {immediate: true}
)

type MembershipRole = 'user' | 'admin'

const roleOptions: MembershipRole[] = ['user', 'admin']

type MembershipKey = string

function normalizeMemberships(list: Membership[]): MembershipKey[] {
  // Create a stable, order-independent representation
  return list
    .map(m => `${m.member}::${m.role}`) // key per membership
    .sort()
}

const hasChanged = computed(() => {
  const a = normalizeMemberships(myMemberships.value)
  const b = normalizeMemberships(initialMemberships.value)

  if (a.length !== b.length) return true

  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return true
  }
  return false
})

const memberTable = ref<QTable | null>(null)

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
//    field: 'creation_timestamp',
    field: (row) => row.creation_timestamp ? formatDate(row.creation_timestamp) : (row.isPending ? 'Pending' : ''),
    align: 'left',
//    format: (val) => formatDate(val as string | null)
  },
  {
    name: 'actions',
    label: '',
    field: 'role',
    align: 'center'
  }
]

const initialPagination = {
  sortBy: '',
  descending: false,
  page: 0,
  rowsPerPage: 0
}

const canManageMembers = computed(() => userStore.canManageMembers)

function addMemberRow() {
  const newRow = {
    id: crypto.randomUUID(),
    member: '',
    role: 'user',
    isNew: true
  } as Membership & { id: string }

  const idxNewMember = myMemberships.value.findIndex((m) => !m.member)
  if (idxNewMember < 0) {
    myMemberships.value.push(newRow)
  }

  scrollToAndFocusLastRow(memberTable.value)
}


function createMembers() {
  if (!canManageMembers.value) {
    return
  }

  const nowIso = new Date().toISOString()

  const memberships = myMemberships.value
    .filter(m => !!m.member)
    .filter(m => (String(m.role || '').toLowerCase() !== 'owner'))
    .map(m => ({
      member: m.member.trim(),
      role: (String(m.role || 'user').toLowerCase() as 'user' | 'admin'),
      creation_timestamp: m.creation_timestamp ?? nowIso,
    }))

  saveMembers(props.workspaceName, memberships)
    .then(() => {
        myMemberships.value.forEach((member: Membership) => {
          if (member.isNew) {
            member.isPending = true
          }
          member.isNew = false
        })
        // reset initialMemberships
        initialMemberships.value = myMemberships.value.map(m => ({ ...m }))

        $q.notify({
          type: 'positive',
          message: 'Members were successfully submitted!'
        })
      }
    )
    .catch((err) => {
      const msg = err instanceof Error ? err.message : String(err)
      $q.notify({
        type: 'negative',
        message: `Error creating members: ${msg}`
      })
    })
}


</script>
