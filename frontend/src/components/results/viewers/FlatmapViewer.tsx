/** Flatmap viewer — wraps ImageViewer with a flatmap-specific title. */
import type { ResultViewerProps } from '../registry'
import { ImageViewer } from './ImageViewer'

export function FlatmapViewer(props: ResultViewerProps) {
  return <ImageViewer {...props} title="Flatmap" />
}
