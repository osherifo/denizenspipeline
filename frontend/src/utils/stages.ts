/** Subject analysis stages in run order, matching the backend's stage list. */
export const SUBJECT_STAGES: readonly string[] = ['stimuli', 'responses', 'features', 'prepare', 'model', 'analyze', 'report']

/** Stages whose output value stage QA reporters inspect (everything before analyze). */
export const QA_STAGE_NAMES: readonly string[] = SUBJECT_STAGES.slice(0, 5)
