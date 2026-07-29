export type MetricRole = 'primary' | 'secondary' | 'guardrail'

export interface MetricInputField {
  key: string
  label: string
  placeholder?: string
  type?: 'text' | 'number'
  required?: boolean
}

export interface MetricKpiOption {
  id: string
  label: string
  description: string
  /** Roles this KPI can appear in */
  roles: MetricRole[]
  /** Extra inputs shown only for primary/secondary selections */
  inputs?: MetricInputField[]
}

/** Shared digital-experiment KPI catalog for Hypothesis Validator metrics. */
export const METRIC_KPI_OPTIONS: MetricKpiOption[] = [
  {
    id: 'ctr',
    label: 'CTR',
    description: 'Click-through rate on the treated surface',
    roles: ['primary', 'secondary'],
    inputs: [
      { key: 'baseline', label: 'Baseline CTR (%)', placeholder: 'e.g. 2.4', type: 'number', required: true },
      { key: 'event', label: 'Tracking event', placeholder: 'e.g. banner_click', type: 'text', required: true },
    ],
  },
  {
    id: 'cvr',
    label: 'Conversion Rate (CVR)',
    description: 'Primary conversion success rate',
    roles: ['primary', 'secondary'],
    inputs: [
      { key: 'baseline', label: 'Baseline CVR (%)', placeholder: 'e.g. 3.1', type: 'number', required: true },
      { key: 'event', label: 'Conversion event', placeholder: 'e.g. purchase_complete', type: 'text', required: true },
    ],
  },
  {
    id: 'landing-cvr',
    label: 'Landing CVR',
    description: 'Conversion quality of acquired traffic',
    roles: ['primary', 'secondary'],
    inputs: [
      { key: 'baseline', label: 'Baseline landing CVR (%)', placeholder: 'e.g. 4.5', type: 'number', required: true },
      { key: 'event', label: 'Landing conversion event', placeholder: 'e.g. lp_convert', type: 'text', required: true },
    ],
  },
  {
    id: 'aov',
    label: 'AOV',
    description: 'Average order value',
    roles: ['primary', 'secondary'],
    inputs: [
      { key: 'baseline', label: 'Baseline AOV ($)', placeholder: 'e.g. 52', type: 'number', required: true },
    ],
  },
  {
    id: 'gmv-per-visitor',
    label: 'GMV per Visitor',
    description: 'Revenue efficiency per visitor',
    roles: ['primary', 'secondary'],
    inputs: [
      { key: 'baseline', label: 'Baseline GMV / visitor ($)', placeholder: 'e.g. 1.8', type: 'number', required: true },
    ],
  },
  {
    id: 'signup-completion',
    label: 'Signup Completion Rate',
    description: 'Activation success through signup',
    roles: ['primary', 'secondary'],
    inputs: [
      { key: 'baseline', label: 'Baseline signup rate (%)', placeholder: 'e.g. 18', type: 'number', required: true },
      { key: 'event', label: 'Signup event', placeholder: 'e.g. signup_success', type: 'text', required: true },
    ],
  },
  {
    id: 'time-to-first-action',
    label: 'Time-to-First-Action',
    description: 'Friction after activation',
    roles: ['primary', 'secondary'],
    inputs: [
      { key: 'baseline', label: 'Baseline time (sec)', placeholder: 'e.g. 45', type: 'number', required: true },
    ],
  },
  {
    id: 'return-7d',
    label: '7-Day Return Rate',
    description: 'Short-horizon retention',
    roles: ['primary', 'secondary'],
    inputs: [
      { key: 'baseline', label: 'Baseline 7-day return (%)', placeholder: 'e.g. 22', type: 'number', required: true },
    ],
  },
  {
    id: 'orders-returning',
    label: 'Orders per Returning User',
    description: 'Value of retained users',
    roles: ['primary', 'secondary'],
    inputs: [
      { key: 'baseline', label: 'Baseline orders / returning user', placeholder: 'e.g. 1.4', type: 'number', required: true },
    ],
  },
  {
    id: 'sessions-per-user',
    label: 'Sessions per User',
    description: 'Engagement depth',
    roles: ['primary', 'secondary'],
    inputs: [
      { key: 'baseline', label: 'Baseline sessions / user', placeholder: 'e.g. 2.1', type: 'number', required: true },
    ],
  },
  {
    id: 'pages-per-session',
    label: 'Pages per Session',
    description: 'Content / UX engagement',
    roles: ['primary', 'secondary'],
    inputs: [
      { key: 'baseline', label: 'Baseline pages / session', placeholder: 'e.g. 3.6', type: 'number', required: true },
    ],
  },
  {
    id: 'bounce-rate',
    label: 'Bounce Rate',
    description: 'Landing quality guardrail',
    roles: ['guardrail'],
  },
  {
    id: 'refund-rate',
    label: 'Refund Rate',
    description: 'Margin and trust guardrail',
    roles: ['guardrail'],
  },
  {
    id: 'cart-abandonment',
    label: 'Cart Abandonment',
    description: 'Checkout friction guardrail',
    roles: ['guardrail'],
  },
  {
    id: 'support-ticket-rate',
    label: 'Support Ticket Rate',
    description: 'Confusion / friction guardrail',
    roles: ['guardrail'],
  },
  {
    id: 'unsubscribe-rate',
    label: 'Unsubscribe Rate',
    description: 'Messaging fatigue guardrail',
    roles: ['guardrail'],
  },
  {
    id: 'crash-error-rate',
    label: 'Crash / Error Rate',
    description: 'Technical stability guardrail',
    roles: ['guardrail'],
  },
]

export const METRIC_KPI_BY_ID = Object.fromEntries(
  METRIC_KPI_OPTIONS.map((k) => [k.id, k]),
) as Record<string, MetricKpiOption>

export function getKpisForRole(role: MetricRole): MetricKpiOption[] {
  return METRIC_KPI_OPTIONS.filter((k) => k.roles.includes(role))
}

export function getMetricInputsForSelection(selectedIds: string[]): {
  kpiId: string
  label: string
  inputs: MetricInputField[]
}[] {
  return selectedIds
    .map((id) => METRIC_KPI_BY_ID[id])
    .filter((k): k is MetricKpiOption => Boolean(k?.inputs?.length))
    .map((k) => ({ kpiId: k.id, label: k.label, inputs: k.inputs! }))
}
