<template>
  <div class="q-pa-md">
    <!-- Loading -->
    <div v-if="loading" class="row justify-center q-my-md">
      <q-spinner size="28px"/>
    </div>

    <!-- Error -->
    <q-banner v-if="errorMessage" class="bg-red-1 text-negative q-mb-md" dense>
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
      </q-card>

      <!-- Storage Credentials -->
      <q-card
        v-if="hasCredentials"
        class="q-mb-md"
      >
        <q-card-section class="text-subtitle1">
          Storage Credentials
        </q-card-section>
        <q-separator/>
        <q-card-section>
          <pre class="q-pa-md bg-grey-2 rounded-borders">{{ prettyCredentials }}</pre>
        </q-card-section>
      </q-card>

      <!-- Members Table -->
      <q-card v-if="ws.datalab?.memberships?.length" class="q-mb-md">
        <q-card-section class="text-subtitle1">Members</q-card-section>
        <q-separator/>
        <q-card-section class="q-pa-none">
          <q-markup-table flat>
            <thead>
            <tr>
              <th class="text-left">Name</th>
            </tr>
            </thead>
            <tbody>
            <tr v-for="membership in ws.datalab?.memberships" :key="membership.member">
              <td>{{ membership.member }}</td>
            </tr>
            </tbody>
          </q-markup-table>
        </q-card-section>
      </q-card>

      <!-- Buckets Table -->
      <q-card v-if="ws.storage?.buckets?.length" class="q-mb-md">
        <q-card-section class="text-subtitle1">Buckets</q-card-section>
        <q-separator/>
        <q-card-section class="q-pa-none">
          <q-markup-table flat>
            <thead>
              <tr>
                <th class="text-left">Bucket Name</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="bucket in ws.storage?.buckets || []" :key="bucket">
                <td>{{ bucket }}</td>
              </tr>
            </tbody>
          </q-markup-table>
        </q-card-section>
      </q-card>
    </div>

    <!-- Fallback if no workspace data -->
    <div v-if="!loading && !errorMessage && !ws" class="q-pa-md text-center text-grey-7">
      <p>No workspace data loaded.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import {computed, ref} from 'vue'
import {useLuigiWorkspace} from 'src/composables/useLuigi'
import type {Workspace} from 'src/models/models'

/** ---- State ---- */
// const loading = ref<boolean>(true)
const errorMessage = ref<string>('')
const ws = ref<Workspace | null>(null)

/** ---- Computed helpers ---- */
const hasCredentials = computed<boolean>(() => {
  const creds = ws.value?.storage?.credentials
  return !!creds && Object.keys(creds).length > 0
})

const prettyCredentials = computed<string>(() =>
  JSON.stringify(ws.value?.storage?.credentials ?? {}, null, 2)
)

const {
  loading,
} = useLuigiWorkspace({
    onReady: (ctx) => {
//      console.log('Workspace initialized:', ws.name)
      if (!ctx || !ctx.workspace) {
        errorMessage.value = 'Workspace Data not provided.'
      } else {
        ws.value = ctx.workspace
      }
    }
  }
)

</script>

<style scoped>
pre {
  border-radius: 4px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
