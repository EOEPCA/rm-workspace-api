<template>
  <!--
<div class="text-body1 q-mb-sm">Members</div>
-->

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
        />
        <span v-else>
          {{ props.row.member }}
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

</template>

<script setup lang="ts">
import {ref, watch} from 'vue'
import type {QTableColumn} from 'quasar';
import { QTable } from 'quasar'
import type {Membership} from 'src/models/models'
import {formatDate, scrollToAndFocusLastRow} from 'src/services/common'

/** v-model */
const props = defineProps<{
  memberships: (Membership)[]
}>()

/*
const emit = defineEmits<{
  (e: 'update:memberships', v: (Membership & { id?: string; isNew?: boolean })[]): void
  (e: 'requestFocusLast'): void
}>()
 */

const myMemberships = ref<Membership[]>([])
watch(
  () => props.memberships,
  (v) => { myMemberships.value = v.map(x => ({ ...x })) },
  { immediate: true }
)

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
    field: 'creation_timestamp',
    align: 'left',
    format: (val) => formatDate(val as string | null)
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

function addMember() {
  const newRow = {
    id: crypto.randomUUID(),
    member: '',
    role: 'contributor',
    isNew: true
  } as Membership & { id: string }

  const idxNewMember = myMemberships.value.findIndex((m) => !m.member)
  if (idxNewMember < 0) {
    myMemberships.value.push(newRow)
  }

  scrollToAndFocusLastRow(memberTable.value)
}

</script>
