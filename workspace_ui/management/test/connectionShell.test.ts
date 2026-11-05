import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'

const shell = readFileSync(new URL('../../luigi-shell/ui.html', import.meta.url), 'utf8')

async function openShell(permissions: string[], query = '', loadFails = false) {
  const workspace = { name: 'ws-alice', user: { name: 'alice', permissions }, datalab: { connections: [], oauth2: [] } }
  const resolved = {
    ...workspace,
    datalab: {
      connections: [{ group: 'administrators', role: 'cluster-admin', credentials: { kubeconfig: 'test-config' } }],
      oauth2: [{ name: 'ws-alice', type: 'client', ready: true, credentials: { clientSecret: 'test-value' } }],
    },
  }
  const source = shell
    .replace('{{ workspace_data | safe }}', Buffer.from(JSON.stringify(workspace)).toString('base64'))
    .replace('{{ endpoints_data | safe }}', Buffer.from('[]').toString('base64'))
    .replace('{{ frontend_url | safe }}', '/ui/management')
    .match(/<script>([\s\S]+)<\/script>/)?.[1]
  assert.ok(source)
  const requests: { url: URL; options: { headers: { Accept: string }; cache: string } }[] = []
  const body = { textContent: '' }
  let context: typeof workspace | undefined
  let sandboxRules: string[] = []
  await vm.runInNewContext(source, {
    URL,
    atob,
    document: { body },
    window: { location: { href: `https://workspace.example.org/workspaces/ws-alice${query}` } },
    fetch: async (url: URL, options: { headers: { Accept: string }; cache: string }) => {
      requests.push({ url, options })
      return { ok: !loadFails, json: async () => resolved }
    },
    Luigi: {
      setConfig: (config: {
        navigation: { nodes: () => { context: { workspace: typeof workspace } }[] }
        settings: { customSandboxRules?: string[] }
      }) => {
        context = config.navigation.nodes()[0]?.context.workspace
        sandboxRules = config.settings.customSandboxRules ?? []
      },
    },
  })
  return { requests, context, sandboxRules, message: body.textContent }
}

const humanPermissions = ['VIEW_CONNECTION_CREDENTIALS', 'VIEW_OAUTH2_CREDENTIALS']

test('human dashboard loads connections and OAuth2 in one request', async () => {
  const { requests, context } = await openShell(humanPermissions)
  assert.equal(requests.length, 1)
  assert.equal(requests[0]?.url.searchParams.get('resolve_connections'), '*')
  assert.equal(requests[0]?.url.searchParams.get('resolve_oauth2'), '*')
  assert.equal(requests[0]?.options.headers.Accept, 'application/json')
  assert.equal(requests[0]?.options.cache, 'no-store')
  assert.equal(context?.datalab.connections.length, 1)
  assert.equal(context?.datalab.oauth2.length, 1)
})

test('hosted and demo dashboards permit kubeconfig downloads from the iframe', async () => {
  const { sandboxRules } = await openShell(humanPermissions)
  assert.ok(sandboxRules.includes('allow-downloads'))

  const standaloneScript = readFileSync(new URL('../../luigi-shell/standalone/index.html', import.meta.url), 'utf8')
    .match(/<script type="module">([\s\S]+)<\/script>/)?.[1]
  assert.ok(standaloneScript)
  const standalone = standaloneScript.replace(/import .* from .*;/, '')
  let demoRules: string[] = []
  vm.runInNewContext(standalone, {
    workspace: { name: 'ws-alice', user: { name: 'alice', permissions: [] } },
    endpointsData: [],
    Luigi: {
      setConfig: (config: { settings: { customSandboxRules?: string[] } }) => {
        demoRules = config.settings.customSandboxRules ?? []
      },
    },
  })
  assert.ok(demoRules.includes('allow-downloads'))
})

test('automation dashboard requests connections without OAuth2 resolution', async () => {
  const { requests } = await openShell(['VIEW_CONNECTION_CREDENTIALS'])
  assert.equal(requests.length, 1)
  assert.equal(requests[0]?.url.searchParams.get('resolve_connections'), '*')
  assert.equal(requests[0]?.url.searchParams.has('resolve_oauth2'), false)
})

test('dashboard does not request secrets without resolution permissions', async () => {
  const { requests, context } = await openShell([])
  assert.equal(requests.length, 0)
  assert.equal(context?.datalab.connections.length, 0)
})

for (const value of ['none', 's3:primary&resolve_connections=postgres:pg0']) {
  test(`UI preserves an explicit resolve_connections=${value} request`, async () => {
    const { requests } = await openShell(humanPermissions, `?resolve_connections=${value}`)
    assert.equal(requests.length, 1)
    assert.deepEqual(requests[0]?.url.searchParams.getAll('resolve_connections'), value === 'none' ? ['none'] : ['s3:primary', 'postgres:pg0'])
    assert.equal(requests[0]?.url.searchParams.get('resolve_oauth2'), '*')
  })
}

test('UI preserves explicit OAuth2 selection while loading all connections', async () => {
  const { requests } = await openShell(humanPermissions, '?resolve_oauth2=client:ws-alice')
  assert.equal(requests.length, 1)
  assert.equal(requests[0]?.url.searchParams.get('resolve_connections'), '*')
  assert.equal(requests[0]?.url.searchParams.get('resolve_oauth2'), 'client:ws-alice')
})

test('UI uses embedded details when both selectors were supplied', async () => {
  const { requests } = await openShell(humanPermissions, '?resolve_connections=*&resolve_oauth2=*')
  assert.equal(requests.length, 0)
})


test('dashboard stops when credential loading fails', async () => {
  const { requests, context, message } = await openShell(humanPermissions, '', true)
  assert.equal(requests.length, 1)
  assert.equal(context, undefined)
  assert.equal(message, 'Could not load workspace details. Reload the page to try again.')
})
