import { onMounted, onUnmounted, ref } from 'vue'
import LuigiClient from '@luigi-project/client'
import type { Workspace, WorkspaceOverview } from 'src/models/models'

type InitContext = { workspace: Workspace | undefined; workspaceOverview: WorkspaceOverview | undefined }

export function useLuigiContext(options: { onReady: (context: InitContext) => void | Promise<void> }) {
  const loading = ref(true)
  let listener: number | undefined

  onMounted(() => {
    listener = LuigiClient.addInitListener((context) => {
      loading.value = false
      void options.onReady({
        workspace: context.workspace as Workspace | undefined,
        workspaceOverview: context.workspaceOverview as WorkspaceOverview | undefined,
      })
    })
  })

  onUnmounted(() => {
    if (listener !== undefined) LuigiClient.removeInitListener(listener)
  })

  return { loading }
}
