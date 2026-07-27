import type { ReactNode } from 'react'

interface InsightsDashboardGridProps {
  children: ReactNode
  featured?: ReactNode
}

export function InsightsDashboardGrid({ children, featured }: InsightsDashboardGridProps) {
  return (
    <div className="grid grid-cols-2 gap-4">
      {featured && <div className="col-span-2">{featured}</div>}
      {children}
    </div>
  )
}
