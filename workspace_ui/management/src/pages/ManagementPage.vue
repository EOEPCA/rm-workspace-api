<template>
  <div class="q-pa-md" style="min-width: 1000px; max-width: calc(80vw); margin: 0 auto;">
    <q-card>
      <q-card-section>
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
        <div v-if="loading" class="row justify-center q-my-md">
          <q-spinner size="28px"/>
        </div>
        <q-form v-if="!loading && form.name">
          <q-tabs
            v-model="activeTab"
            class="text-primary q-mb-md"
            align="justify"
            dense
            outside-arrows
            mobile-arrows
          >
            <q-tab v-if="canSeeMembers" name="members" label="Members" :alert="form.memberships.length === 0"/>
            <q-tab v-if="canSeeBuckets" name="buckets" label="Buckets"/>
            <q-tab v-if="canSeeBuckets" name="bucketRequests" label="Requested Buckets"/>
            <q-tab v-if="canSeeStores" name="stores" label="Stores"/>
            <q-tab v-if="canSeeVClusters" name="vclusters" label="Vclusters"/>
            <q-tab v-if="canSeeSessions" name="sessions" label="Sessions"/>
          </q-tabs>

          <q-separator/>
          <q-tab-panels v-model="activeTab" animated>
            <q-tab-panel v-if="canSeeMembers" name="members">
              <MembersTab
                :workspace-name="form.name"
                v-model:memberships="form.memberships"
              />
            </q-tab-panel>
            <q-tab-panel v-if="canSeeBuckets" name="buckets">
              <BucketsTab
                :workspace-name="form.name"
                v-model:buckets="form.buckets"
                v-model:linked-buckets="form.linked_buckets"
              />

            </q-tab-panel>
            <q-tab-panel v-if="canSeeBuckets" name="bucketRequests">
              <BucketRequestsTab
                :workspace-name="form.name"
                v-model:linked-buckets="form.linked_buckets"
              />
            </q-tab-panel>

            <q-tab-panel v-if="canSeeStores" name="stores">
              <StoresTab
                :workspace-name="form.name"
                :datalab-available="form.datalab_available"
                :available-store-types="form.available_store_types"
                v-model:stores="form.stores"
              />
            </q-tab-panel>

            <q-tab-panel v-if="canSeeVClusters" name="vclusters">
              <VClustersTab :workspace-name="form.name" v-model:vclusters="form.vclusters" />
            </q-tab-panel>

            <q-tab-panel v-if="canSeeSessions" name="sessions">
              <SessionsTab
                :workspace-name="form.name"
                :datalab-available="form.datalab_available"
                :max-sessions="form.max_sessions"
                v-model:sessions="form.sessions"
              />
            </q-tab-panel>

          </q-tab-panels>

        </q-form>
      </q-card-section>
    </q-card>
  </div>
</template>

<script setup lang="ts">
import {computed, ref} from 'vue'
import type {Bucket, BucketUI, WorkspaceEditUI} from 'src/models/models'
import {useLuigiWorkspace} from 'src/composables/useLuigi'
import MembersTab from 'src/components/MembersTab.vue'
import BucketsTab from 'src/components/BucketsTab.vue'
import BucketRequestsTab from 'src/components/BucketRequestsTab.vue'
import {useUserStore} from 'stores/userStore'
import StoresTab from 'components/StoresTab.vue'
import SessionsTab from 'components/SessionsTab.vue'
import VClustersTab from 'components/VClustersTab.vue'
import { getWorkspaceForManagement } from 'src/services/api'
import { availableManagementTabs, type ManagementTab } from 'src/services/workspaceTabs'

const message = ref<string>('')
const userStore = useUserStore()

const form = ref<WorkspaceEditUI>({
  name: '',
  memberships: [],
  buckets: [],
  linked_buckets: [],
  storage_available: false,
  datalab_available: false,
  available_store_types: [],
  stores: [],
  vclusters: [],
  sessions: [],
  max_sessions: 3,
})

const visibleTabs = computed(() => availableManagementTabs(
  userStore.permissions,
  form.value.storage_available,
  form.value.datalab_available,
  form.value.available_store_types,
  form.value.vclusters,
))
const canSeeMembers = computed(() => visibleTabs.value.includes('members'))
const canSeeBuckets = computed(() => visibleTabs.value.includes('buckets'))
const canSeeStores = computed(() => visibleTabs.value.includes('stores'))
const canSeeVClusters = computed(() => visibleTabs.value.includes('vclusters'))
const canSeeSessions = computed(() => visibleTabs.value.includes('sessions'))
const activeTab = ref<ManagementTab | ''>('')

const isError = computed(() => message.value.startsWith('Error:'))
const displayMessage = computed(() =>
  isError.value ? message.value.substring(7) : message.value
)

const managementLoading = ref(false)
const {loading: contextLoading} = useLuigiWorkspace({
  onReady: async (ctx) => {
    managementLoading.value = true
    try {
      if (ctx && ctx.workspace) {
        const ws = await getWorkspaceForManagement(ctx.workspace.name)
        if (ws.name) {
          message.value = ''
          userStore.setUser(ws.user ?? null)

          form.value = {
            name: ws.name,
            memberships: (ws.datalab?.memberships ?? []).map(m => ({...m, id: crypto.randomUUID(), isNew: false})),
            buckets: (ws.storage?.buckets ?? []).map(b => ({
                bucket: b.name,
                discoverable: b.discoverable,
                lifecycle_rules: (b.lifecycle_rules ?? []).map(rule => ({...rule, id: crypto.randomUUID()})),
                requests: 0,
                grants: 0
              } as BucketUI)),
            linked_buckets: ws.storage?.bucket_access_requests ?? [],
            storage_available: ws.storage?.available ?? false,
            datalab_available: ws.datalab?.available ?? false,
            available_store_types: ws.datalab?.available_store_types ?? [],
            stores: (ws.datalab?.stores ?? []).map(m => ({...m, id: crypto.randomUUID(), isNew: false})),
            vclusters: ws.datalab?.vclusters ?? [],
            sessions: (ws.datalab?.sessions ?? []).map(m => ({...m, id: crypto.randomUUID(), isNew: false})),
            max_sessions: ws.datalab?.max_sessions ?? 3
          }

          if (!activeTab.value || !visibleTabs.value.includes(activeTab.value)) {
            activeTab.value = visibleTabs.value[0] ?? ''
          }

          // Show requests and grants on the bucket that owns them.
          form.value.linked_buckets.forEach((b: Bucket) => {
            if (b.workspace !== ws.name) {
              const bucket = form.value.buckets.find((ex => ex.bucket === b.bucket))
              if (bucket) {
                if (b.request_timestamp) {
                  bucket.requests++
                }
                if (b.grant_timestamp) {
                  bucket.grants++
                }
              }
            }
          })
        } else {
          message.value = 'Workspace data is missing.'
          userStore.setUser(null)
        }
      }
    } catch (error) {
      message.value = `Error: Could not load workspace configuration: ${error instanceof Error ? error.message : String(error)}`
      form.value.name = ''
    } finally {
      managementLoading.value = false
    }
  }
})
const loading = computed(() => contextLoading.value || managementLoading.value)

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
