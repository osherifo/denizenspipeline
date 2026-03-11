/** Color-coded QC metric badge. */

interface QcBadgeProps {
  label: string
  value: number | null
  thresholds?: [number, number] // [yellow, red]
  suffix?: string
  decimals?: number
}

export function QcBadge({ label, value, thresholds, suffix = '', decimals = 2 }: QcBadgeProps) {
  if (value == null) return null

  let color = 'var(--accent-green)'
  if (thresholds) {
    if (value >= thresholds[1]) color = 'var(--accent-red)'
    else if (value >= thresholds[0]) color = 'var(--accent-yellow)'
  }

  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 6px',
      borderRadius: 3,
      fontSize: 10,
      fontWeight: 600,
      backgroundColor: `color-mix(in srgb, ${color} 15%, transparent)`,
      color,
      marginRight: 6,
    }}>
      {label}={value.toFixed(decimals)}{suffix}
    </span>
  )
}
