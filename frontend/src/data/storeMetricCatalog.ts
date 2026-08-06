/**
 * Store Channel Metric Catalog — General Retail MVP
 *
 * Complete metric catalog for the Store channel Initiative Setup & Benchmarking.
 * Each metric maps to SQL expressions against the UC tables in
 * dev.matchview_store.* and is used by the Flask backend to generate
 * performance queries for experiment analysis.
 *
 * Categories:
 *   - Financial (7) — Revenue, margin, and space efficiency
 *   - Traffic & Conversion (5) — Foot traffic and transaction capture
 *   - Basket Mechanics (4) — Basket depth and item-level economics
 *   - Supply Chain (5) — Inventory health and operational efficiency
 *   - Environmental Confounders (4) — External noise factors for baselining
 *   - Guardrails (3) — Mandatory floor metrics that must not degrade
 */

import type { MetricRole, MetricInputField, MetricKpiOption } from './metricCatalog'
export type { MetricRole, MetricInputField, MetricKpiOption }

export type StoreMetricCategory =
  | 'Financial'
  | 'Traffic & Conversion'
  | 'Basket Mechanics'
  | 'Supply Chain'
  | 'Environmental Confounders'
  | 'Guardrails'

export type MetricFormat = 'currency' | 'percentage' | 'number' | 'decimal'

export interface StoreMetricKpiOption extends MetricKpiOption {
  /** SQL aggregation expression for computing this metric */
  sqlExpression: string
  /** Metric category for grouping in the UI */
  category: StoreMetricCategory
  /** Display format hint */
  format: MetricFormat
}

// ═══════════════════════════════════════════════════════════════════════════════
// Financial Metrics (7)
// ═══════════════════════════════════════════════════════════════════════════════

export const STORE_METRIC_KPI_OPTIONS: StoreMetricKpiOption[] = [
  {
    id: 'total_sales',
    label: 'Gross Sales',
    description: 'Total gross sales amount. Primary target variable for macro net lift calculations.',
    roles: ['primary', 'secondary'],
    category: 'Financial',
    sqlExpression: 'SUM(gross_sales_amt)',
    format: 'currency',
    inputs: [
      { key: 'baseline', label: 'Baseline weekly gross sales ($)', placeholder: 'e.g. 42000', type: 'number', required: true },
      { key: 'mde', label: 'Min. detectable effect (%)', placeholder: 'e.g. 3', type: 'number', required: true },
    ],
  },
  {
    id: 'net_sales',
    label: 'Net Sales Revenue',
    description: 'Gross sales minus returns and discounts.',
    roles: ['primary', 'secondary'],
    category: 'Financial',
    sqlExpression: 'SUM(gross_sales_amt) - SUM(returns) - SUM(discounts)',
    format: 'currency',
    inputs: [
      { key: 'baseline', label: 'Baseline weekly net sales ($)', placeholder: 'e.g. 38000', type: 'number', required: true },
      { key: 'mde', label: 'Min. detectable effect (%)', placeholder: 'e.g. 3', type: 'number', required: true },
    ],
  },
  {
    id: 'aur',
    label: 'Average Unit Retail',
    description: 'Average price point realized per physical item unit sold.',
    roles: ['primary', 'secondary'],
    category: 'Financial',
    sqlExpression: 'SUM(net_sales_amt) / SUM(total_units)',
    format: 'currency',
    inputs: [
      { key: 'baseline', label: 'Baseline AUR ($)', placeholder: 'e.g. 2.85', type: 'number', required: true },
    ],
  },
  {
    id: 'gross_margin',
    label: 'Gross Profit Margin',
    description: 'Percentage of revenue remaining after subtracting the cost of goods sold (COGS).',
    roles: ['primary', 'secondary'],
    category: 'Financial',
    sqlExpression: '(SUM(net_sales_amt) - SUM(cogs)) / NULLIF(SUM(net_sales_amt), 0)',
    format: 'percentage',
    inputs: [
      { key: 'baseline', label: 'Baseline gross margin (%)', placeholder: 'e.g. 35', type: 'number', required: true },
    ],
  },
  {
    id: 'markdown_rate',
    label: 'Markdown Rate',
    description: 'Percentage of gross sales given back via promotional markdowns.',
    roles: ['primary', 'secondary'],
    category: 'Financial',
    sqlExpression: 'SUM(markdown_dollars) / NULLIF(SUM(gross_sales_amt), 0)',
    format: 'percentage',
    inputs: [
      { key: 'baseline', label: 'Baseline markdown rate (%)', placeholder: 'e.g. 8', type: 'number', required: true },
    ],
  },
  {
    id: 'sales_per_sqft',
    label: 'Sales per Square Foot',
    description: 'Store space efficiency. Net sales divided by total store square footage.',
    roles: ['primary', 'secondary'],
    category: 'Financial',
    sqlExpression: 'SUM(net_sales_amt) / MAX(store_size_sqft)',
    format: 'currency',
    inputs: [
      { key: 'baseline', label: 'Baseline $/sqft', placeholder: 'e.g. 4.2', type: 'number', required: true },
    ],
  },
  {
    id: 'same_store_sales',
    label: 'Comp Store Sales (YoY)',
    description: 'Year-over-year sales growth for stores open at least one year.',
    roles: ['primary', 'secondary'],
    category: 'Financial',
    sqlExpression: '(SUM(current_sales) - SUM(ly_sales)) / NULLIF(SUM(ly_sales), 0)',
    format: 'percentage',
    inputs: [
      { key: 'baseline', label: 'Baseline comp growth (%)', placeholder: 'e.g. 2.5', type: 'number', required: true },
    ],
  },

  // ═══════════════════════════════════════════════════════════════════════════════
  // Traffic & Conversion (5)
  // ═══════════════════════════════════════════════════════════════════════════════
  {
    id: 'traffic',
    label: 'Physical Foot Traffic',
    description: 'Top-of-funnel physical footprint volume captured by door sensors.',
    roles: ['primary', 'secondary'],
    category: 'Traffic & Conversion',
    sqlExpression: 'SUM(sensor_inbound_counts)',
    format: 'number',
    inputs: [
      { key: 'baseline', label: 'Baseline weekly traffic', placeholder: 'e.g. 2500', type: 'number', required: true },
      { key: 'mde', label: 'Min. detectable effect (%)', placeholder: 'e.g. 5', type: 'number', required: true },
    ],
  },
  {
    id: 'conversion_rate',
    label: 'Transaction Conversion Rate',
    description: 'Percentage of foot traffic that completes a POS transaction.',
    roles: ['primary', 'secondary'],
    category: 'Traffic & Conversion',
    sqlExpression: 'SUM(transactions) / NULLIF(SUM(traffic), 0)',
    format: 'percentage',
    inputs: [
      { key: 'baseline', label: 'Baseline conversion (%)', placeholder: 'e.g. 35', type: 'number', required: true },
      { key: 'mde', label: 'Min. detectable effect (%)', placeholder: 'e.g. 2', type: 'number', required: true },
    ],
  },
  {
    id: 'transactions',
    label: 'Total Transaction Count',
    description: 'Distinct count of POS receipts generated.',
    roles: ['primary', 'secondary'],
    category: 'Traffic & Conversion',
    sqlExpression: 'COUNT(DISTINCT pos_receipt_id)',
    format: 'number',
    inputs: [
      { key: 'baseline', label: 'Baseline weekly transactions', placeholder: 'e.g. 900', type: 'number', required: true },
    ],
  },
  {
    id: 'sales_per_traffic',
    label: 'Sales per Visitor',
    description: 'Average revenue generated per individual walking through the door.',
    roles: ['primary', 'secondary'],
    category: 'Traffic & Conversion',
    sqlExpression: 'SUM(net_sales_amt) / NULLIF(SUM(traffic), 0)',
    format: 'currency',
    inputs: [
      { key: 'baseline', label: 'Baseline $/visitor', placeholder: 'e.g. 18.5', type: 'number', required: true },
    ],
  },
  {
    id: 'capture_rate',
    label: 'Curb-to-Inbound Capture',
    description: 'Ratio of in-store traffic versus total pedestrian flow outside the store.',
    roles: ['primary', 'secondary'],
    category: 'Traffic & Conversion',
    sqlExpression: 'SUM(traffic) / NULLIF(SUM(trade_area_pedestrian_flow), 0)',
    format: 'percentage',
    inputs: [
      { key: 'baseline', label: 'Baseline capture rate (%)', placeholder: 'e.g. 12', type: 'number', required: true },
    ],
  },

  // ═══════════════════════════════════════════════════════════════════════════════
  // Basket Mechanics (4)
  // ═══════════════════════════════════════════════════════════════════════════════
  {
    id: 'upt',
    label: 'Units Per Transaction',
    description: 'Average basket depth. Total units divided by total transactions.',
    roles: ['primary', 'secondary'],
    category: 'Basket Mechanics',
    sqlExpression: 'SUM(total_units) / NULLIF(SUM(transactions), 0)',
    format: 'decimal',
    inputs: [
      { key: 'baseline', label: 'Baseline UPT', placeholder: 'e.g. 3.2', type: 'number', required: true },
    ],
  },
  {
    id: 'atv',
    label: 'Average Transaction Value',
    description: 'Average revenue per basket. Equivalent to AUR multiplied by UPT.',
    roles: ['primary', 'secondary'],
    category: 'Basket Mechanics',
    sqlExpression: 'SUM(net_sales_amt) / NULLIF(SUM(transactions), 0)',
    format: 'currency',
    inputs: [
      { key: 'baseline', label: 'Baseline ATV ($)', placeholder: 'e.g. 9.10', type: 'number', required: true },
    ],
  },
  {
    id: 'total_units',
    label: 'Total Physical Units Sold',
    description: 'Raw count of all physical items scanned at the POS.',
    roles: ['primary', 'secondary'],
    category: 'Basket Mechanics',
    sqlExpression: 'SUM(unit_quantity_sold)',
    format: 'number',
    inputs: [
      { key: 'baseline', label: 'Baseline weekly units', placeholder: 'e.g. 3000', type: 'number', required: true },
    ],
  },
  {
    id: 'multi_item_ticket_rate',
    label: 'Multi-Item Ticket Rate',
    description: 'Percentage of transactions containing more than one item.',
    roles: ['primary', 'secondary'],
    category: 'Basket Mechanics',
    sqlExpression: "SUM(CASE WHEN units_in_txn > 1 THEN 1 ELSE 0 END) / NULLIF(COUNT(pos_receipt_id), 0)",
    format: 'percentage',
    inputs: [
      { key: 'baseline', label: 'Baseline multi-item rate (%)', placeholder: 'e.g. 72', type: 'number', required: true },
    ],
  },

  // ═══════════════════════════════════════════════════════════════════════════════
  // Supply Chain (5)
  // ═══════════════════════════════════════════════════════════════════════════════
  {
    id: 'inventory_turnover',
    label: 'Inventory Turnover Ratio',
    description: 'How many times inventory is sold and replaced over a period.',
    roles: ['primary', 'secondary'],
    category: 'Supply Chain',
    sqlExpression: 'SUM(cogs) / NULLIF(AVG(ending_inventory_cost), 0)',
    format: 'decimal',
    inputs: [
      { key: 'baseline', label: 'Baseline turnover ratio', placeholder: 'e.g. 6.2', type: 'number', required: true },
    ],
  },
  {
    id: 'gmroi',
    label: 'Gross Margin Return on Inventory',
    description: 'Total gross profit dollars returned per dollar invested in inventory.',
    roles: ['primary', 'secondary'],
    category: 'Supply Chain',
    sqlExpression: 'SUM(gross_profit_dollars) / NULLIF(AVG(inventory_cost), 0)',
    format: 'decimal',
    inputs: [
      { key: 'baseline', label: 'Baseline GMROI', placeholder: 'e.g. 2.8', type: 'number', required: true },
    ],
  },
  {
    id: 'oos_rate',
    label: 'Out-Of-Stock Rate',
    description: 'Percentage of core SKUs reading zero perpetual inventory.',
    roles: ['primary', 'secondary'],
    category: 'Supply Chain',
    sqlExpression: 'SUM(CASE WHEN inventory_qty <= 0 THEN 1 ELSE 0 END) / NULLIF(COUNT(sku_id), 0)',
    format: 'percentage',
    inputs: [
      { key: 'baseline', label: 'Baseline OOS rate (%)', placeholder: 'e.g. 5', type: 'number', required: true },
    ],
  },
  {
    id: 'shrink_rate',
    label: 'Inventory Shrinkage',
    description: 'Lost inventory value relative to net sales.',
    roles: ['primary', 'secondary'],
    category: 'Supply Chain',
    sqlExpression: '(SUM(book_inventory_value) - SUM(physical_audited_value)) / NULLIF(SUM(net_sales_amt), 0)',
    format: 'percentage',
    inputs: [
      { key: 'baseline', label: 'Baseline shrink rate (%)', placeholder: 'e.g. 2.1', type: 'number', required: true },
    ],
  },
  {
    id: 'returns_rate',
    label: 'Product Return Rate',
    description: 'Dollar value of returns as a percentage of gross sales.',
    roles: ['primary', 'secondary'],
    category: 'Supply Chain',
    sqlExpression: 'SUM(returns_dollars) / NULLIF(SUM(gross_sales_amt), 0)',
    format: 'percentage',
    inputs: [
      { key: 'baseline', label: 'Baseline return rate (%)', placeholder: 'e.g. 3.5', type: 'number', required: true },
    ],
  },

  // ═══════════════════════════════════════════════════════════════════════════════
  // Environmental Confounders (4)
  // ═══════════════════════════════════════════════════════════════════════════════
  {
    id: 'weather_severity',
    label: 'Weather Severity Index',
    description: 'Composite index tracking precipitation, wind, and temperature deviations.',
    roles: ['secondary'],
    category: 'Environmental Confounders',
    sqlExpression: 'AVG(weather_severity_score)',
    format: 'decimal',
    inputs: [
      { key: 'baseline', label: 'Baseline weather index', placeholder: 'e.g. 45', type: 'number', required: true },
    ],
  },
  {
    id: 'economic_index',
    label: 'Local Economic Index',
    description: 'Normalized tracker for local median income and unemployment shifts.',
    roles: ['secondary'],
    category: 'Environmental Confounders',
    sqlExpression: 'AVG(local_economic_score)',
    format: 'decimal',
    inputs: [
      { key: 'baseline', label: 'Baseline economic index', placeholder: 'e.g. 72', type: 'number', required: true },
    ],
  },
  {
    id: 'holiday_density',
    label: 'Holiday Traffic Index',
    description: 'Weighted score for retail holidays falling within the measurement week.',
    roles: ['secondary'],
    category: 'Environmental Confounders',
    sqlExpression: 'SUM(holiday_weight)',
    format: 'decimal',
    inputs: [
      { key: 'baseline', label: 'Baseline holiday index', placeholder: 'e.g. 1.2', type: 'number', required: true },
    ],
  },
  {
    id: 'competitor_intensity',
    label: 'Competitor Promotion Index',
    description: 'Score measuring nearby competitor discount density and footprint.',
    roles: ['secondary'],
    category: 'Environmental Confounders',
    sqlExpression: 'AVG(competitor_intensity_score)',
    format: 'decimal',
    inputs: [
      { key: 'baseline', label: 'Baseline competitor index', placeholder: 'e.g. 3.5', type: 'number', required: true },
    ],
  },
]

// ═══════════════════════════════════════════════════════════════════════════════
// Guardrail Metrics (4) — mandatory floor metrics that must not degrade
// ═══════════════════════════════════════════════════════════════════════════════

export const STORE_GUARDRAIL_OPTIONS: StoreMetricKpiOption[] = [
  {
    id: 'store_traffic_floor',
    label: 'Store Traffic (Footfall Counts)',
    description: 'Mandatory floor ensuring the initiative does not suppress baseline customer footfall.',
    roles: ['guardrail'],
    category: 'Guardrails',
    sqlExpression: 'SUM(traffic)',
    format: 'number',
  },
  {
    id: 'oos_rate_ceiling',
    label: 'Out-of-Stock (OOS) Rate %',
    description: 'Mandatory ceiling on shelf stockout rate — prevents the initiative from starving inventory.',
    roles: ['guardrail'],
    category: 'Guardrails',
    sqlExpression: 'AVG(oos_rate)',
    format: 'percentage',
  },
  {
    id: 'checkout_wait_time_ceiling',
    label: 'Customer Checkout Wait Time (Minutes)',
    description: 'Mandatory ceiling on checkout wait time — flags if labor/staffing changes degrade service speed.',
    roles: ['guardrail'],
    category: 'Guardrails',
    sqlExpression: 'AVG(checkout_wait_minutes)',
    format: 'decimal',
  },
  {
    id: 'labor_overtime_budget_ceiling',
    label: 'Labor Overtime Budget ($)',
    description: 'Mandatory ceiling on labor overtime spend attributable to the initiative.',
    roles: ['guardrail'],
    category: 'Guardrails',
    sqlExpression: 'SUM(labor_overtime_cost)',
    format: 'currency',
  },
]

// ═══════════════════════════════════════════════════════════════════════════════
// Combined catalog + utility functions
// ═══════════════════════════════════════════════════════════════════════════════

export const ALL_STORE_METRICS: StoreMetricKpiOption[] = [
  ...STORE_METRIC_KPI_OPTIONS,
  ...STORE_GUARDRAIL_OPTIONS,
]

export const STORE_METRIC_BY_ID = Object.fromEntries(
  ALL_STORE_METRICS.map((k) => [k.id, k]),
) as Record<string, StoreMetricKpiOption>

/**
 * Intent-based search keywords per KPI — lets users search "cvr" or
 * "conversion" and find Transaction Conversion Rate without needing to know
 * the exact catalog label. Used by StoreMetricsStep to enrich the KPI
 * dropdown options passed to MultiSelectDropdown's search/ranking.
 */
export const STORE_KPI_SEARCH_KEYWORDS: Record<string, string[]> = {
  total_sales: ['gross sales', 'revenue', 'top line', 'total revenue'],
  net_sales: ['net revenue', 'sales after returns'],
  aur: ['average unit retail', 'price point', 'unit price', 'avg price'],
  gross_margin: ['margin', 'profit margin', 'gp', 'gross profit percent'],
  markdown_rate: ['markdown', 'discount rate', 'promo rate'],
  sales_per_sqft: ['sales per square foot', 'space productivity', 'sq ft productivity'],
  same_store_sales: ['comp sales', 'comps', 'yoy sales', 'same store', 'sss'],
  traffic: ['foot traffic', 'footfall', 'visits', 'store visits', 'walk-ins'],
  conversion_rate: ['cvr', 'conversion', 'conv rate', 'close rate', 'buy rate'],
  transactions: ['txn count', 'basket count', 'receipts', 'transaction count'],
  sales_per_traffic: ['sales per visitor', 'revenue per visitor'],
  capture_rate: ['curb to inbound', 'pedestrian capture'],
  upt: ['units per transaction', 'units per basket', 'basket depth'],
  atv: ['average transaction value', 'basket size', 'average ticket', 'atv'],
  total_units: ['unit volume', 'units sold', 'item count'],
  multi_item_ticket_rate: ['multi item', 'basket attachment', 'attach rate'],
  inventory_turnover: ['turns', 'stock turnover', 'inventory turns'],
  gmroi: ['margin return on inventory', 'inventory profitability'],
  oos_rate: ['out of stock', 'stockout', 'oos'],
  shrink_rate: ['shrinkage', 'inventory loss', 'theft'],
  returns_rate: ['returns', 'return rate', 'refund rate'],
  weather_severity: ['weather', 'weather index'],
  economic_index: ['economy', 'local economy', 'unemployment', 'income'],
  holiday_density: ['holiday', 'seasonality', 'holiday weeks'],
  competitor_intensity: ['competition', 'competitor', 'competitive pressure'],
  store_traffic_floor: ['footfall', 'traffic guardrail', 'visit floor', 'foot traffic'],
  oos_rate_ceiling: ['out of stock', 'stockout', 'oos', 'shelf stockout'],
  checkout_wait_time_ceiling: ['checkout wait', 'wait time', 'queue time', 'line length'],
  labor_overtime_budget_ceiling: ['overtime', 'labor overtime', 'ot budget', 'labor cost'],
}

export function getStoreKpisForRole(role: MetricRole): StoreMetricKpiOption[] {
  return ALL_STORE_METRICS.filter((k) => k.roles.includes(role))
}

export function getStoreKpisByCategory(category: StoreMetricCategory): StoreMetricKpiOption[] {
  return ALL_STORE_METRICS.filter((k) => k.category === category)
}

export function getStoreMetricInputsForSelection(selectedIds: string[]): {
  kpiId: string
  label: string
  inputs: MetricInputField[]
}[] {
  return selectedIds
    .map((id) => STORE_METRIC_BY_ID[id])
    .filter((k): k is StoreMetricKpiOption => Boolean(k?.inputs?.length))
    .map((k) => ({ kpiId: k.id, label: k.label, inputs: k.inputs! }))
}

/**
 * Maps a store metric ID to the SQL expression needed to compute it.
 * Used by the Flask backend to generate queries against UC tables.
 */
export function getStoreMetricSqlExpression(metricId: string): string | null {
  const metric = STORE_METRIC_BY_ID[metricId]
  if (!metric) return null
  return metric.sqlExpression
}

/**
 * Returns the expected lag (in weeks) for an initiative category.
 * Used by the power calculator to determine minimum experiment duration.
 */
export const INITIATIVE_CATEGORY_LAG: Record<string, number> = {
  Assortment: 3,
  Staffing: 4,
  Remodel: 8,
  Pricing: 4,
  Marketing: 3,
}
