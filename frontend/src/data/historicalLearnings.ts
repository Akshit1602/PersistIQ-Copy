export interface HistoricalLearning {
  id: string
  experiment: string
  summary: string
  keywords: string[]
  outcome: 'Ship' | 'Iterate' | 'Kill' | 'Hold'
}

const LEARNINGS: HistoricalLearning[] = [
  {
    id: 'hl-1',
    experiment: 'Walmart Banner Redesign',
    summary: '+4.2% CTR lift; creative contrast drove acquisition without hurting bounce.',
    keywords: ['banner', 'ctr', 'click', 'creative', 'acquisition', 'traffic'],
    outcome: 'Ship',
  },
  {
    id: 'hl-2',
    experiment: 'Cart Flow Optimization',
    summary: 'Checkout step simplification lifted CVR; guardrail refund rate held flat.',
    keywords: ['cart', 'checkout', 'cvr', 'conversion', 'abandonment', 'flow'],
    outcome: 'Ship',
  },
  {
    id: 'hl-3',
    experiment: 'Holiday Promo Lift Test',
    summary: 'Aggressive promo copy lifted GMV but raised refund rate — iterate messaging.',
    keywords: ['promo', 'gmv', 'holiday', 'discount', 'revenue', 'refund'],
    outcome: 'Iterate',
  },
  {
    id: 'hl-4',
    experiment: 'Mobile PDP Layout v2',
    summary: 'Above-fold CTA change improved activation; session depth secondary improved.',
    keywords: ['mobile', 'pdp', 'cta', 'activation', 'engagement'],
    outcome: 'Ship',
  },
  {
    id: 'hl-5',
    experiment: 'Email Re-engagement Cadence',
    summary: 'Higher frequency hurt unsubscribe guardrail — killed weekly burst variant.',
    keywords: ['email', 'retention', 'churn', 'unsubscribe', 're-engagement'],
    outcome: 'Kill',
  },
]

function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .split(/[^a-z0-9+]+/)
    .filter((t) => t.length > 2)
}

/** Keyword-overlap match against past digital experiment learnings. */
export function findSimilarLearnings(
  hypothesis: string,
  goal: string,
  limit = 3,
): HistoricalLearning[] {
  const tokens = new Set(tokenize(`${hypothesis} ${goal}`))
  if (tokens.size === 0) return LEARNINGS.slice(0, limit)

  const scored = LEARNINGS.map((learning) => {
    const overlap = learning.keywords.filter((k) =>
      [...tokens].some((t) => k.includes(t) || t.includes(k)),
    ).length
    return { learning, overlap }
  })
    .filter((s) => s.overlap > 0)
    .sort((a, b) => b.overlap - a.overlap)

  if (scored.length === 0) return LEARNINGS.slice(0, limit)
  return scored.slice(0, limit).map((s) => s.learning)
}

/** Markdown-ish body for ChatRichText: heading, numbered list, closing note. */
export function buildSimilarLearningsMessage(learnings: HistoricalLearning[]): string {
  if (learnings.length === 0) {
    return 'No closely matching historical learnings found yet — proceed with **Opportunity Sizing**.'
  }

  const items = learnings.map((l) => {
    const href = `experiment:${l.experiment}`
    return `[${l.experiment}](${href}) · *${l.outcome}* — ${l.summary}`
  })

  return [
    '**Similar past digital experiments / learnings**',
    '',
    ...items.map((item, i) => `${i + 1}. ${item}`),
    '',
    'Use these as baselines while you complete **Opportunity Sizing**.',
  ].join('\n')
}
