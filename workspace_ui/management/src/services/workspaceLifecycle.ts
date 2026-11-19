import axios from 'axios'
import type { WorkspaceCreate, WorkspaceOverview, WorkspaceProviderChoices } from '../models/models'

export async function loadWorkspaceProviders(overview: WorkspaceOverview): Promise<WorkspaceProviderChoices[]> {
  const providers = await Promise.all((['storage', 'datalab'] as const).map(async provider => {
    const { data } = await axios.get<{ available: boolean; compositions: string[] }>(overview.compositions_url, {
      params: { provider }, headers: { Accept: 'application/json', 'Cache-Control': 'no-cache' },
    })
    if (!data.available) return null
    if (!data.compositions.length) throw new Error(`No ${provider} compositions are available.`)
    const environments = await Promise.all(data.compositions.map(async composition => {
      const response = await axios.get<string[]>(overview.environments_url, {
        params: { provider, composition }, headers: { Accept: 'application/json', 'Cache-Control': 'no-cache' },
      })
      return [composition, response.data.filter(name => name !== composition)] as const
    }))
    return {
      provider,
      compositions: data.compositions,
      composition: data.compositions.length === 1 ? data.compositions[0]! : '',
      environments: Object.fromEntries(environments),
      environment_name: '',
    }
  }))
  const available = providers.filter(provider => provider !== null)
  if (!available.length) throw new Error('No workspace provider is available.')
  return available
}

export function workspaceCreatePayload(name: string, owner: string, providers: WorkspaceProviderChoices[]): WorkspaceCreate {
  return {
    preferred_name: name,
    default_owner: owner,
    ...Object.fromEntries(providers.map(provider => [provider.provider, {
      composition: provider.composition,
      ...(provider.environment_name ? { environment_name: provider.environment_name } : {}),
    }])),
  }
}
