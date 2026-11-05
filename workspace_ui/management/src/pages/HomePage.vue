<template>
  <div class="q-pa-md">
    <div v-if="loading" class="row justify-center q-my-md">
      <q-spinner size="28px"/>
    </div>
    <q-banner v-if="errorMessage" class="q-mb-md" dense>
      {{ errorMessage }}
    </q-banner>
    <div v-if="!loading && !errorMessage && ws">
      <q-card class="q-mb-md">
        <q-card-section>
          <q-chip
            :color="ws.status === 'ready' ? 'green-9' : 'orange-10'"
            text-color="white"
            square
          >
            <q-icon name="info" class="q-mr-sm"/>
            Status: {{ ws.status }}
          </q-chip>
        </q-card-section>

        <template v-if="canSeeResourceUsage && resourceStorage">
          <q-separator/>
          <q-list separator dense role="group">
            <q-expansion-item
              dense
              dense-toggle
              expand-separator
              toggle-aria-label=""
            >
              <template v-slot:header>
                <q-item-section>
                  <div class="entity-line">
                    <span class="entity-name">Persistent storage</span>
                    <span class="storage-total">{{ storageRequestedLabel }}</span>
                    <span class="text-grey-7">({{ storageQuotaLabel }})</span>
                  </div>
                </q-item-section>
              </template>

              <q-markup-table
                flat
                dense
                separator="horizontal"
                class="storage-usage-table"
                aria-label="Persistent volume claims and requested sizes"
              >
                <tbody>
                  <tr
                    v-for="pvc in resourceStorage.persistent_volume_claims"
                    :key="pvc.name"
                  >
                    <td>{{ pvc.name }}</td>
                    <td class="text-right storage-value">{{ pvc.size }}</td>
                  </tr>
                  <tr v-if="resourceStorage.persistent_volume_claims.length === 0">
                    <td colspan="2" class="text-grey-7">No persistent volume claims</td>
                  </tr>
                </tbody>
              </q-markup-table>
            </q-expansion-item>
          </q-list>
        </template>
      </q-card>
      <q-card v-if="canSeeMembers && ws.datalab?.memberships?.length" class="q-mb-md">
        <q-card-section class="row items-center q-py-sm">
          <div class="text-subtitle1">Members</div>
          <q-space/>
          <span class="attribute attribute-count">{{ ws.datalab?.memberships?.length }}</span>
        </q-card-section>
        <q-separator/>
        <q-list separator dense>
          <q-item
            v-for="membership in ws.datalab?.memberships"
            :key="membership.member"
            dense
          >
            <q-item-section>
              <div class="entity-line">
                <span class="entity-name">{{ membership.member }}</span>
                <span class="attribute">{{ membership.role }}</span>
              </div>
            </q-item-section>
          </q-item>
        </q-list>
      </q-card>
      <BucketCard
        v-if="canSeeBuckets && ws.storage?.buckets?.length"
        :buckets="ws.storage.buckets" :connections="bucketConnections"
        :workspace-name="ws.name" :can-read-credentials="canSeeConnections"
      />
      <StoreCard
        v-if="canSeeStores && ws.datalab?.stores?.length"
        :stores="ws.datalab.stores" :connections="connections"
        :workspace-name="ws.name" :can-read-credentials="canSeeConnections"
      />
      <q-card v-if="canSeeConnections && virtualClusters.length" class="q-mb-md">
        <q-card-section class="row items-center q-py-sm">
          <div class="text-subtitle1">Virtual clusters</div>
          <q-space />
          <q-badge outline>{{ virtualClusters.length }}</q-badge>
        </q-card-section>
        <q-separator />
        <ConnectionList :connections="virtualClusters" :workspace-name="ws.name" />
      </q-card>

      <template v-for="service in serviceConnections" :key="service.label">
        <q-card v-if="canSeeConnections && service.connections.length" class="q-mb-md">
          <q-card-section class="row items-center q-py-sm">
            <div class="text-subtitle1">{{ service.label }}</div>
            <q-space />
            <span class="attribute attribute-count">{{ service.connections.length }}</span>
          </q-card-section>
          <q-separator />
          <ConnectionList :connections="service.connections" :workspace-name="ws.name" />
        </q-card>
      </template>

      <q-card v-if="canSeeOAuth2 && ws.datalab?.oauth2?.length" class="q-mb-md">
        <q-card-section class="row items-center q-py-sm">
          <div class="text-subtitle1">OAuth2</div>
          <q-space />
          <span class="attribute attribute-count">{{ ws.datalab.oauth2.length }}</span>
        </q-card-section>
        <q-separator />
        <ConnectionList :connections="ws.datalab.oauth2" :workspace-name="ws.name" />
      </q-card>

    </div>
    <div v-if="!loading && !errorMessage && !ws" class="q-pa-md text-center">
      <p>No workspace data loaded.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useLuigiWorkspace } from 'src/composables/useLuigi'
import type { Workspace } from 'src/models/models'
import { formatStorageQuantity } from 'src/services/storageQuantity'
import ConnectionList from 'src/components/ConnectionList.vue'
import BucketCard from 'src/components/BucketCard.vue'
import StoreCard from 'src/components/StoreCard.vue'
import { otherConnections } from 'src/services/dashboardConnections'
import { useUserStore } from 'src/stores/userStore'

const errorMessage = ref<string>('')
const ws = ref<Workspace | null>(null)

const userStore = useUserStore()

const canSeeMembers = computed(() => userStore.canViewMembers && !!ws.value?.datalab?.available)
const canSeeBuckets = computed(() => userStore.canViewBuckets && !!ws.value?.storage?.available)
const canSeeResourceUsage = computed(() => userStore.canViewResourceUsage)
const canSeeStores = computed(() => userStore.canViewStores && !!ws.value?.datalab?.available)
const canSeeConnections = computed(() => userStore.canViewConnectionCredentials && !!ws.value?.datalab?.available)
const canSeeOAuth2 = computed(() => userStore.canViewOAuth2Credentials && !!ws.value?.datalab?.available)

const resourceStorage = computed(() => ws.value?.resource_usage?.storage)
const storageRequestedLabel = computed(() => formatStorageQuantity(resourceStorage.value?.requested ?? '0'))
const storageQuotaLabel = computed(() => {
  const quota = resourceStorage.value?.quota
  return quota ? `${formatStorageQuantity(quota)} allowed` : 'No quota set'
})

const connections = computed(() => ws.value?.datalab?.connections ?? [])
const bucketConnections = computed(() => connections.value.filter(connection => connection.type === 's3' && connection.name === 'primary'))
const virtualClusters = computed(() => connections.value.filter(connection => connection.type === 'vcluster'))
const serviceConnections = computed(() => {
  const remaining = otherConnections(
    connections.value,
    canSeeStores.value ? ws.value?.datalab?.stores ?? [] : [],
    canSeeBuckets.value && !!ws.value?.storage?.buckets?.length,
  )
  const labels: Record<string, string> = { s3: 'S3', postgres: 'PostgreSQL', mongo: 'MongoDB', redis: 'Redis' }
  return [...new Set(remaining.map(connection => connection.type))].map(type => ({
    label: labels[type] ?? type,
    connections: remaining.filter(connection => connection.type === type),
  }))
})

const { loading } = useLuigiWorkspace({
  onReady: (ctx) => {
    if (!ctx || !ctx.workspace) {
      errorMessage.value = 'Workspace data is missing.'
      ws.value = null
      userStore.clearUser()
      return
    }

    ws.value = ctx.workspace
    userStore.setUser(ctx.workspace.user ?? null)
  },
})
</script>

<style scoped>
.entity-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.entity-name {
  min-width: 9rem;
  font-weight: 500;
}

.attribute {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  max-width: 100%;
  padding: 2px 8px;
  border: 1px solid #4a4a4a;
  color: #4a4a4a;
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.attribute-count {
  min-width: 2rem;
  justify-content: center;
}

.storage-usage-table {
  width: 100%;
  border-top: 1px solid currentColor;
}

.storage-value {
  width: 10rem;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.storage-total {
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}
</style>
