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
        <q-form v-if="!loading && form.name">
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
              <MembersTab
                :workspace-name="form.name"
                v-model:memberships="form.memberships"
              />
            </q-tab-panel>

            <!-- BUCKETS TAB -->
            <q-tab-panel name="buckets">
              <BucketsTab
                :workspace-name="form.name"
                v-model:buckets="form.buckets"
                v-model:linked-buckets="form.linked_buckets"
              />

            </q-tab-panel>

            <!-- REQUESTED BUCKETS TAB -->
            <q-tab-panel name="bucketRequests">
              <BucketRequestsTab
                :workspace-name="form.name"
                v-model:linked-buckets="form.linked_buckets"
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

/** ---- State ---- */
const message = ref<string>('')

const form = ref<WorkspaceEditUI>({
  name: '',
  memberships: [],
  buckets: [],
  linked_buckets: []
})

/** Tabs */
const activeTab = ref<'members' | 'buckets' | 'bucketRequests'>('members')

/** ---- UI helpers ---- */
const isError = computed(() => message.value.startsWith('Error:'))
const displayMessage = computed(() =>
  isError.value ? message.value.substring(7) : message.value
)


const {loading} = useLuigiWorkspace({
  onReady: (ctx) => {
    if (ctx && ctx.workspace) {
      const ws = ctx.workspace
      if (ws.name) {
        message.value = `Using pre-loaded data for workspace: ${ws.name} (${ws.version})`
        form.value = {
          name: ws.name,
          memberships: (ws.memberships ?? []).map(m => ({...m, id: crypto.randomUUID(), isNew: false})),
          buckets: (ws.buckets ?? []).map(b => ({
              bucket: b,
              requests: 0,
              grants: 0
            } as BucketUI)) ?? [],
          linked_buckets: ws.bucket_access_requests ?? []
        }

        // prepare number of requests and grants for buckets
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
        message.value = 'Workspace Data not provided.'
      }
    }
  }
})

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
