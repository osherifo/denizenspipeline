/** Register built-in viewers. Import this file once at app startup. */
import {
  registerViewer,
  matchesFilename,
  matchesPattern,
  matchesExtension,
} from './registry'
import { MetricsViewer } from './viewers/MetricsViewer'
import { FlatmapViewer } from './viewers/FlatmapViewer'
import { HistogramViewer } from './viewers/HistogramViewer'
import { WebGLViewer } from './viewers/WebGLViewer'
import { ImageViewer } from './viewers/ImageViewer'
import { JsonViewer } from './viewers/JsonViewer'
import { FileInfoViewer } from './viewers/FileInfoViewer'

// Priority tiers:
//   100+ : filename-exact viewers (metrics.json)
//    80  : filename-pattern viewers (*flatmap*.png, webgl_viewer/)
//    50  : extension-based viewers (.png, .json)
//     0  : fallback

registerViewer({
  id: 'metrics',
  label: 'Metrics',
  priority: 100,
  matches: matchesFilename('metrics.json'),
  component: MetricsViewer,
})

registerViewer({
  id: 'flatmap',
  label: 'Flatmap',
  priority: 80,
  matches: matchesPattern(/flatmap.*\.(png|jpg|jpeg)$/i),
  component: FlatmapViewer,
})

registerViewer({
  id: 'histogram',
  label: 'Histogram',
  priority: 80,
  matches: matchesPattern(/histogram.*\.(png|jpg|jpeg)$/i),
  component: HistogramViewer,
})

registerViewer({
  id: 'webgl',
  label: 'WebGL viewer',
  priority: 80,
  matches: (a) =>
    /webgl_viewer(\/|$)|\/index\.html$/i.test(a.name)
    || a.name === 'webgl_viewer',
  component: WebGLViewer,
})

registerViewer({
  id: 'image',
  label: 'Image',
  priority: 50,
  matches: matchesExtension('png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'),
  component: ImageViewer,
})

registerViewer({
  id: 'json',
  label: 'JSON',
  priority: 50,
  matches: matchesExtension('json'),
  component: JsonViewer,
})

registerViewer({
  id: 'fallback',
  label: 'File',
  priority: 0,
  matches: () => true,
  component: FileInfoViewer,
})
