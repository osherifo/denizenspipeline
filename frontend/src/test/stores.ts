import { useModuleStore } from '../stores/module-store'
import { useEditorStore } from '../stores/editor-store'
import { useRunStore } from '../stores/run-store'
import { useDashboardStore } from '../stores/dashboard-store'
import { useConfigStore } from '../stores/config-store'
import { usePreprocStore } from '../stores/preproc-store'
import { useAutoflattenStore } from '../stores/autoflatten-store'
import { useConvertStore } from '../stores/convert-store'
import { useGraphStore } from '../stores/graph-store'

type StoreApi = {
  getState: () => Record<string, unknown>
  setState: (s: Record<string, unknown>, replace?: true) => void
}

const allStores: StoreApi[] = [
  useModuleStore as unknown as StoreApi,
  useEditorStore as unknown as StoreApi,
  useRunStore as unknown as StoreApi,
  useDashboardStore as unknown as StoreApi,
  useConfigStore as unknown as StoreApi,
  usePreprocStore as unknown as StoreApi,
  useAutoflattenStore as unknown as StoreApi,
  useConvertStore as unknown as StoreApi,
  useGraphStore as unknown as StoreApi,
]

const initialStates = new Map<StoreApi, Record<string, unknown>>()

for (const store of allStores) {
  initialStates.set(store, { ...store.getState() })
}

export function resetAllStores() {
  for (const store of allStores) {
    const initial = initialStates.get(store)
    if (initial) {
      store.setState({ ...initial }, true)
    }
  }
}
