import type { Connection, Store, StoreType } from '../models/models'

const connectionTypes: Record<StoreType, string> = {
  database: 'postgres',
  document: 'mongo',
  cache: 'redis',
}

export function connectionsForStore(store: Pick<Store, 'type' | 'instance'>, connections: readonly Connection[]): Connection[] {
  return connections.filter(connection => connection.type === connectionTypes[store.type] && connection.name === store.instance)
}

export function otherConnections(connections: readonly Connection[], stores: readonly Store[], showBuckets: boolean): Connection[] {
  const assigned = new Set(stores.flatMap(store => connectionsForStore(store, connections)))
  return connections.filter(connection =>
    connection.type !== 'vcluster' &&
    connection.type !== 'qdrant' &&
    !(showBuckets && connection.type === 's3' && connection.name === 'primary') &&
    !assigned.has(connection)
  )
}

export function storeTypeLabel(type: StoreType): string {
  return { database: 'PostgreSQL', document: 'MongoDB', cache: 'Redis' }[type]
}
