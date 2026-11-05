import { defineStore } from 'pinia'
import type {UserPermission, WorkspaceUser} from 'src/models/models'

interface UserState {
  user: WorkspaceUser | null
}

export const useUserStore = defineStore('user', {
  state: (): UserState => ({
    user: null,
  }),

  getters: {
    permissions(state): UserPermission[] {
      return state.user?.permissions ?? []
    },

    isLoggedIn(state): boolean {
      return !!state.user?.name
    },

    hasPermission(): (perm: UserPermission) => boolean {
      return (perm: UserPermission) => this.permissions.includes(perm)
    },

    hasAnyPermission(): (perms: UserPermission[]) => boolean {
      return (perms: UserPermission[]) => perms.some(p => this.permissions.includes(p))
    },

    canViewBuckets(): boolean {
      return this.permissions.includes('VIEW_BUCKETS')
    },
    canViewConnectionCredentials(): boolean {
      return this.permissions.includes('VIEW_CONNECTION_CREDENTIALS')
    },
    canViewOAuth2Credentials(): boolean {
      return this.permissions.includes('VIEW_OAUTH2_CREDENTIALS')
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
    canViewStores(): boolean {
      return this.permissions.includes('VIEW_STORES')
    },
    canManageStores(): boolean {
      return this.permissions.includes('MANAGE_STORES')
    },
    canViewSessions(): boolean {
      return this.permissions.includes('VIEW_SESSIONS')
    },
    canManageSessions(): boolean {
      return this.permissions.includes('MANAGE_SESSIONS')
    },
  },

  actions: {
    setUser(user: WorkspaceUser | null) {
      this.user = user
    },
    clearUser() {
      this.user = null
    },
  },
})
