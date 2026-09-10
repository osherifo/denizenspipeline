/** Which tabs a node's popup shows.
 *
 * Every node gets the generic tabs. A capability the node declares or derives
 * (`record.ui`, see the backend's `node_ui`) adds a built-in tab. `APP_TABS`
 * is the one place that knows a node *type* (fmriprep's friendlier summary);
 * an addon node never needs an entry here to get its capability tabs.
 */
import type { ReactNode } from 'react'
import type { CheckpointRecord, RunNodeRecord } from '../../../api/types'
import { OverviewTab } from './OverviewTab'
import { OutputsTab } from './OutputsTab'
import { CheckpointsTab } from './CheckpointsTab'
import { InnerDagTab } from './InnerDagTab'
import { LogTab } from './LogTab'
import { SummaryTab } from './SummaryTab'
import { ReportTab } from './ReportTab'
import { StructuralQCTab } from './StructuralQCTab'
import { FmriprepSummaryTab } from './FmriprepSummaryTab'
import { PhysioTab } from './PhysioTab'

export interface NodePopupContext {
  runId: string
  nodeId: string
  record: RunNodeRecord
  checkpoints: CheckpointRecord[]
  isRunning: boolean
}

export interface NodeTabDef {
  id: string
  label: string
  /** Absent = always shown. */
  when?: (ctx: NodePopupContext) => boolean
  render: (ctx: NodePopupContext) => ReactNode
}

export const GENERIC_TABS: NodeTabDef[] = [
  { id: 'overview', label: 'Overview', render: (ctx) => <OverviewTab ctx={ctx} /> },
  { id: 'outputs', label: 'Outputs', render: (ctx) => <OutputsTab ctx={ctx} /> },
  { id: 'checkpoints', label: 'Checkpoints', when: (ctx) => Boolean(ctx.record.ui.checkpoints) || ctx.checkpoints.length > 0, render: (ctx) => <CheckpointsTab ctx={ctx} /> },
  { id: 'inner', label: 'Inner DAG', when: (ctx) => Boolean(ctx.record.ui.inner_dag), render: (ctx) => <InnerDagTab ctx={ctx} /> },
  { id: 'log', label: 'Log', when: (ctx) => Boolean(ctx.record.ui.log) || ctx.record.has_log, render: (ctx) => <LogTab ctx={ctx} /> },
]

export const CAPABILITY_TABS: NodeTabDef[] = [
  { id: 'summary', label: 'Summary', when: (ctx) => Boolean(ctx.record.ui.summary), render: (ctx) => <SummaryTab ctx={ctx} /> },
  { id: 'report', label: 'Report', when: (ctx) => Boolean(ctx.record.ui.report), render: (ctx) => <ReportTab ctx={ctx} /> },
  { id: 'structural_qc', label: 'Structural QC', when: (ctx) => Boolean(ctx.record.ui.structural_qc) && Boolean(ctx.record.subject), render: (ctx) => <StructuralQCTab ctx={ctx} /> },
]

/** Per node *type*: overrides (same id replaces) and extras. */
export const APP_TABS: Record<string, NodeTabDef[]> = {
  fmriprep: [
    { id: 'summary', label: 'Summary', when: (ctx) => Boolean(ctx.record.ui.summary), render: (ctx) => <FmriprepSummaryTab ctx={ctx} /> },
  ],
  physio_regressors: [
    { id: 'physio', label: 'Pairing', render: (ctx) => <PhysioTab ctx={ctx} /> },
  ],
  physio_clean: [
    { id: 'physio', label: 'Cleaning', render: (ctx) => <PhysioTab ctx={ctx} /> },
  ],
}

export function tabsFor(ctx: NodePopupContext): NodeTabDef[] {
  const base = [...GENERIC_TABS, ...CAPABILITY_TABS]
  const overrides = APP_TABS[ctx.record.node_type] ?? []
  const merged = base.map((t) => overrides.find((o) => o.id === t.id) ?? t)
  for (const o of overrides) if (!merged.some((t) => t.id === o.id)) merged.push(o)
  return merged.filter((t) => !t.when || t.when(ctx))
}
