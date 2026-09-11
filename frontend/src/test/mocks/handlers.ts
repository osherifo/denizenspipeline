import { modulesHandlers } from './handlers.modules'
import { configsHandlers } from './handlers.configs'
import { runsHandlers } from './handlers.runs'
import { preprocHandlers } from './handlers.preproc'
import { autoflattenHandlers } from './handlers.autoflatten'
import { convertHandlers } from './handlers.convert'
import { errorsHandlers } from './handlers.errors'
import { settingsHandlers } from './handlers.settings'
import { preprocPipelinesHandlers } from './handlers.preproc-pipelines'
import { fsHandlers } from './handlers.fs'
import { analysisGraphsHandlers } from './handlers.analysis-graphs'

export const handlers = [
  ...analysisGraphsHandlers,
  // Pipeline runs own /api/preproc/runs; they must precede the legacy preproc handlers.
  ...preprocPipelinesHandlers,
  ...fsHandlers,
  ...modulesHandlers,
  ...configsHandlers,
  ...runsHandlers,
  ...preprocHandlers,
  ...autoflattenHandlers,
  ...convertHandlers,
  ...errorsHandlers,
  ...settingsHandlers,
]
