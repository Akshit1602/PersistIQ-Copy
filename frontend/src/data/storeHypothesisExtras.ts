/**
 * Store Channel — Initiative Setup & Benchmarking: Step 1 enhancements
 *
 *   - Exposure Ledger Integration: every hypothesis links to a recognized
 *     Initiative Domain
 *   - Dosage Tracking: captures the exact degree of intervention, not a
 *     binary flag
 *   - Shadow Initiative Check: simulated change-point scan (stand-in for a
 *     real PELT/Bai-Perron backend job) to flag undocumented interventions
 */

export type InitiativeDomain = 'labor_staffing' | 'store_format_remodel' | 'merchandising_assortment' | 'pricing_promo'

export const DOMAIN_OPTIONS: { value: InitiativeDomain; label: string; hint: string }[] = [
  { value: 'labor_staffing', label: 'Labor & Staffing', hint: 'Dedicated cashiers, greeter staffing, headcount changes' },
  { value: 'store_format_remodel', label: 'Store Format & Remodel', hint: 'Paint-and-Powder, layout redesign, footprint changes' },
  { value: 'merchandising_assortment', label: 'Merchandising & Assortment', hint: 'Endcap placement, shelf tagging, SKU assortment shifts' },
  { value: 'pricing_promo', label: 'Pricing & Promo', hint: 'Multi-price rollout, in-store circular/POP promotions' },
]

export type DosageType = 'units_per_week' | 'hours_per_week' | 'budget_dollars' | 'square_feet' | 'price_delta_dollars' | 'price_delta_percent'

export const DOSAGE_TYPE_OPTIONS: { value: DosageType; label: string; placeholder: string }[] = [
  { value: 'units_per_week', label: 'Additional Facings / Store Units', placeholder: 'e.g. 250' },
  { value: 'hours_per_week', label: 'Cashier Hours / Store / Week', placeholder: 'e.g. 40' },
  { value: 'budget_dollars', label: 'Budget ($)', placeholder: 'e.g. 800000' },
  { value: 'square_feet', label: 'Remodel Sq Ft', placeholder: 'e.g. 1200' },
  { value: 'price_delta_dollars', label: 'Price Delta ($)', placeholder: 'e.g. 0.50' },
  { value: 'price_delta_percent', label: 'Price Delta (%)', placeholder: 'e.g. 5' },
]

/**
 * Dynamic Dosage Configurator: the dosage input adapts to the selected
 * Initiative Domain rather than offering all 6 types unconditionally.
 * The first entry in each list is the domain's default dosage type.
 */
export const DOMAIN_DOSAGE_TYPES: Record<InitiativeDomain, DosageType[]> = {
  labor_staffing: ['hours_per_week'],
  merchandising_assortment: ['units_per_week'],
  pricing_promo: ['price_delta_percent', 'price_delta_dollars'],
  store_format_remodel: ['budget_dollars', 'square_feet'],
}

export interface ShadowCheckResult {
  changePointDetected: boolean
  changePointDate: string | null
  confidence: number // 0-1
  verdict: 'documented' | 'shadow_initiative_suspected'
  ranAtIso: string
}

export interface StoreHypothesisExtras {
  domain: InitiativeDomain | null
  dosageValue: number | null
  dosageType: DosageType
  shadowCheckResult: ShadowCheckResult | null
  isRunningShadowCheck: boolean
}

export const STORE_HYPOTHESIS_EXTRAS_DEFAULTS: StoreHypothesisExtras = {
  domain: null,
  dosageValue: null,
  dosageType: 'budget_dollars',
  shadowCheckResult: null,
  isRunningShadowCheck: false,
}

/**
 * Simulated background change-point scan (stands in for a real PELT /
 * Bai-Perron job run against store_performance_weekly). Deterministic given
 * the same hypothesis name — a real deployment would run this as an async
 * Databricks job and poll for the result.
 */
export function simulateShadowInitiativeCheck(hypothesisName: string): Promise<ShadowCheckResult> {
  return new Promise((resolve) => {
    const charSum = hypothesisName.split('').reduce((a, c) => a + c.charCodeAt(0), 0)
    const seed = hypothesisName.length * 13 + charSum
    const pseudoRandom = Math.abs(Math.sin(seed * 0.31))
    // Most documented initiatives should scan clean — only flag ~25% of the time.
    const changePointDetected = pseudoRandom > 0.75

    let changePointDate: string | null = null
    if (changePointDetected) {
      const daysAgo = 10 + Math.round(pseudoRandom * 60)
      const d = new Date()
      d.setDate(d.getDate() - daysAgo)
      changePointDate = d.toISOString().slice(0, 10)
    }

    window.setTimeout(() => {
      resolve({
        changePointDetected,
        changePointDate,
        confidence: Math.round((changePointDetected ? 0.7 + pseudoRandom * 0.25 : 0.85 + (1 - pseudoRandom) * 0.14) * 100) / 100,
        verdict: changePointDetected ? 'shadow_initiative_suspected' : 'documented',
        ranAtIso: new Date().toISOString(),
      })
    }, 900)
  })
}

export function isStoreHypothesisExtrasValid(extras: StoreHypothesisExtras): boolean {
  return extras.domain !== null
}
