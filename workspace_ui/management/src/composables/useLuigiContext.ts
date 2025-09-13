// src/composables/useLuigi.ts
import { ref, onMounted } from 'vue'
import type { LuigiClientLike, LinkManagerLike, UxManagerLike } from 'src/types/luigi'

export function useLuigi() {
  const luigi = ref<LuigiClientLike | null>(null)

  // --- type guards ---
  const isLinkManager = (v: unknown): v is LinkManagerLike =>
    typeof v === 'object' && v !== null && 'navigate' in v

  const isUxManager = (v: unknown): v is UxManagerLike =>
    typeof v === 'object' && v !== null &&
    ('setViewReady' in v || 'setDocumentTitle' in v)

  onMounted(async () => {
    try {
      const mod = await import('@luigi-project/client')
      luigi.value = (mod as unknown as { default: unknown }).default as LuigiClientLike
    } catch {
      // fallback to global
      luigi.value = (window as unknown as { LuigiClient?: LuigiClientLike }).LuigiClient ?? null
    }
  })

  function navigate(path: string) {
    const lm = luigi.value?.linkManager?.()
    if (isLinkManager(lm)) {
      lm.navigate?.(path)
    }
  }

  function getContext() {
    return luigi.value?.getContext?.() ?? {}
  }

  function setViewReady() {
    const ux = luigi.value?.uxManager?.()
    if (isUxManager(ux)) {
      ux.setViewReady?.()
    }
  }

  return { luigi, navigate, getContext, setViewReady }
}
