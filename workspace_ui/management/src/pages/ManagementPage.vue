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
              <MembersTab
                v-model:memberships="form.memberships"
              />
            </q-tab-panel>

            <!-- BUCKETS TAB -->
            <q-tab-panel name="buckets">
              <BucketsTab
                v-model:extra-buckets="form.extra_buckets"
                v-model:linked-buckets="form.linked_buckets"
                :workspace-name="form.name"
              />

            </q-tab-panel>

            <!-- REQUESTED BUCKETS TAB -->
            <q-tab-panel name="bucketRequests">
              <BucketRequestsTab
                v-model:linked-buckets="form.linked_buckets"
                :workspace-name="form.name"
              />
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
import {computed, ref} from 'vue'
import axios from 'axios'
import type {Bucket, ExtraBucketUI, WorkspaceEdit, WorkspaceEditUI} from 'src/models/models'
import {useLuigiWorkspace} from 'src/composables/useLuigi'
import {useQuasar} from 'quasar'
import MembersTab from 'src/components/MembersTab.vue'
import BucketsTab from 'src/components/BucketsTab.vue'
import BucketRequestsTab from 'src/components/BucketRequestsTab.vue'

const $q = useQuasar()

/** ---- State ---- */
const message = ref<string>('')

const form = ref<WorkspaceEditUI>({
  name: '',
  memberships: [],
  extra_buckets: [],
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

        // prepare number of requests and grants for extraBuckets
        form.value.linked_buckets.forEach((b: Bucket) => {
          if (b.workspace !== ws.name) {
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
