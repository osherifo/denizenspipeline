/**
 * Small "installed from <source>" origin badge for the existing browsers.
 *
 * Reads the hub provenance ledger (fetched once, cached in the hub store) and
 * renders a tier-coloured chip when the given (kind, name) was installed from a
 * hub source — otherwise nothing. Additive and decoupled: a browser opts in by
 * dropping <HubBadge kind=… name=… /> next to an item; removing the hub feature
 * removes this file and the badge simply disappears.
 */

import { useEffect, type CSSProperties } from 'react'
import { useHubStore } from '../../stores/hub-store'

export function HubBadge({ kind, name }: { kind: string; name: string }) {
  const provenance = useHubStore((s) => s.provenance)
  const loadProvenance = useHubStore((s) => s.loadProvenance)

  useEffect(() => { void loadProvenance() }, [loadProvenance])

  const origin = provenance[`${kind}:${name}`]
  if (!origin) return null

  const color = origin.tier === 'community' ? 'var(--accent-green)' : 'var(--accent-cyan)'
  const style: CSSProperties = {
    fontSize: 10, fontWeight: 700, padding: '1px 7px', borderRadius: 10,
    color, backgroundColor: 'transparent', border: `1px solid ${color}`,
    whiteSpace: 'nowrap',
  }
  return (
    <span style={style} title={`Installed from ${origin.source_name} (${origin.tier}) · ${origin.installed_at}`}>
      hub: {origin.source_name}
    </span>
  )
}
