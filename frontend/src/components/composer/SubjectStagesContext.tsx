/** SubjectStagesContext — shared state surface for the 7-stage form.
 *
 * Both the SubjectComposerBody (operating on the top-level subject
 * config-store) and the GroupComposer's ``subject_template`` card
 * (operating on a slice of the group config-store) render the same
 * StimulusBody / ResponseBody / FeaturesBody / … components. Those
 * bodies talk to this context instead of importing useConfigStore
 * directly, so they don't care which store is behind the wheel.
 *
 * The provider just hands down a "stage API" — a PipelineConfig
 * snapshot plus the action callbacks the bodies need. Each caller is
 * free to source those from any store + path translation it likes.
 */
import { createContext, useContext } from 'react'
import type {
  PipelineConfig, FeatureConfig, StepConfig, AnalyzerConfig,
} from '../../api/types'


export interface SubjectStagesAPI {
  config: PipelineConfig
  setField: (path: string, value: unknown) => void

  addFeature: (feature: FeatureConfig) => void
  removeFeature: (index: number) => void
  updateFeature: (index: number, feature: FeatureConfig) => void
  reorderFeatures: (from: number, to: number) => void

  addStep: (step: StepConfig) => void
  removeStep: (index: number) => void
  updateStep: (index: number, step: StepConfig) => void
  reorderSteps: (from: number, to: number) => void

  addAnalyzer: (analyzer: AnalyzerConfig) => void
  removeAnalyzer: (index: number) => void
  updateAnalyzer: (index: number, analyzer: AnalyzerConfig) => void
}


const SubjectStagesContext = createContext<SubjectStagesAPI | null>(null)


export function SubjectStagesProvider(props: {
  api: SubjectStagesAPI
  children: React.ReactNode
}) {
  return (
    <SubjectStagesContext.Provider value={props.api}>
      {props.children}
    </SubjectStagesContext.Provider>
  )
}


export function useSubjectStages(): SubjectStagesAPI {
  const ctx = useContext(SubjectStagesContext)
  if (!ctx) {
    throw new Error(
      'useSubjectStages must be used inside a <SubjectStagesProvider>',
    )
  }
  return ctx
}
