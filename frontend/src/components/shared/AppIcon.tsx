import type { LucideIcon } from 'lucide-react'

export type IconSize = 'xs' | 'sm' | 'md' | 'lg'

const SIZE_MAP: Record<IconSize, number> = {
  xs: 14,
  sm: 16,
  md: 18,
  lg: 20,
}

interface AppIconProps {
  icon: LucideIcon
  size?: IconSize
  className?: string
  strokeWidth?: number
}

export function AppIcon({
  icon: Icon,
  size = 'sm',
  className = '',
  strokeWidth = 1.75,
}: AppIconProps) {
  return (
    <Icon
      size={SIZE_MAP[size]}
      strokeWidth={strokeWidth}
      className={`shrink-0 ${className}`}
      aria-hidden="true"
    />
  )
}
