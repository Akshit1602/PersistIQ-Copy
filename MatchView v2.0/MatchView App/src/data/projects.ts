import type { Project, ThreadGroup } from '../context/types'

export const INITIAL_PROJECTS: Project[] = [
  {
    id: 'proj-walmart-digital',
    name: 'Digital Growth',
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

export const INITIAL_EXPERIMENT_PROJECT_IDS: Record<string, string> = {
  'Walmart Banner Redesign': 'proj-walmart-digital',
  'Holiday Promo Lift Test': 'proj-walmart-digital',
  'Cart Flow Optimization': 'proj-cart-reliability',
}

export const INITIAL_THREAD_GROUPS_WITH_PROJECTS: ThreadGroup[] = [
  {
    projectId: 'proj-walmart-digital',
    experiment: 'Walmart Banner Redesign',
    threads: [
      { id: 't1', title: 'Lift results summary', timestamp: '2h ago' },
      { id: 't2', title: 'ROI deep-dive follow-up', timestamp: 'Yesterday' },
      { id: 't3', title: 'Creative variant comparison', timestamp: '3 days ago' },
    ],
  },
  {
    projectId: 'proj-cart-reliability',
    experiment: 'Cart Flow Optimization',
    threads: [
      { id: 't4', title: 'Funnel drop-off analysis', timestamp: '1 week ago' },
      { id: 't5', title: 'Checkout step A/B results', timestamp: '2 weeks ago' },
    ],
  },
]
