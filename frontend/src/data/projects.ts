import type { Project, ThreadGroup } from '../context/types'

export const INITIAL_PROJECTS: Project[] = [
  {
    id: 'proj-walmart-digital',
    name: 'Walmart Digital Growth',
    description: 'Checkout, banner, and promo experiments for digital storefront conversion.',
    objective: 'Lift digital CVR and GMV without harming refund / bounce guardrails.',
    channel: 'digital',
    dataSource: { type: 'internal' },
    createdAt: '2026-06-01',
  },
  {
    id: 'proj-cart-reliability',
    name: 'Cart Reliability',
    description: 'Funnel and checkout flow diagnostics for cart abandonment reduction.',
    objective: 'Reduce cart drop-off while keeping support tickets flat.',
    channel: 'digital',
    dataSource: {
      type: 'external',
      externalConnection: 'snowflake://analytics.prod/matchview',
    },
    createdAt: '2026-06-15',
  },
]

export const INITIAL_EXPERIMENT_PROJECT_IDS: Record<string, string> = {}

export const INITIAL_THREAD_GROUPS_WITH_PROJECTS: ThreadGroup[] = []
