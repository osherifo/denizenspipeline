/** Partition a NipypeTree into per-run "lanes" for layout.
 *
 * fmriprep's structure at depth 3 looks like this for a subject with
 * multiple BOLD runs:
 *
 *     fmriprep_wf
 *       └── single_subject_<id>_wf
 *             ├── anat_preproc_wf            ─┐
 *             ├── sdc_estimate_wf             │ Shared upstream lane
 *             ├── surface_recon_wf            ─┘
 *             ├── func_preproc_..._run_1_wf  ─── Run 1 lane
 *             ├── func_preproc_..._run_2_wf  ─── Run 2 lane
 *             └── func_preproc_..._run_3_wf  ─── Run 3 lane
 *
 * partitionLanes() buckets the depth-3 workflow ids (and their
 * filtered descendants) into:
 *   - "Shared upstream" — anatomical / fieldmap / anything not a
 *     `func_preproc_*` workflow.
 *   - One lane per (ses, task, run) tuple decoded from
 *     `func_preproc_(ses_X_)?task_Y_(run_Z_)?wf` ids.
 *
 * The decoded BIDS entities (ses/task/run) are literal substrings of
 * the workflow id — re-spaced for reading, not renamed.
 *
 * Non-fmriprep nipype trees (no `single_subject_*_wf` parent) fall
 * back to a single "Workflow" lane containing every workflow id.
 *
 * The depth-1 `fmriprep_wf` and depth-2 `single_subject_*_wf`
 * ancestor nodes are NOT placed in any lane. Their counts and
 * conceptual identity are already conveyed by the lane title bar
 * and the modal header.
 */

import type { NipypeTree, NipypeTreeNode } from './nipype_tree'


type Counts = NonNullable<NipypeTreeNode['counts']>


export interface NipypeLane {
  /** Synthetic id for the lane's ReactFlow group node. */
  id: string
  /** Title shown in the lane header (e.g. "Shared upstream", "Run 1 · ses-1 task-x run-1"). */
  title: string
  /** Roll-up status counts across the depth-3 roots assigned to this lane. */
  counts: Counts
  /** All ids (workflow + leaf) placed inside this lane. Stable sorted. */
  memberIds: string[]
}


const SHARED_LANE_ID = 'lane:shared'
const ALL_LANE_ID = 'lane:all'

const SINGLE_SUBJECT_RE = /^single_subject_.+_wf$/


interface DecodedFunc {
  ses: string | null
  task: string | null
  run: string | null
}


/** Decode a `func_preproc_(ses_X_)?(task_Y_)?(run_Z_)?wf` workflow
 *  label into its BIDS entity parts. Returns null if the label is
 *  not a func_preproc workflow. */
function _decodeFuncId(label: string): DecodedFunc | null {
  if (!label.startsWith('func_preproc_')) return null
  let body = label.slice('func_preproc_'.length).replace(/_wf$/, '')

  // Pull off optional trailing _run_X (X is alphanumeric per BIDS).
  let run: string | null = null
  const runTrailing = body.match(/_run_([^_]+)$/)
  if (runTrailing) {
    run = runTrailing[1]
    body = body.slice(0, -runTrailing[0].length)
  } else {
    // Body might BE "run_X" if there's no ses/task in this id.
    const bareRun = body.match(/^run_([^_]+)$/)
    if (bareRun) { run = bareRun[1]; body = '' }
  }

  // Pull off optional leading ses_X.
  let ses: string | null = null
  const sesLeading = body.match(/^ses_([^_]+)/)
  if (sesLeading) {
    ses = sesLeading[1]
    body = body.slice(sesLeading[0].length).replace(/^_/, '')
  }

  // Whatever remains, if it starts with `task_`, is the task entity.
  let task: string | null = null
  const taskRest = body.match(/^task_(.+)$/)
  if (taskRest) task = taskRest[1]

  return { ses, task, run }
}


function _runKey(d: DecodedFunc): string {
  return [d.ses ?? '', d.task ?? '', d.run ?? ''].join('|')
}


function _emptyCounts(): Counts {
  return { running: 0, ok: 0, failed: 0, completed_assumed: 0, cached: 0, total: 0 }
}


function _sumRootCounts(
  tree: NipypeTree,
  rootIds: ReadonlySet<string>,
): Counts {
  const out = _emptyCounts()
  const byId = new Map(tree.nodes.map((n) => [n.id, n]))
  for (const id of rootIds) {
    const n = byId.get(id)
    if (!n || !n.counts) continue
    out.running += n.counts.running
    out.ok += n.counts.ok
    out.failed += n.counts.failed
    out.completed_assumed += n.counts.completed_assumed
    out.cached += n.counts.cached
    out.total += n.counts.total
  }
  return out
}


function _formatRunTitle(index: number, meta: DecodedFunc): string {
  const parts: string[] = []
  if (meta.ses) parts.push(`ses-${meta.ses}`)
  if (meta.task) parts.push(`task-${meta.task}`)
  if (meta.run) parts.push(`run-${meta.run}`)
  const suffix = parts.length > 0 ? ` · ${parts.join(' ')}` : ''
  return `Run ${index}${suffix}`
}


function _allInOneLane(tree: NipypeTree): NipypeLane[] {
  if (tree.nodes.length === 0) return []
  const roots = tree.nodes.filter((n) => n.parentId === null && n.kind === 'workflow')
  return [{
    id: ALL_LANE_ID,
    title: 'Workflow',
    counts: _sumRootCounts(tree, new Set(roots.map((n) => n.id))),
    memberIds: tree.nodes.map((n) => n.id).sort(),
  }]
}


function _lanesForSubject(tree: NipypeTree, subject: NipypeTreeNode): NipypeLane[] {
  const subjectPrefix = subject.id + '.'
  const subjectDepth = subject.id.split('.').length

  // Depth-3 workflow children of this subject (depth-3 = subjectDepth + 1).
  const depth3Roots = tree.nodes.filter(
    (n) => n.kind === 'workflow' && n.parentId === subject.id,
  )

  interface Bucket {
    meta: DecodedFunc | null
    rootIds: Set<string>
    allIds: Set<string>
  }
  const runBuckets = new Map<string, Bucket>()
  const sharedBucket: Bucket = { meta: null, rootIds: new Set(), allIds: new Set() }

  for (const wf of depth3Roots) {
    const decoded = _decodeFuncId(wf.label)
    if (decoded) {
      const key = _runKey(decoded)
      let entry = runBuckets.get(key)
      if (!entry) { entry = { meta: decoded, rootIds: new Set(), allIds: new Set() }; runBuckets.set(key, entry) }
      entry.rootIds.add(wf.id)
      entry.allIds.add(wf.id)
    } else {
      sharedBucket.rootIds.add(wf.id)
      sharedBucket.allIds.add(wf.id)
    }
  }

  // Assign expanded descendants (depth > subjectDepth + 1) to the
  // same bucket as their depth-3 ancestor.
  for (const n of tree.nodes) {
    if (!n.id.startsWith(subjectPrefix)) continue
    if (n.parentId === subject.id) continue
    const segs = n.id.split('.')
    if (segs.length <= subjectDepth + 1) continue
    const depth3Ancestor = segs.slice(0, subjectDepth + 1).join('.')
    if (sharedBucket.rootIds.has(depth3Ancestor)) {
      sharedBucket.allIds.add(n.id)
      continue
    }
    for (const entry of runBuckets.values()) {
      if (entry.rootIds.has(depth3Ancestor)) {
        entry.allIds.add(n.id)
        break
      }
    }
  }

  const lanes: NipypeLane[] = []
  if (sharedBucket.allIds.size > 0) {
    lanes.push({
      id: SHARED_LANE_ID,
      title: 'Shared upstream',
      counts: _sumRootCounts(tree, sharedBucket.rootIds),
      memberIds: Array.from(sharedBucket.allIds).sort(),
    })
  }
  // Stable order: alphabetical by (ses, task, run) tuple key.
  const sortedRuns = Array.from(runBuckets.entries()).sort((a, b) => a[0].localeCompare(b[0]))
  sortedRuns.forEach(([, entry], idx) => {
    lanes.push({
      id: `lane:run-${idx + 1}`,
      title: _formatRunTitle(idx + 1, entry.meta!),
      counts: _sumRootCounts(tree, entry.rootIds),
      memberIds: Array.from(entry.allIds).sort(),
    })
  })
  return lanes
}


/** Partition a tree into lanes for layout. See module docstring. */
export function partitionLanes(tree: NipypeTree): NipypeLane[] {
  if (tree.nodes.length === 0) return []
  const subjectNodes = tree.nodes.filter(
    (n) => n.kind === 'workflow' && SINGLE_SUBJECT_RE.test(n.label),
  )
  if (subjectNodes.length === 0) return _allInOneLane(tree)
  // fmriprep emits one subject per run, but be defensive: if there
  // are multiple subjects (e.g. a hand-rolled batch tree), produce
  // one lane set per subject.
  if (subjectNodes.length === 1) return _lanesForSubject(tree, subjectNodes[0])
  return subjectNodes.flatMap((s) => _lanesForSubject(tree, s))
}


/** Exposed for tests + the modal renderer that wants to know if a
 *  given workflow id is the func_preproc root of a run lane. */
export function _decodeFuncIdForTests(label: string): DecodedFunc | null {
  return _decodeFuncId(label)
}
