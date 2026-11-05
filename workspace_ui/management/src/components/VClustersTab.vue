<template>
  <div class="row items-center q-gutter-sm">
    <div class="text-body1 q-mb-sm">Vclusters</div>
  </div>
  <div v-if="!vclusters.length" class="q-pa-md text-grey-7">No virtual clusters are configured.</div>
  <q-card v-for="cluster in vclusters" :key="cluster.name" flat bordered class="q-mb-md">
    <q-card-section class="row items-center q-py-sm">
      <div class="text-subtitle1">Access profiles for {{ cluster.name }}</div>
      <q-space />
      <q-btn v-if="canManage" color="primary" flat no-caps icon="add" label="Add access profile" @click="openDialog(cluster.name)" />
    </q-card-section>
    <q-table
      flat dense hide-bottom
      :rows="cluster.groups" :columns="columns" row-key="name"
      :rows-per-page-options="[0]" no-data-label="No additional access profiles are configured."
    />
  </q-card>

  <q-dialog v-model="dialogOpen" :persistent="saving">
    <q-card style="width: 480px; max-width: 95vw">
      <q-form @submit="addAccessProfile">
        <q-card-section class="text-h6">Add access profile for {{ instance }}</q-card-section>
        <q-card-section class="q-gutter-md">
          <q-input
            v-model="profileName" label="Name" outlined dense autofocus maxlength="40"
            :disable="saving" :rules="[value => nameError(value) || true]"
          />
          <q-input
            v-model="namespace" label="Namespace" outlined dense
            :disable="saving" :rules="[value => namespaceError(value) || true]"
          />
          <q-select v-model="role" :options="roleOptions" label="Role" outlined dense :disable="saving" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancel" v-close-popup :disable="saving" />
          <q-btn type="submit" color="primary" no-caps label="Add access profile" :loading="saving" />
        </q-card-actions>
      </q-form>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useQuasar, type QTableColumn } from 'quasar'
import type { VCluster, VClusterGroup } from 'src/models/models'
import { createVClusterGroup } from 'src/services/api'
import { namespaceError, profileNameError } from 'src/services/vclusterGroups'
import { useUserStore } from 'src/stores/userStore'

const props = defineProps<{ workspaceName: string; vclusters: VCluster[] }>()
const emit = defineEmits<{ 'update:vclusters': [VCluster[]] }>()
const userStore = useUserStore()
const canManage = computed(() => userStore.hasPermission('MANAGE_VCLUSTERS'))
const $q = useQuasar()
const dialogOpen = ref(false)
const saving = ref(false)
const instance = ref('')
const namespace = ref('')
const profileName = ref('')
const role = ref<'view' | 'edit' | 'admin'>('edit')
const roleOptions = ['view', 'edit', 'admin']
const columns: QTableColumn<VClusterGroup>[] = [
  { name: 'name', label: 'Name', field: 'name', align: 'left' },
  { name: 'namespace', label: 'Namespace', field: 'namespace', align: 'left' },
  { name: 'role', label: 'Role', field: 'role', align: 'left' },
]

function openDialog(name: string) {
  instance.value = name
  namespace.value = ''
  profileName.value = ''
  role.value = 'edit'
  dialogOpen.value = true
}

function nameError(value: string): string {
  const names = props.vclusters.find(cluster => cluster.name === instance.value)?.groups.map(group => group.name) ?? []
  return profileNameError(value, names)
}

async function addAccessProfile() {
  if (!canManage.value || saving.value || nameError(profileName.value) || namespaceError(namespace.value)) return
  saving.value = true
  try {
    const group = await createVClusterGroup(props.workspaceName, instance.value, { name: profileName.value, namespace: namespace.value, role: role.value })
    emit('update:vclusters', props.vclusters.map(cluster => cluster.name === instance.value
      ? { ...cluster, groups: [...cluster.groups, group] }
      : cluster))
    dialogOpen.value = false
    $q.notify({ type: 'positive', message: 'Access profile request submitted.' })
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    $q.notify({ type: 'negative', message: `Could not add access profile: ${message}` })
  } finally {
    saving.value = false
  }
}
</script>
