<template>
  <div class="q-pa-md credential-values">
    <template v-if="credentials.kubeconfig">
      <div class="row q-gutter-sm q-mb-sm">
        <q-btn outline no-caps icon="content_copy" label="Copy kubeconfig" @click="copy(credentials.kubeconfig, 'Kubeconfig')" />
        <q-btn outline no-caps icon="download" label="Download kubeconfig" @click="download" />
      </div>
      <details class="q-mb-md configuration-preview">
        <summary>Show kubeconfig</summary>
        <pre>{{ credentials.kubeconfig }}</pre>
      </details>
    </template>
    <q-input
      v-for="field in fields"
      :key="field.name"
      :model-value="field.value"
      :label="field.name"
      :type="isSecret(field.name) && !visible[field.name] ? 'password' : 'text'"
      outlined
      dense
      readonly
      class="q-mb-sm"
    >
      <template #append>
        <q-btn
          v-if="isSecret(field.name)"
          flat round dense
          :icon="visible[field.name] ? 'visibility_off' : 'visibility'"
          :aria-label="(visible[field.name] ? 'Hide ' : 'Show ') + field.name"
          @click="visible[field.name] = !visible[field.name]"
        />
        <q-btn flat round dense icon="content_copy" :aria-label="'Copy ' + field.name" @click="copy(field.value, field.name)">
          <q-tooltip>Copy {{ field.name }}</q-tooltip>
        </q-btn>
      </template>
    </q-input>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { copyToClipboard, exportFile, useQuasar } from 'quasar'

const props = defineProps<{ credentials: Record<string, string>; downloadName: string }>()
const $q = useQuasar()
const visible = ref<Record<string, boolean>>({})
const fields = computed(() => Object.entries(props.credentials)
  .filter(([name]) => name !== 'kubeconfig')
  .map(([name, value]) => ({ name, value })))

function isSecret(name: string): boolean {
  return /secret|password|token/i.test(name)
}

async function copy(value: string, name: string) {
  try {
    await copyToClipboard(value)
    $q.notify({ type: 'positive', color: 'green-9', message: name + ' copied.' })
  } catch {
    $q.notify({ type: 'negative', message: 'Could not copy. Select the value manually.' })
  }
}

function download() {
  const result = exportFile(props.downloadName, props.credentials.kubeconfig ?? '', 'text/plain;charset=utf-8')
  if (result !== true) $q.notify({ type: 'negative', message: 'Could not download the kubeconfig.' })
}
</script>

<style scoped>
.credential-values {
  min-width: 0;
}

.configuration-preview summary {
  cursor: pointer;
  padding: 8px 0;
}

.configuration-preview pre {
  max-height: 24rem;
  overflow: auto;
  margin: 0;
  padding: 12px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  border: 1px solid currentColor;
  font-size: 12px;
}
</style>
