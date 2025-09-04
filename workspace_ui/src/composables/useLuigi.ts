import { onMounted, ref } from 'vue'
import type { LuigiClientLike } from 'src/types/luigi'

type Options<T> = {
  /** If true, initLuigi() will be called on mounting (default: true) */
  autoInit?: boolean
  /** Optional callback fired once workspace has been initialized */
  onReady?: (workspace: T | null) => void
}

const isUxManager = (v: unknown): v is { setViewReady?: () => void } =>
  typeof v === 'object' && v !== null && 'setViewReady' in v

async function resolveLuigiClient(): Promise<LuigiClientLike | null> {
  try {
    const mod = await import('@luigi-project/client')
    return (mod as unknown as { default: unknown }).default as LuigiClientLike
  } catch {
    const w = window as unknown as { LuigiClient?: LuigiClientLike }
    return w.LuigiClient ?? null
  }
}

export function useLuigiWorkspace<T>(opts: Options<T> = { autoInit: true }) {
  const loading = ref<boolean>(true)
  const workspace = ref<T | null>(null)

  type InitCtx = {
    workspace?: T
  }

  async function initLuigi(): Promise<void> {
    loading.value = true
    const LuigiClient = await resolveLuigiClient()

    // No Luigi-Shell present → exit gracefully
    if (!LuigiClient) {
      loading.value = false
      workspace.value = null
      opts.onReady?.(null)
      return
    }

    LuigiClient.addInitListener?.((ctx: InitCtx) => {
      loading.value = false

      const ws = ctx.workspace
      if (ws && typeof ws === 'object') {
        workspace.value = ws
        const ux = LuigiClient?.uxManager?.()
        if (isUxManager(ux)) {
          ux.setViewReady?.()
        }
      } else {
        workspace.value = null
      }

      // Call the optional callback after initialization
      opts.onReady?.(workspace.value)
    })
  }

  if (opts.autoInit !== false) {
    onMounted(() => {
      void initLuigi()
    })
  }

  return {
    // reactive state
    loading,
    workspace,
    // public actions
    initLuigi,
  }
}
