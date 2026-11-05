<template>
  <q-card class="q-mb-md">
    <q-card-section class="row items-center q-py-sm">
      <div class="text-subtitle1">Stores</div>
      <q-space />
      <q-badge outline color="grey-8">{{ stores.length }}</q-badge>
    </q-card-section>
    <q-separator />
    <q-list separator dense role="group">
      <q-expansion-item
        v-for="store in stores"
        :key="`${store.type}:${store.instance}:${store.name}`"
        dense dense-toggle toggle-aria-label=""
        :disable="!canReadCredentials"
      >
        <template #header>
          <q-item-section>
            <div class="store-summary">
              <span class="text-weight-medium">{{ store.name }}</span>
              <q-badge outline color="grey-8">{{ storeTypeLabel(store.type) }}</q-badge>
              <q-badge v-if="store.storage" outline color="grey-8">{{ store.storage }}</q-badge>
              <q-badge v-if="store.backup_storage" outline color="grey-8">Backup {{ store.backup_storage }}</q-badge>
            </div>
            <div v-if="store.instance" class="text-caption text-grey-7">Instance: {{ store.instance }}</div>
          </q-item-section>
        </template>
        <ConnectionList
          flat
          v-if="connectionsForStore(store, connections).length"
          :connections="connectionsForStore(store, connections)"
          :workspace-name="workspaceName"
        />
        <div v-else class="q-pa-md text-grey-7">No connection is published for this store.</div>
      </q-expansion-item>
    </q-list>
  </q-card>
</template>

<script setup lang="ts">
import type { Connection, Store } from 'src/models/models'
import { connectionsForStore, storeTypeLabel } from 'src/services/dashboardConnections'
import ConnectionList from 'src/components/ConnectionList.vue'
defineProps<{ stores: Store[]; connections: Connection[]; workspaceName: string; canReadCredentials: boolean }>()
</script>

<style scoped>
.store-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  overflow-wrap: anywhere;
}
.store-summary .q-badge {
  white-space: normal;
}
</style>
