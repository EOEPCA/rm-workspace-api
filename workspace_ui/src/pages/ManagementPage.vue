<template>
  <div class="q-pa-md" style="max-width: 700px; margin: 0 auto;">
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
            <q-icon :name="isError ? 'error' : 'check_circle'" class="q-mr-sm" />
            <div class="col">{{ displayMessage }}</div>
          </div>
        </q-banner>

        <!-- Loading -->
        <div v-if="loading" class="row justify-center q-my-md">
          <q-spinner size="28px" />
        </div>

        <!-- Form -->
        <q-form v-if="!loading && form.name" @submit.prevent="submit">
          <q-select
            v-model="form.clusterStatus"
            :options="clusterStatusOptions"
            label="vCluster"
            outlined
            class="q-mb-md"
          />

          <!-- Members -->
          <div class="q-mb-md">
            <div class="text-body1 q-mb-sm">Members</div>
            <div
              v-for="(member, index) in form.members"
              :key="'member-' + index"
              class="q-mb-xs"
            >
              <q-input
                v-model="form.members[index]"
                outlined
                dense
                hide-bottom-space
              />
            </div>
            <q-btn
              color="primary"
              flat
              no-caps
              class="q-mt-sm"
              @click="form.members.push('')"
            >
              <q-icon name="add" class="q-mr-sm" />
              Add Member
            </q-btn>
          </div>

          <!-- Extra Buckets -->
          <div class="q-mb-md">
            <div class="text-body1 q-mb-sm">Extra Buckets</div>
            <div
              v-for="(source, index) in form.extraBuckets"
              :key="'source-' + index"
              class="q-mb-xs"
            >
              <q-input
                v-model="form.extraBuckets[index]"
                outlined
                dense
                hide-bottom-space
              />
            </div>
            <q-btn
              color="primary"
              flat
              no-caps
              class="q-mt-sm"
              @click="form.extraBuckets.push('')"
            >
              <q-icon name="add" class="q-mr-sm" />
              Add Source
            </q-btn>
          </div>

          <q-btn type="submit" color="primary" unelevated no-caps label="Save Changes" />
        </q-form>
      </q-card-section>
    </q-card>
  </div>
</template>

<script setup lang="ts">
import {computed, ref} from 'vue'
import axios from 'axios'
import type {Workspace, WorkspaceEdit} from 'src/models/models'
import type {ClusterStatus} from 'src/types/workspace'
import {useLuigiWorkspace} from 'src/composables/useLuigi'

/*
type InitCtx = {
  workspaceName?: string
  edit?: {
    name?: string
    members?: Array<string | { name: string }>
    clusterStatus?: ClusterStatus
    extraBuckets?: string[]
  }
}

 */

/** ---- State ---- */
const message = ref<string>('')
// const loading = ref<boolean>(true)

const form = ref<WorkspaceEdit>({
  name: '',
  members: [],
  clusterStatus: 'active',
  extraBuckets: []
})

/** ---- UI helpers ---- */
const isError = computed(() => message.value.startsWith('Error:'))
const displayMessage = computed(() => (isError.value ? message.value.substring(7) : message.value))
const clusterStatusOptions: ClusterStatus[] = ['active', 'suspended']


const {
  loading,
//  workspace
} = useLuigiWorkspace<Workspace>({
    onReady: (ws) => {
//      console.log('Workspace initialized:', ws?.name)
      if (ws) {
        if (ws.name) {
          message.value = `Using pre-loaded data for workspace: ${ws.name}`

          const rawMembers = Array.isArray(ws.members) ? ws.members : []
          const normalizedMembers = rawMembers.map((m) => (m?.name ?? '?')
          )

          const extraBuckets = ws.buckets?.filter(b => b.name !== ws.name && b.name.startsWith(ws.name)).map(b => b.name) || []

          form.value = {
            name: ws.name,
            members: normalizedMembers,
            clusterStatus: ws.cluster?.status ?? form.value.clusterStatus,
            extraBuckets: extraBuckets ?? form.value.extraBuckets,
          }

        } else
          message.value = 'Workspace Data not provided.'
      }
    }
  }
)


/** ---- Submit ---- */
const submit = async () => {
  if (!form.value.name) {
    message.value = 'Error: Workspace name is missing. Cannot save.'
    return
  }

  const prefix = form.value.name
  const invalidBuckets = form.value.extraBuckets.filter((b) => !!b && !b.startsWith(prefix))

  if (invalidBuckets.length > 0) {
    message.value = `Error: The following bucket names must start with '${prefix}': ${invalidBuckets.join(', ')}`
    return
  }

  try {
    await axios.put(`/workspaces/${encodeURIComponent(form.value.name)}`, form.value)
    message.value = 'Workspace updated successfully!'
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    message.value = `Error: Error saving workspace: ${msg}`
  }
}

</script>
