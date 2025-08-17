<template>
  <v-container>
    <v-progress-circular
      v-if="loading"
      indeterminate
      color="primary"
      class="d-block mx-auto my-4"
    />

    <v-alert
      v-if="errorMessage"
      type="error"
      :text="errorMessage"
      prominent
      class="mb-4"
    />

    <div v-if="!loading && !errorMessage && workspace">
      <!-- Workspace Header -->
      <v-card class="mb-4">
        <v-card-text>
          <v-chip
            :color="workspace.status === 'ready' ? 'green' : 'orange'"
            variant="elevated"
          >
            <v-icon start icon="mdi-information-outline"></v-icon>
            Status: {{ workspace.status }}
          </v-chip>
        </v-card-text>
      </v-card>

      <!-- Storage Credentials -->
      <v-card
        v-if="workspace.storage?.credentials && Object.keys(workspace.storage.credentials).length > 0"
        class="mb-4"
      >
        <v-card-title>Storage Credentials</v-card-title>
        <v-card-text>
          <pre class="pa-3">{{ JSON.stringify(workspace.storage.credentials, null, 2) }}</pre>
        </v-card-text>
      </v-card>

      <!-- Members Table -->
      <v-card v-if="workspace.members?.length" class="mb-4">
        <v-card-title>Members</v-card-title>
        <v-table>
          <!-- <thead>
            <tr>
              <th class="text-left">Name</th>
            </tr>
          </thead> -->
          <tbody>
            <tr v-for="member in workspace.members" :key="member.name">
              <td>{{ member.name }}</td>
            </tr>
          </tbody>
        </v-table>
      </v-card>
    </div>

    <!-- Fallback if no workspace data -->
    <v-sheet
      v-if="!loading && !errorMessage && !workspace"
      class="pa-4 text-center text-grey-darken-1"
    >
      <p>No workspace data loaded.</p>
    </v-sheet>
  </v-container>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import LuigiClient from '@luigi-project/client';

const loading = ref(true);
const errorMessage = ref('');
const workspace = ref(null);

onMounted(() => {
  LuigiClient.addInitListener((initialContext) => {
    loading.value = false;
    if (initialContext?.workspace) {
      workspace.value = initialContext.workspace;
      console.log(workspace.value);
    } else {
      errorMessage.value = 'Workspace Data not accessible.';
    }
  });
});
</script>

<style scoped>
pre {
  background-color: #f5f5f5;
  border-radius: 4px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
