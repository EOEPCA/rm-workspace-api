<template>
  <q-list separator dense role="group">
    <template v-for="connection in connections" :key="connection.type + ':' + connection.name">
      <q-item v-if="flat" dense>
        <q-item-section>
          <div class="connection-title q-pa-sm">
            <span class="text-weight-medium">{{ connection.name }}</span>
            <q-badge :color="connection.ready ? 'green-9' : 'grey-7'">{{ connection.ready ? 'Ready' : 'Preparing' }}</q-badge>
          </div>
          <div v-if="connection.endpoint" class="connection-endpoint q-px-sm">{{ connection.endpoint }}</div>
          <div v-if="connection.region" class="text-caption q-px-sm">Region: {{ connection.region }}</div>
          <CredentialValues v-if="connection.ready && connection.credentials" :credentials="connection.credentials" :download-name="downloadName(connection)" />
          <div v-else class="q-pa-md text-grey-7">{{ unavailableMessage(connection) }}</div>
        </q-item-section>
      </q-item>
      <q-expansion-item v-else dense dense-toggle toggle-aria-label="">
        <template #header>
          <q-item-section class="connection-summary">
            <div class="connection-title">
              <span class="text-weight-medium">{{ connection.type === 'vcluster' ? connection.instance : connection.name }}</span>
              <q-badge v-if="connection.group" outline color="grey-8">{{ connection.group }}</q-badge>
              <q-badge :color="connection.ready ? 'green-9' : 'grey-7'">{{ connection.ready ? 'Ready' : 'Preparing' }}</q-badge>
            </div>
            <dl v-if="connection.target_namespace || connection.role" class="connection-details">
              <div v-if="connection.target_namespace">
                <dt>Namespace</dt>
                <dd>{{ connection.target_namespace === '*' ? 'All namespaces' : connection.target_namespace }}</dd>
              </div>
              <div v-if="connection.role">
                <dt>Role</dt>
                <dd>{{ connection.role }}</dd>
              </div>
            </dl>
            <div v-if="connection.endpoint" class="connection-endpoint">{{ connection.endpoint }}</div>
            <div v-if="connection.region" class="text-caption">Region: {{ connection.region }}</div>
            <div v-if="'issuer_url' in connection" class="connection-endpoint">{{ connection.issuer_url }}</div>
          </q-item-section>
      </template>
      <CredentialValues
        v-if="connection.ready && connection.credentials"
        :credentials="connection.credentials"
        :download-name="downloadName(connection)"
      />
      <div v-else class="q-pa-md text-grey-7">{{ unavailableMessage(connection) }}</div>
    </q-expansion-item>
    </template>
  </q-list>
</template>

<script setup lang="ts">
import type { Connection, OAuth2Connection } from 'src/models/models'
import CredentialValues from 'src/components/CredentialValues.vue'

const props = defineProps<{ connections: (Connection | OAuth2Connection)[]; workspaceName: string; flat?: boolean }>()

function downloadName(connection: Connection): string {
  return [props.workspaceName, connection.type, connection.name].join('-').replace(/[^a-zA-Z0-9._-]/g, '-') + '.kubeconfig'
}

function unavailableMessage(connection: Connection): string {
  if (!connection.ready) return 'This connection is still being prepared.'
  if (connection.resolution_error === 'oauth2_reference') return 'Use the OAuth2 section for these credentials.'
  if (connection.resolution_error) return 'Credentials are not available. Reload the page to try again.'
  return 'Credentials are not loaded.'
}
</script>

<style scoped>
.connection-summary {
  min-width: 0;
}

.connection-title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  overflow-wrap: anywhere;
}

.connection-title .q-badge {
  white-space: normal;
}

.connection-details {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 24px;
  margin: 8px 0;
  font-size: 12px;
}

.connection-details > div {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.connection-details dt {
  font-weight: 500;
}

.connection-details dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.connection-endpoint {
  margin-top: 4px;
  font-size: 12px;
  overflow-wrap: anywhere;
}
</style>
