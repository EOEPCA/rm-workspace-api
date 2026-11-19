<template>
  <div class="q-pa-md overview-page">
    <div v-if="loading" class="row justify-center q-my-md">
      <q-spinner size="28px" />
    </div>
    <template v-if="overview">
      <div class="row items-center q-mb-md q-gutter-sm">
        <div class="text-h6">Workspaces</div>
        <q-space />
        <q-btn
          v-if="overview.is_admin"
          color="primary" no-caps icon="add" label="Create workspace"
          :loading="loadingChoices" :disable="busy" @click="openCreate"
        />
      </div>
      <q-banner v-if="pageError" class="bg-red-1 text-negative q-mb-md" rounded role="alert">
        {{ pageError }}
        <template #action>
          <q-btn v-if="refreshFailed" flat no-caps label="Retry" @click="refreshWorkspaces" />
        </template>
      </q-banner>
      <q-card>
        <q-list separator>
          <q-item v-for="workspace in overview.workspaces" :key="workspace.name">
            <q-item-section>
              <q-item-label>
                <q-btn flat no-caps color="primary" icon-right="open_in_new"
                       :label="workspace.name" :href="workspace.url" target="_top" />
              </q-item-label>
              <div v-if="workspace.sessions.length" class="q-ml-md">
                <q-btn v-for="session in workspace.sessions" :key="session.name"
                       flat dense no-caps color="grey-8" icon-right="open_in_new"
                       :label="`Datalab (${session.name})`" :href="session.url" target="_blank" rel="noopener noreferrer" />
              </div>
            </q-item-section>
            <q-item-section v-if="overview.is_admin" side>
              <q-btn flat round color="negative" icon="delete" :aria-label="`Delete workspace ${workspace.name}`"
                     :disable="busy || loadingChoices" @click="openDelete(workspace.name)">
                <q-tooltip>Delete workspace</q-tooltip>
              </q-btn>
            </q-item-section>
          </q-item>
          <q-item v-if="!overview.workspaces.length">
            <q-item-section class="text-grey-7">No workspaces available.</q-item-section>
          </q-item>
        </q-list>
      </q-card>

      <q-dialog v-model="createOpen" :persistent="busy">
        <q-card class="workspace-dialog">
          <q-form @submit="createWorkspace">
            <q-card-section class="text-h6">Create workspace</q-card-section>
            <q-card-section class="q-pt-none q-gutter-md">
              <div class="row no-wrap items-start">
                <span v-if="overview.workspace_name_prefix" class="workspace-name-prefix q-mr-sm">
                  {{ overview.workspace_name_prefix }}
                </span>
                <q-input
                    v-model="name" label="Workspace name" class="col" outlined autofocus stack-label hide-bottom-space
                    :aria-label="overview.workspace_name_prefix ? `Workspace name after ${overview.workspace_name_prefix}` : 'Workspace name'"
                    :error="nameEdited && !!nameError" :error-message="nameError"
                    :disable="busy" @update:model-value="nameEdited = true"
                />
              </div>
              <q-input v-model="owner" label="Owner username" outlined :disable="busy" :rules="[requiredOwner]" />
              <q-card v-for="provider in providers" :key="provider.provider" flat bordered>
                <q-card-section class="text-subtitle1">
                  {{ provider.provider === 'storage' ? 'Storage' : 'Datalab' }}
                </q-card-section>
                <q-card-section class="q-pt-none q-gutter-md">
                  <q-select v-if="provider.compositions.length > 1"
                            v-model="provider.composition" label="Composition" outlined
                            :options="provider.compositions" :disable="busy"
                            @update:model-value="provider.environment_name = ''" />
                  <q-input v-else :model-value="provider.composition" label="Composition" outlined readonly
                           bg-color="grey-2" />
                  <q-select v-if="overrideNames(provider).length"
                            v-model="provider.environment_name" label="Configuration" outlined
                            :options="overrideOptions(provider)" emit-value map-options :disable="busy" />
                  <q-input v-else :model-value="provider.composition" label="Configuration" outlined readonly bg-color="grey-2" />
                </q-card-section>
              </q-card>
              <q-banner v-if="createError" class="bg-red-1 text-negative" rounded role="alert">{{ createError }}</q-banner>
            </q-card-section>
            <q-card-actions align="right">
              <q-btn flat no-caps label="Cancel" :disable="busy" v-close-popup />
              <q-btn color="primary" no-caps label="Create" type="submit" :loading="busy" :disable="!canCreate" />
            </q-card-actions>
          </q-form>
        </q-card>
      </q-dialog>

      <q-dialog v-model="deleteOpen" :persistent="busy">
        <q-card class="workspace-dialog">
          <q-card-section class="text-h6">Delete workspace</q-card-section>
          <q-card-section class="q-pt-none">
            Delete <strong>{{ deletingName }}</strong> and its managed resources? This action cannot be undone.
            <q-banner v-if="deleteError" class="bg-red-1 text-negative q-mt-md" rounded role="alert">{{ deleteError }}</q-banner>
          </q-card-section>
          <q-card-actions align="right">
            <q-btn flat no-caps label="Cancel" :disable="busy" v-close-popup />
            <q-btn color="negative" no-caps label="Delete workspace" :loading="busy" @click="deleteWorkspace" />
          </q-card-actions>
        </q-card>
      </q-dialog>
    </template>
    <q-banner v-else-if="!loading" class="bg-red-1 text-negative" rounded>
      Workspace overview data is missing. Reload the page to try again.
    </q-banner>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import axios from 'axios'
import type { WorkspaceListItem, WorkspaceOverview, WorkspaceProviderChoices } from 'src/models/models'
import { useLuigiContext } from 'src/composables/useLuigi'
import { apiErrorMessage } from 'src/services/apiErrors'
import { workspaceNameError } from 'src/services/resourceNames'
import { loadWorkspaceProviders, workspaceCreatePayload } from 'src/services/workspaceLifecycle'

const overview = ref<WorkspaceOverview>()
const providers = ref<WorkspaceProviderChoices[]>([])
const name = ref('')
const owner = ref('')
const nameEdited = ref(false)
const createOpen = ref(false)
const deleteOpen = ref(false)
const deletingName = ref('')
const busy = ref(false)
const loadingChoices = ref(false)
const pageError = ref('')
const refreshFailed = ref(false)
const createError = ref('')
const deleteError = ref('')

const { loading } = useLuigiContext({
  onReady: ({ workspaceOverview }) => { overview.value = workspaceOverview },
})
const nameError = computed(() => workspaceNameError(name.value, overview.value?.workspace_name_prefix ?? ''))
const canCreate = computed(() => overview.value?.is_admin && !busy.value && !nameError.value && !!owner.value.trim() &&
  providers.value.length > 0 && providers.value.every(provider => !!provider.composition))

function requiredOwner(value: string) { return !!value.trim() || 'Enter an owner username.' }
function overrideNames(provider: WorkspaceProviderChoices) { return provider.environments[provider.composition] ?? [] }
function overrideOptions(provider: WorkspaceProviderChoices) {
  return [{ label: provider.composition, value: '' }, ...overrideNames(provider).map(value => ({ label: value, value }))]
}

async function openCreate() {
  if (!overview.value?.is_admin || loadingChoices.value || busy.value) return
  loadingChoices.value = true
  pageError.value = ''
  refreshFailed.value = false
  try {
    providers.value = await loadWorkspaceProviders(overview.value)
    name.value = ''
    owner.value = overview.value.username
    nameEdited.value = false
    createError.value = ''
    createOpen.value = true
  } catch (error) {
    pageError.value = apiErrorMessage(error)
  } finally {
    loadingChoices.value = false
  }
}

async function refreshWorkspaces() {
  if (!overview.value) return
  try {
    const response = await axios.get<WorkspaceListItem[]>(overview.value.workspaces_url, { headers: { Accept: 'application/json' } })
    overview.value.workspaces = response.data
    pageError.value = ''
    refreshFailed.value = false
  } catch (error) {
    pageError.value = `Could not refresh the workspace list: ${apiErrorMessage(error)}`
    refreshFailed.value = true
  }
}

async function createWorkspace() {
  nameEdited.value = true
  if (!canCreate.value || !overview.value) return
  busy.value = true
  createError.value = ''
  try {
    await axios.post(overview.value.workspaces_url, workspaceCreatePayload(name.value, owner.value, providers.value))
    createOpen.value = false
    await refreshWorkspaces()
  } catch (error) {
    createError.value = apiErrorMessage(error)
  } finally {
    busy.value = false
  }
}

function openDelete(workspaceName: string) {
  if (!overview.value?.is_admin || busy.value || loadingChoices.value) return
  deletingName.value = workspaceName
  deleteError.value = ''
  deleteOpen.value = true
}

async function deleteWorkspace() {
  if (!overview.value?.is_admin || busy.value) return
  busy.value = true
  deleteError.value = ''
  try {
    await axios.delete(`${overview.value.workspaces_url}/${encodeURIComponent(deletingName.value)}`)
    deleteOpen.value = false
    await refreshWorkspaces()
  } catch (error) {
    deleteError.value = apiErrorMessage(error)
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.overview-page { max-width: 1000px; margin: 0 auto; }
.workspace-dialog { width: 480px; max-width: calc(100vw - 32px); }
.workspace-name-prefix { flex-shrink: 0; padding-top: 26px; line-height: 20px; white-space: nowrap; }
</style>
