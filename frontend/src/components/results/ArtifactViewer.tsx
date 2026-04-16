/** Dispatcher — picks the right viewer from the registry and renders it. */
import type { ArtifactInfo } from '../../api/types'
import { findViewerFor } from './registry'
import { FileInfoViewer } from './viewers/FileInfoViewer'

// Ensure built-in viewers are registered (side-effect import).
import './builtin'

interface Props {
  artifact: ArtifactInfo
  runId: string
}

export function ArtifactViewer({ artifact, runId }: Props) {
  const viewer = findViewerFor(artifact)
  const Component = viewer?.component ?? FileInfoViewer
  return <Component artifact={artifact} runId={runId} />
}
