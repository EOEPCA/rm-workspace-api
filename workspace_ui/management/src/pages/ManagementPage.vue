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
          <!-- Tabs header -->
          <q-tabs
            v-model="activeTab"
            class="text-primary q-mb-md"
            align="justify"
            dense
            outside-arrows
            mobile-arrows
          >
            <q-tab name="members" label="Members" :alert="form.memberships.length === 0" />
            <q-tab name="buckets" label="Buckets" />
          </q-tabs>

          <q-separator />

          <!-- Tabs content -->
          <q-tab-panels v-model="activeTab" animated>
            <!-- MEMBERS TAB -->
            <q-tab-panel name="members">
              <div class="text-body1 q-mb-sm">Members</div>

              <div
                v-for="(member, index) in form.memberships"
                :key="'member-' + index"
                class="row items-center q-col-gutter-sm q-mb-xs"
              >
                <div class="col">
                  <q-input
                    v-model="member.member"
                    outlined
                    dense
                    hide-bottom-space
                    placeholder="user"
                    :readonly="!member.isNew"
                  />
                </div>
                <div class="col">
                  <q-input
                    v-model="member.creation_timestamp"
                    outlined
                    dense
                    hide-bottom-space
                    readonly
                  />
                </div>
                <div class="col-auto">
                  <q-btn
                    flat
                    round
                    dense
                    icon="delete"
                    color="negative"
                    @click="form.memberships.splice(index, 1)"
                  />
                </div>
              </div>

              <q-btn
                color="primary"
                flat
                no-caps
                class="q-mt-sm"
                @click="form.memberships.push({member:'', isNew: true} as Membership)"
              >
                <q-icon name="add" class="q-mr-sm" />
                Add Member
              </q-btn>
            </q-tab-panel>

            <!-- BUCKETS TAB -->
            <q-tab-panel name="buckets">
              <!-- Extra Buckets -->
              <div class="text-body1 q-mb-sm">Extra Buckets</div>
              <div
                v-for="(bucket, index) in form.extra_buckets"
                :key="'extra-bucket-' + index"
                class="row items-center q-col-gutter-sm q-mb-xs"
              >
                <div class="col">
                  <q-input
                    v-model="form.extra_buckets[index]"
                    outlined
                    dense
                    hide-bottom-space
                    placeholder="workspace-name-extra"
                  />
                </div>
                <div class="col-auto">
                  <q-btn
                    flat
                    round
                    dense
                    icon="delete"
                    color="negative"
                    @click="form.extra_buckets.splice(index, 1)"
                  />
                </div>
              </div>
              <q-btn
                color="primary"
                flat
                no-caps
                class="q-mt-sm q-mb-lg"
                @click="form.extra_buckets.push('')"
              >
                <q-icon name="add" class="q-mr-sm" />
                Add Extra Bucket
              </q-btn>

              <q-separator class="q-my-md" />

              <!-- Linked Buckets -->
              <div class="text-body1 q-mb-sm">Linked Buckets</div>
              <div
                v-for="(bucket, index) in form.linked_buckets"
                :key="'linked-bucket-' + index"
                class="row items-center q-col-gutter-sm q-mb-xs"
              >
                <div class="col">
                  <q-input
                    v-model="form.linked_buckets[index]"
                    outlined
                    dense
                    hide-bottom-space
                    placeholder="some-other-bucket"
                  />
                </div>
                <div class="col-auto">
                  <q-btn
                    flat
                    round
                    dense
                    icon="delete"
                    color="negative"
                    @click="form.linked_buckets.splice(index, 1)"
                  />
                </div>
              </div>
            </q-tab-panel>
          </q-tab-panels>

          <q-separator class="q-my-md" />

          <q-btn type="submit" color="primary" unelevated no-caps label="Save Changes" />
        </q-form>
      </q-card-section>
    </q-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import axios from 'axios'
import type {Membership, WorkspaceEdit, WorkspaceEditUI} from 'src/models/models'
import { useLuigiWorkspace } from 'src/composables/useLuigi'
import {useQuasar} from 'quasar'

const $q = useQuasar()

/** ---- State ---- */
const message = ref<string>('')

const form = ref<WorkspaceEditUI>({
  name: '',
  memberships: [],
  extra_buckets: [],
  linked_buckets: [],
})

/** Tabs */
const activeTab = ref<'members' | 'buckets'>('members')

/** ---- UI helpers ---- */
const isError = computed(() => message.value.startsWith('Error:'))
const displayMessage = computed(() =>
  isError.value ? message.value.substring(7) : message.value
)

const { loading } = useLuigiWorkspace({
  onReady: (ctx) => {
    if (ctx && ctx.workspace) {
      const ws = ctx.workspace
      if (ws.name) {
        message.value = `Using pre-loaded data for workspace: ${ws.name} (${ws.version})`
        form.value = {
          name: ws.name,
          memberships: (ctx.memberships ?? []).map(m => ({ ...m, isNew: false })),
          extra_buckets:
            ws.storage?.buckets?.filter((b) => b !== ws.name && b.startsWith(ws.name)) ?? [],
          linked_buckets: ws.storage?.buckets?.filter((b) => !b.startsWith(ws.name)) ?? [],
        }
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
    (b) => b === workspaceName || !b.startsWith(workspaceName)
  )

  if (invalidBuckets.length > 0) {
    message.value = `Error: The following bucket names must start with '${workspaceName}': ${invalidBuckets.join(', ')}`
    activeTab.value = 'buckets'
    return
  }

  const workspaceEdit = {
    name: workspaceName,
    members: (form.value.memberships ?? []).map(m => m.member),
    extra_buckets: form.value.extra_buckets,
    linked_buckets: form.value.linked_buckets,
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
