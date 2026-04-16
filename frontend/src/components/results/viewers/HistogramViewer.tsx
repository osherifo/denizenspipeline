/** Histogram viewer — wraps ImageViewer with a histogram-specific title. */
import type { ResultViewerProps } from '../registry'
import { ImageViewer } from './ImageViewer'

export function HistogramViewer(props: ResultViewerProps) {
  return <ImageViewer {...props} title="Score histogram" />
}
