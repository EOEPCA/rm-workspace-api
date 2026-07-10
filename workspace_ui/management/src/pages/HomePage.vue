<template>
  <div class="q-pa-md">
    <!-- Loading -->
    <div v-if="loading" class="row justify-center q-my-md">
      <q-spinner size="28px"/>
    </div>

    <!-- Error -->
    <q-banner v-if="errorMessage" class="q-mb-md" dense>
      {{ errorMessage }}
    </q-banner>

    <!-- Workspace Content -->
    <div v-if="!loading && !errorMessage && ws">
      <!-- Workspace Header -->
      <q-card class="q-mb-md">
        <q-card-section>
          <q-chip
            :color="ws.status === 'ready' ? 'green' : 'orange'"
            text-color="white"
            square
          >
            <q-icon name="info" class="q-mr-sm"/>
            Status: {{ ws.status }}
          </q-chip>
        </q-card-section>

        <template v-if="canSeeResourceUsage && resourceStorage">
          <q-separator/>
          <q-list separator dense>
            <q-expansion-item
              dense
              dense-toggle
              expand-separator
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

      <!-- Members -->
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

      <!-- Buckets -->
      <q-card v-if="canSeeBuckets && ws.storage?.buckets?.length" class="q-mb-md">
        <q-card-section class="row items-center q-py-sm">
          <div class="text-subtitle1">Buckets</div>
          <q-space/>
          <span class="attribute attribute-count">{{ ws.storage?.buckets?.length }}</span>
        </q-card-section>
        <q-separator/>
        <q-list separator dense>
          <template
            v-for="bucket in ws.storage?.buckets || []"
            :key="bucket.name"
          >
            <q-expansion-item
              v-if="hasStorageCredentials"
              dense
              dense-toggle
              expand-separator
            >
              <template v-slot:header>
                <q-item-section>
                  <div class="entity-line">
                    <span class="entity-name">{{ bucket.name }}</span>
                    <span v-if="bucket.discoverable" class="attribute">discoverable</span>
                    <span
                      v-for="rule in bucket.lifecycle_rules || []"
                      :key="rule.target"
                      class="attribute lifecycle-rule"
                    >
                      {{ formatLifecycleRule(rule) }}
                      <q-tooltip>{{ lifecycleRuleTooltip(rule) }}</q-tooltip>
                    </span>
                  </div>
                </q-item-section>
              </template>

              <pre class="credential-json">{{ prettyStorageCredentials }}</pre>
            </q-expansion-item>

            <q-item
              v-else
              dense
            >
              <q-item-section>
                <div class="entity-line">
                  <span class="entity-name">{{ bucket.name }}</span>
                  <span v-if="bucket.discoverable" class="attribute">discoverable</span>
                  <span
                    v-for="rule in bucket.lifecycle_rules || []"
                    :key="rule.target"
                    class="attribute lifecycle-rule"
                  >
                    {{ formatLifecycleRule(rule) }}
                    <q-tooltip>{{ lifecycleRuleTooltip(rule) }}</q-tooltip>
                  </span>
                </div>
              </q-item-section>
              <q-tooltip>Credentials not available yet</q-tooltip>
            </q-item>
          </template>
        </q-list>
      </q-card>

      <!-- Stores -->
      <q-card v-if="canSeeStores && storeSummaries.length" class="q-mb-md">
        <q-card-section class="row items-center q-py-sm">
          <div class="text-subtitle1">Stores</div>
          <q-space/>
          <span class="attribute attribute-count">{{ storeSummaries.length }}</span>
        </q-card-section>
        <q-separator/>
        <q-list separator dense>
          <template
            v-for="store in storeSummaries"
            :key="`${store.type}:${store.name}`"
          >
            <q-expansion-item
              v-if="store.hasCredentials"
              dense
              dense-toggle
              expand-separator
            >
              <template v-slot:header>
                <q-item-section>
                  <div class="entity-line">
                    <span class="entity-name">{{ store.name }}</span>
                    <span class="attribute">{{ store.label }}</span>
                    <span v-if="store.storage" class="attribute">{{ store.storage }}</span>
                    <span v-if="store.backupStorage" class="attribute">backup {{ store.backupStorage }}</span>
                  </div>
                </q-item-section>
              </template>

              <pre class="credential-json">{{ prettyJson(store.credentials) }}</pre>
            </q-expansion-item>

            <q-item
              v-else
              dense
            >
              <q-item-section>
                <div class="entity-line">
                  <span class="entity-name">{{ store.name }}</span>
                  <span class="attribute">{{ store.label }}</span>
                  <span v-if="store.storage" class="attribute">{{ store.storage }}</span>
                  <span v-if="store.backupStorage" class="attribute">backup {{ store.backupStorage }}</span>
                </div>
              </q-item-section>
              <q-tooltip>Credentials not available yet</q-tooltip>
            </q-item>
          </template>
        </q-list>
      </q-card>

    </div>

    <!-- Fallback if no workspace data -->
    <div v-if="!loading && !errorMessage && !ws" class="q-pa-md text-center">
      <p>No workspace data loaded.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useLuigiWorkspace } from 'src/composables/useLuigi'
import type { BucketLifecycleRule, Store, Workspace } from 'src/models/models'
import { formatStorageQuantity } from 'src/services/storageQuantity'
import { useUserStore } from 'src/stores/userStore'

/** ---- State ---- */
const errorMessage = ref<string>('')
const ws = ref<Workspace | null>(null)

const userStore = useUserStore()

/** ---- Permission-driven computed flags ---- */
const canSeeMembers = computed(() => userStore.canViewMembers)
const canSeeBuckets = computed(() => userStore.canViewBuckets)
const canSeeBucketCredentials = computed(() => userStore.canViewBucketCredentials)
const canSeeResourceUsage = computed(() => userStore.canViewResourceUsage)
const canSeeStores = computed(() => userStore.canViewStores)

const resourceStorage = computed(() => ws.value?.resource_usage?.storage)
const storageRequestedLabel = computed(() => formatStorageQuantity(resourceStorage.value?.requested ?? '0'))
const storageQuotaLabel = computed(() => {
  const quota = resourceStorage.value?.quota
  return quota ? `${formatStorageQuantity(quota)} allowed` : 'No quota set'
})

const hasStorageCredentials = computed<boolean>(() => {
  if (!canSeeBucketCredentials.value) return false
  const creds = ws.value?.storage?.credentials
  return !!creds && Object.keys(creds).length > 0
})

const storageCredentialsForDisplay = computed<Record<string, unknown>>(() =>
  Object.fromEntries(
    Object.entries(ws.value?.storage?.credentials ?? {}).filter(([key]) => key !== 'bucketname')
  )
)

const prettyStorageCredentials = computed<string>(() =>
  prettyJson(storageCredentialsForDisplay.value)
)

function storeTypeLabel(type: string) {
  const labels: Record<string, string> = {
    database: 'Database (Postgres)',
    vector: 'Vector store (Qdrant)',
    cache: 'Cache (Redis)',
    document: 'Document store (MongoDB)',
  }
  return labels[type] ?? type
}

function credentialsForStore(store: Store): Record<string, unknown> {
  const credentialsByName = ws.value?.datalab?.store_credentials?.[store.type]
  if (!credentialsByName) return {}

  const directCredentials = credentialsByName[store.name] ?? credentialsByName.pg0 ?? credentialsByName.default
  if (directCredentials) return credentialsForStoreName(store, directCredentials)

  const credentialGroups = Object.values(credentialsByName)
  return credentialGroups.length === 1 ? credentialsForStoreName(store, credentialGroups[0] ?? {}) : {}
}

function credentialsForStoreName(store: Store, credentials: Record<string, unknown>): Record<string, unknown> {
  if (store.type !== 'database') {
    return credentials
  }

  const scopedCredentials: Record<string, unknown> = { ...credentials }
  const urls = scopedCredentials.urls
  const externalUrls = scopedCredentials.external_urls

  if (isRecord(urls)) {
    if (urls[store.name]) {
      scopedCredentials.url = urls[store.name]
    }
    delete scopedCredentials.urls
  }

  if (isRecord(externalUrls)) {
    if (externalUrls[store.name]) {
      scopedCredentials.external_url = externalUrls[store.name]
    }
    delete scopedCredentials.external_urls
  }

  return scopedCredentials
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function credentialEntries(credentials: Record<string, unknown>) {
  return Object.entries(credentials).filter(([, value]) => value !== null && value !== undefined && value !== '')
}

function prettyJson(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2)
}

function formatLifecycleRule(rule: BucketLifecycleRule) {
  const condition = rule.min_age ? rule.min_age : rule.at
  return `${rule.mode} ${rule.target} ${condition ?? ''}`.trim()
}

function lifecycleRuleTooltip(rule: BucketLifecycleRule) {
  if (rule.min_age) {
    return `${rule.mode} ${rule.target} after ${rule.min_age}`
  }
  return `${rule.mode} ${rule.target} at ${rule.at}`
}

const storeSummaries = computed(() =>
  (ws.value?.datalab?.stores ?? []).map(store => {
    const credentials = credentialsForStore(store)
    return {
      name: store.name,
      type: store.type,
      label: storeTypeLabel(store.type),
      storage: store.storage,
      backupStorage: store.backup_storage,
      credentials,
      hasCredentials: credentialEntries(credentials).length > 0,
    }
  })
)

const { loading } = useLuigiWorkspace({
  onReady: (ctx) => {
    if (!ctx || !ctx.workspace) {
      errorMessage.value = 'Workspace Data not provided.'
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

.credential-json {
  margin: 0;
  padding: 12px;
  border-top: 1px solid currentColor;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: 12px;
}

.lifecycle-rule {
  max-width: 18rem;
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
