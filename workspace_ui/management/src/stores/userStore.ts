import { defineStore } from 'pinia'
import type {UserPermission, WorkspaceUser} from 'src/models/models'

interface UserState {
  user: WorkspaceUser | null
}

function ensureViewPermissions(perms: UserPermission[]): UserPermission[] {
  const set = new Set<UserPermission>(perms)

  // MANAGE implies VIEW
  if (set.has('MANAGE_BUCKETS')) set.add('VIEW_BUCKETS')
  if (set.has('MANAGE_MEMBERS')) set.add('VIEW_MEMBERS')

  return Array.from(set)
}

export const useUserStore = defineStore('user', {
  state: (): UserState => ({
    user: null,
  }),

  getters: {
    // Convenience: always returns an array (never null/undefined).
    permissions(state): UserPermission[] {
      return state.user?.permissions ?? []
    },

    isLoggedIn(state): boolean {
      return !!state.user?.name
    },

    // Generic permission check
    hasPermission(): (perm: UserPermission) => boolean {
      return (perm: UserPermission) => this.permissions.includes(perm)
    },

    // "Any-of" helper for sections that accept multiple permissions
    hasAnyPermission(): (perms: UserPermission[]) => boolean {
      return (perms: UserPermission[]) => perms.some(p => this.permissions.includes(p))
    },

    // Opinionated, readable flags for the UI
    canViewBuckets(): boolean {
      return this.permissions.includes('VIEW_BUCKETS')
    },
    canViewBucketCredentials(): boolean {
      return this.permissions.includes('VIEW_BUCKET_CREDENTIALS')
    },
    canViewMembers(): boolean {
      return this.permissions.includes('VIEW_MEMBERS')
    },
    canManageMembers(): boolean {
      return this.permissions.includes('MANAGE_MEMBERS')
    },
    canManageBuckets(): boolean {
      return this.permissions.includes('MANAGE_BUCKETS')
    },
  },

  actions: {
    setUser(user: WorkspaceUser | null) {
      if (!user) {
        this.user = null
        return
      }

      const normalizedPermissions = ensureViewPermissions(user.permissions ?? [])

      this.user = {
        ...user,
        permissions: normalizedPermissions,
      }
    },
    clearUser() {
      this.user = null
    },
  },
})
