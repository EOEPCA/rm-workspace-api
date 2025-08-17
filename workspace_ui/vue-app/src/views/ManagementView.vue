<template>
  <v-container style="max-width: 700px;">
    <v-card>
      <v-card-text>
        <v-alert v-if="message && message.startsWith('Error:')" type="error" prominent class="mb-4" :text="message.substring(7)" />
        <v-alert v-else-if="message" type="success" prominent class="mb-4" :text="message" />

        <v-progress-circular indeterminate color="primary" v-if="loading" class="d-block mx-auto my-4" />

        <v-form v-if="!loading && form.name" @submit.prevent="submit">
          <v-select
            v-model="form.clusterStatus"
            :items="['active', 'suspended']"
            label="Cluster Status"
            variant="outlined"
            class="mb-4"
          />

          <div class="mb-4">
            <v-label class="mb-2 d-block font-weight-medium">Members</v-label>
            <v-row v-for="(member, index) in form.members" :key="'member-' + index" dense align="center" class="mb-1">
              <v-col cols="12">
                <v-text-field v-model="form.members[index]" variant="outlined" density="compact" hide-details />
              </v-col>
            </v-row>
            <v-btn color="primary" variant="text" @click="form.members.push('')" class="mt-2">
              <v-icon start>mdi-plus</v-icon>Add Member
            </v-btn>
          </div>

          <div class="mb-4">
            <v-label class="mb-2 d-block font-weight-medium">Extra Buckets</v-label>
            <v-row v-for="(source, index) in form.extraBuckets" :key="'source-' + index" dense align="center" class="mb-1">
              <v-col cols="12">
                <v-text-field v-model="form.extraBuckets[index]" variant="outlined" density="compact" hide-details />
              </v-col>
            </v-row>
            <v-btn color="primary" variant="text" @click="form.extraBuckets.push('')" class="mt-2">
              <v-icon start>mdi-plus</v-icon>Add Source
            </v-btn>
          </div>

          <v-btn type="submit" color="primary" size="large">Save Changes</v-btn>
        </v-form>
      </v-card-text>
    </v-card>
  </v-container>
</template>


<script setup>
import { ref, onMounted } from 'vue'
import LuigiClient from '@luigi-project/client'
import axios from 'axios'

const message = ref('')
const loading = ref(true)

const form = ref({
  name: '',
  members: [],
  clusterStatus: 'active',
  extraBuckets: []
})

onMounted(() => {
  LuigiClient.addInitListener((ctx) => {
    if (ctx.workspaceName && ctx.edit) {
      message.value = `Using pre-loaded data for workspace: ${ctx.workspaceName}`
      form.value = {
        ...form.value,
        ...ctx.edit,
        name: ctx.workspaceName,
        members: (ctx.edit.members || []).map(m => (typeof m === 'string' ? m : m.name))
      }
    } else {
      message.value = `Currently not possible to edit workspace.`
    }
    loading.value = false
  })
})

const submit = async () => {
  if (!form.value.name) {
    message.value = 'Error: Workspace name is missing. Cannot save.'
    return
  }

  const prefix = form.value.name
  const invalidBuckets = form.value.extraBuckets.filter(b => !b.startsWith(prefix))

  if (invalidBuckets.length > 0) {
    message.value = `Error: The following bucket names must start with '${prefix}': ${invalidBuckets.join(', ')}`
    return
  }

  try {
    await axios.put(`/workspaces/${form.value.name}`, form.value)
    message.value = 'Workspace updated successfully!'
  } catch (err) {
    message.value = `Error saving workspace: ${err.message}`
  }
}
</script>