<template>
  <div class="q-pa-md">
    <!-- Loading -->
    <div v-if="loading" class="row justify-center q-my-md">
      <q-spinner size="28px" />
    </div>

    <!-- Error -->
    <q-banner v-if="errorMessage" class="bg-red-1 text-negative q-mb-md" dense>
      {{ errorMessage }}
    </q-banner>

    <!-- Workspace Content -->
    <div v-if="!loading && !errorMessage && workspace">
      <!-- Workspace Header -->
      <q-card class="q-mb-md">
        <q-card-section>
          <q-chip
            :color="workspace.status === 'ready' ? 'green' : 'orange'"
            text-color="white"
            square
          >
            <q-icon name="info" class="q-mr-sm" />
            Status: {{ workspace.status }}
          </q-chip>
        </q-card-section>
      </q-card>

      <!-- Storage Credentials -->
      <q-card
        v-if="hasCredentials"
        class="q-mb-md"
      >
        <q-card-section class="text-subtitle1">
          Storage Credentials
        </q-card-section>
        <q-separator />
        <q-card-section>
          <pre class="q-pa-md bg-grey-2 rounded-borders">{{ prettyCredentials }}</pre>
        </q-card-section>
      </q-card>

      <!-- Members Table -->
      <q-card v-if="workspace.members?.length" class="q-mb-md">
        <q-card-section class="text-subtitle1">Members</q-card-section>
        <q-separator />
        <q-card-section class="q-pa-none">
          <q-markup-table flat>
            <thead>
            <tr>
              <th class="text-left">Name</th>
            </tr>
            </thead>
            <tbody>
            <tr v-for="member in workspace.members" :key="member.name">
              <td>{{ member.name }}</td>
            </tr>
            </tbody>
          </q-markup-table>
        </q-card-section>
      </q-card>
    </div>

    <!-- Fallback if no workspace data -->
    <div v-if="!loading && !errorMessage && !workspace" class="q-pa-md text-center text-grey-7">
      <p>No workspace data loaded.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'

/** ---- Types ---- */
type WorkspaceStatus = 'ready' | 'pending' | 'error'

interface Member {
  name: string
  // add other fields if they exist
}

interface StorageInfo {
  credentials?: Record<string, unknown>
}

interface Workspace {
  status: WorkspaceStatus
  members?: Member[]
  storage?: StorageInfo
  // add other fields if they exist (id, name, etc.)
}

/** Narrowed public surface we need from Luigi */
interface LuigiClientLike {
  addInitListener?: (cb: (ctx: Record<string, unknown>, origin?: string) => void, disableTpcCheck?: boolean) => void
  getContext?: () => Record<string, unknown>
  uxManager?: () => unknown
}

/** Tiny guard for uxManager */
const isUxManager = (v: unknown): v is { setViewReady?: () => void } =>
  typeof v === 'object' && v !== null && 'setViewReady' in v

/** ---- State ---- */
const loading = ref<boolean>(true)
const errorMessage = ref<string>('')
const workspace = ref<Workspace | null>(null)

/** ---- Computed helpers ---- */
const hasCredentials = computed<boolean>(() => {
  const creds = workspace.value?.storage?.credentials
  return !!creds && Object.keys(creds).length > 0
})

const prettyCredentials = computed<string>(() =>
  JSON.stringify(workspace.value?.storage?.credentials ?? {}, null, 2)
)

/** ---- Luigi bootstrap (safe & typed) ---- */
async function initLuigi() {
  let LuigiClient: LuigiClientLike | null = null

  try {
    // dynamic import to avoid hard dependency/type conflicts
    const mod = await import('@luigi-project/client')
    LuigiClient = (mod as unknown as { default: unknown }).default as LuigiClientLike
  } catch {
    // optional global fallback if the shell exposes it
    const w = window as unknown as { LuigiClient?: LuigiClientLike }
    LuigiClient = w.LuigiClient ?? null
  }

  // If not running under Luigi, finish gracefully
  if (!LuigiClient) {
    loading.value = false
    errorMessage.value = ''
    workspace.value = null
    return
  }

  // Use init listener as your source of truth
  LuigiClient.addInitListener?.((initialContext: Record<string, unknown>) => {
    loading.value = false

    const ws = (initialContext as { workspace?: unknown }).workspace
    if (ws && typeof ws === 'object') {
      workspace.value = ws as Workspace
      const ux = LuigiClient?.uxManager?.()
      if (isUxManager(ux)) ux.setViewReady?.()
    } else {
      errorMessage.value = 'Workspace Data not accessible.'
    }
  })
}

onMounted(() => {
  void initLuigi()
})
</script>

<style scoped>
pre {
  border-radius: 4px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
