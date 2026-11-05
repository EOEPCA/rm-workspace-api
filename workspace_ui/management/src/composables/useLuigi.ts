import { onMounted, onUnmounted, ref } from 'vue'
import LuigiClient from '@luigi-project/client'
import type { Workspace } from 'src/models/models'

type InitContext = { workspace: Workspace | undefined }

export function useLuigiWorkspace(options: { onReady: (context: InitContext) => void | Promise<void> }) {
  const loading = ref(true)
  let listener: number | undefined

  onMounted(() => {
    listener = LuigiClient.addInitListener((context) => {
      loading.value = false
      void options.onReady({ workspace: context.workspace as Workspace | undefined })
    })
  })

  onUnmounted(() => {
    if (listener !== undefined) LuigiClient.removeInitListener(listener)
  })

  return { loading }
}
