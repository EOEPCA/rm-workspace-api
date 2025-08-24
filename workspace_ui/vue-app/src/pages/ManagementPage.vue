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
            label="Cluster Status"
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
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'
import type { LuigiClientLike } from 'src/types/luigi' // from our earlier definitions

/** ---- Types ---- */
type ClusterStatus = 'active' | 'suspended'

interface WorkspaceEdit {
  name: string
  members: string[]
  clusterStatus: ClusterStatus
  extraBuckets: string[]
}

type InitCtx = {
  workspaceName?: string
  edit?: {
    name?: string
    members?: Array<string | { name: string }>
    clusterStatus?: ClusterStatus
    extraBuckets?: string[]
  }
}

/** ---- State ---- */
const message = ref<string>('')
const loading = ref<boolean>(true)

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

/** ---- Luigi bootstrap (typed + safe) ---- */
async function initLuigi() {
  let LuigiClient: LuigiClientLike | null = null

  try {
    const mod = await import('@luigi-project/client')
    LuigiClient = (mod as unknown as { default: unknown }).default as LuigiClientLike
  } catch {
    const w = window as unknown as { LuigiClient?: LuigiClientLike }
    LuigiClient = w.LuigiClient ?? null
  }

  if (!LuigiClient) {
    // Standalone (outside Luigi) -> cannot edit
    message.value = 'Currently not possible to edit workspace.'
    loading.value = false
    return
  }

  LuigiClient.addInitListener?.((ctxUnknown: Record<string, unknown>) => {
    const ctx = ctxUnknown as InitCtx

    if (ctx.workspaceName && ctx.edit) {
      message.value = `Using pre-loaded data for workspace: ${ctx.workspaceName}`

      const rawMembers = Array.isArray(ctx.edit.members) ? ctx.edit.members : []
      const normalizedMembers = rawMembers.map((m) =>
        typeof m === 'string' ? m : (m?.name ?? '')
      )

      form.value = {
        name: ctx.workspaceName,
        clusterStatus: ctx.edit.clusterStatus ?? form.value.clusterStatus,
        extraBuckets: ctx.edit.extraBuckets ?? form.value.extraBuckets,
        members: normalizedMembers
      }
    } else {
      message.value = 'Currently not possible to edit workspace.'
    }

    loading.value = false
  })
}

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

onMounted(() => {
  void initLuigi()
})
</script>
