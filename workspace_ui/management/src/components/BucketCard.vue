<template>
  <q-card class="q-mb-md">
    <q-card-section class="row items-center q-py-sm">
      <div class="text-subtitle1">Buckets</div>
      <q-space />
      <q-badge outline color="grey-8">{{ buckets.length }}</q-badge>
    </q-card-section>
    <q-separator />
    <q-list separator dense>
      <q-item v-for="bucket in buckets" :key="bucket.name" dense>
        <q-item-section>
          <div class="bucket-summary">
            <span class="text-weight-medium">{{ bucket.name }}</span>
            <q-badge v-if="bucket.discoverable" outline color="grey-8">Discoverable</q-badge>
            <q-badge v-for="rule in bucket.lifecycle_rules || []" :key="rule.target" outline color="grey-8">
              {{ rule.mode }} {{ rule.target }} {{ rule.min_age ? 'after ' + rule.min_age : 'at ' + rule.at }}
            </q-badge>
          </div>
        </q-item-section>
      </q-item>
    </q-list>
    <template v-if="canReadCredentials">
      <q-separator />
      <ConnectionList v-if="connections.length" :connections="connections" :workspace-name="workspaceName" />
      <div v-else class="q-pa-md text-grey-7">S3 credentials are not published yet.</div>
    </template>
  </q-card>
</template>

<script setup lang="ts">
import type { BucketNew, Connection } from 'src/models/models'
import ConnectionList from 'src/components/ConnectionList.vue'
defineProps<{ buckets: BucketNew[]; connections: Connection[]; workspaceName: string; canReadCredentials: boolean }>()
</script>

<style scoped>
.bucket-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  overflow-wrap: anywhere;
}
.bucket-summary .q-badge {
  white-space: normal;
}
</style>
