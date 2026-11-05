import type { StoreType, UserPermission, VCluster } from '../models/models'

export type ManagementTab = 'members' | 'buckets' | 'bucketRequests' | 'stores' | 'vclusters' | 'sessions'

export function availableManagementTabs(
  permissions: readonly UserPermission[],
  storageAvailable: boolean,
  datalabAvailable: boolean,
  storeTypes: readonly StoreType[],
  vclusters: readonly VCluster[],
): ManagementTab[] {
  const tabs: ManagementTab[] = []
  if (datalabAvailable && permissions.includes('VIEW_MEMBERS')) tabs.push('members')
  if (storageAvailable && permissions.includes('VIEW_BUCKETS')) tabs.push('buckets', 'bucketRequests')
  if (datalabAvailable && storeTypes.length > 0 && permissions.includes('VIEW_STORES')) tabs.push('stores')
  if (datalabAvailable && vclusters.some(cluster => cluster.name === 'vc0') && permissions.includes('VIEW_VCLUSTERS')) tabs.push('vclusters')
  if (datalabAvailable && permissions.includes('VIEW_SESSIONS')) tabs.push('sessions')
  return tabs
}
