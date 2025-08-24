// src/types/luigi.d.ts

export interface LinkManagerLike {
  navigate?: (path: string) => void
}

export interface UxManagerLike {
  setViewReady?: () => void
  setDocumentTitle?: (title: string) => void
}

export interface LuigiClientLike {
  addInitListener?: (cb: (ctx: Record<string, unknown>, origin?: string) => void, disableTpcCheck?: boolean) => void
  addContextUpdateListener?: (cb: (ctx: Record<string, unknown>) => void) => void
  getContext?: () => Record<string, unknown>
  // Return types as unknown; we’ll narrow with guards in the composable
  linkManager?: () => unknown
  uxManager?: () => unknown
}

declare global {
  interface Window {
    LuigiClient?: LuigiClientLike
  }
}

export {}
