import { onMounted, ref } from 'vue'
import type { LuigiClientLike } from 'src/types/luigi'
import type {Bucket, Membership, Workspace} from 'src/models/models'

export type InitCtx = {
  workspace?: Workspace
  memberships?: Membership[],
  bucketAccessRequests?: Bucket[]
}

type Options = {
  /** If true, initLuigi() will be called on mounting (default: true) */
  autoInit?: boolean
  /** Optional callback fired once workspace has been initialized */
  onReady?: (workspace: InitCtx | null) => void
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

export function useLuigiWorkspace(opts: Options = { autoInit: true }) {
  const loading = ref<boolean>(true)
  const context = ref<InitCtx | null>(null)

  async function initLuigi(): Promise<void> {
    loading.value = true
    const LuigiClient = await resolveLuigiClient()

    // No Luigi-Shell present → exit gracefully
    if (!LuigiClient) {
      loading.value = false
      context.value = null
      opts.onReady?.(null)
      return
    }

    LuigiClient.addInitListener?.((ctx: InitCtx) => {
      loading.value = false

      context.value = ctx
      if (ctx && typeof ctx === 'object') {
        const ux = LuigiClient?.uxManager?.()
        if (isUxManager(ux)) {
          ux.setViewReady?.()
        }
      }

      // Call the optional callback after initialization
      opts.onReady?.(ctx)
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
//    workspace,
    // public actions
    initLuigi,
  }
}
