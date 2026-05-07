import { modulesHandlers } from './handlers.modules'
import { configsHandlers } from './handlers.configs'
import { runsHandlers } from './handlers.runs'
import { preprocHandlers } from './handlers.preproc'
import { autoflattenHandlers } from './handlers.autoflatten'
import { convertHandlers } from './handlers.convert'
import { errorsHandlers } from './handlers.errors'

export const handlers = [
  ...modulesHandlers,
  ...configsHandlers,
  ...runsHandlers,
  ...preprocHandlers,
  ...autoflattenHandlers,
  ...convertHandlers,
  ...errorsHandlers,
]
