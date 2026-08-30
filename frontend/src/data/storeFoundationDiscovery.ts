/**
 * Store Channel — Foundation & Discovery (6 modules)
 *
 * Each module gets distinct, store-specific curated data (not generic
 * web-analytics placeholders) plus an explicit link back to the active
 * hypothesis being validated by that data layer.
 */

export interface ChartPoint {
  label: string
  value: number
}

export interface SegmentItem {
  label: string
  value: number
  unit?: string
}

export interface MetricItem {
  label: string
  value: string
  status?: 'good' | 'warn' | 'bad'
}

export interface FoundationModuleData {
  hypothesisContext: string
  storeDefinition: string
  primaryChart: { title: string; unit: string; points: ChartPoint[] }
  segmentBreakdown: { title: string; segments: SegmentItem[] }
  metricSheet: { title: string; metrics: MetricItem[] }
}

export type FoundationModuleKey =
  | 'data-validation'
  | 'dimension-setup'
  | 'distribution-shift'
  | 'pipeline-health'
  | 'schema-discovery'
  | 'watchtower'

export const FOUNDATION_MODULE_DATA: Record<FoundationModuleKey, FoundationModuleData> = {
  'data-validation': {
    hypothesisContext:
      'Active Hypothesis: Weekend Promotion Lift — cannot be validated if POS transaction data itself is unreliable.',
    storeDefinition:
      'Ensures daily POS logs, inventory counts, and supplier invoices are accurate, complete, and free of corruption or missing values.',
    primaryChart: {
      title: 'Daily Transaction Accuracy Rate (14-day window, target 99.9%)',
      unit: '%',
      points: [
        { label: 'D1', value: 99.82 }, { label: 'D2', value: 99.85 }, { label: 'D3', value: 99.79 },
        { label: 'D4', value: 99.91 }, { label: 'D5', value: 99.88 }, { label: 'D6', value: 99.93 },
        { label: 'D7', value: 99.9 }, { label: 'D8', value: 99.86 }, { label: 'D9', value: 99.94 },
        { label: 'D10', value: 99.92 }, { label: 'D11', value: 99.89 }, { label: 'D12', value: 99.95 },
        { label: 'D13', value: 99.91 }, { label: 'D14', value: 99.93 },
      ],
    },
    segmentBreakdown: {
      title: 'Error Rate by POS Terminal',
      segments: [
        { label: 'Register 1', value: 0.18, unit: '%' },
        { label: 'Register 2', value: 0.09, unit: '%' },
        { label: 'Self-Checkout', value: 0.31, unit: '%' },
      ],
    },
    metricSheet: {
      title: 'Data Integrity Metrics',
      metrics: [
        { label: 'Missing Barcode Scans', value: '0.12%', status: 'good' },
        { label: 'Duplicate Transaction IDs', value: '0', status: 'good' },
        { label: 'Negative Inventory Anomalies', value: '3 SKUs flagged', status: 'warn' },
      ],
    },
  },

  'dimension-setup': {
    hypothesisContext:
      'Active Hypothesis: Beverage Discount Effectiveness — needs dimension slicing (Aisle 3 vs. Checkout) to compare.',
    storeDefinition:
      'Categorizes raw store data into meaningful retail dimensions: product hierarchy, store zones, and customer segments.',
    primaryChart: {
      title: 'Revenue Contribution by Store Zone',
      unit: '%',
      points: [
        { label: 'Aisles', value: 54 },
        { label: 'End-caps', value: 28 },
        { label: 'Checkout Counters', value: 18 },
      ],
    },
    segmentBreakdown: {
      title: 'Basket Size by Customer Loyalty Tier',
      segments: [
        { label: 'Regular', value: 4.8, unit: 'items' },
        { label: 'Occasional', value: 3.1, unit: 'items' },
        { label: 'New', value: 2.4, unit: 'items' },
      ],
    },
    metricSheet: {
      title: 'Dimension Mapping Metrics',
      metrics: [
        { label: 'Active SKUs Mapped', value: '1,420', status: 'good' },
        { label: 'Unassigned Barcodes', value: '0', status: 'good' },
        { label: 'Active Promotion Dimensions', value: '4 categories', status: 'good' },
      ],
    },
  },

  'distribution-shift': {
    hypothesisContext:
      'Active Hypothesis: Store Layout Redesign v2 — must rule out unrelated footfall/weather shifts before crediting the layout.',
    storeDefinition:
      'Detects unexpected shifts in customer purchasing behavior, payment methods, or traffic patterns vs. historical baselines.',
    primaryChart: {
      title: 'Peak vs. Off-Peak Footfall Trend (this week vs. 30-day baseline)',
      unit: 'visits',
      points: [
        { label: '8am', value: 42 }, { label: '10am', value: 78 }, { label: '12pm', value: 145 },
        { label: '2pm', value: 118 }, { label: '4pm', value: 96 }, { label: '6pm', value: 162 },
        { label: '8pm', value: 88 },
      ],
    },
    segmentBreakdown: {
      title: 'Shift in Payment Preferences (vs. baseline)',
      segments: [
        { label: 'Digital (UPI/Card)', value: 14, unit: '% \u2191' },
        { label: 'Cash', value: -11, unit: '% \u2193' },
      ],
    },
    metricSheet: {
      title: 'Distribution Shift Metrics',
      metrics: [
        { label: 'Cold Beverages Demand', value: '+28%', status: 'good' },
        { label: 'Hot Snacks Demand', value: '-12%', status: 'warn' },
        { label: 'Footfall Variance', value: '+4.2%', status: 'good' },
      ],
    },
  },

  'pipeline-health': {
    hypothesisContext:
      'Active Hypothesis: Dynamic Digital Shelf Pricing Flash Sale — requires real-time data with no latency artifacts.',
    storeDefinition:
      'Monitors the technical infrastructure and real-time data flow from physical hardware to the local/cloud database.',
    primaryChart: {
      title: 'Data Sync Latency over 24 Hours',
      unit: 'sec',
      points: [
        { label: '00:00', value: 0.9 }, { label: '04:00', value: 0.8 }, { label: '08:00', value: 1.6 },
        { label: '12:00', value: 2.1 }, { label: '16:00', value: 1.8 }, { label: '20:00', value: 1.1 },
      ],
    },
    segmentBreakdown: {
      title: 'Hardware Uptime by Device Type',
      segments: [
        { label: 'POS Terminals', value: 99.97, unit: '%' },
        { label: 'Barcode Scanners', value: 99.89, unit: '%' },
        { label: 'Receipt Printers', value: 99.72, unit: '%' },
      ],
    },
    metricSheet: {
      title: 'Pipeline Health Metrics',
      metrics: [
        { label: 'Average Sync Delay', value: '1.2s', status: 'good' },
        { label: 'Offline POS Incidents', value: '0', status: 'good' },
        { label: 'Database API Error Rate', value: '0.001%', status: 'good' },
      ],
    },
  },

  'schema-discovery': {
    hypothesisContext:
      'Active Hypothesis: Salty Snacks Promotion — new arrivals must auto-join the category test, not require manual setup.',
    storeDefinition:
      'Automatically detects and categorizes new SKUs, supplier tags, or pricing tiers added to the store database.',
    primaryChart: {
      title: 'New SKU Discovery Rate (per week)',
      unit: 'SKUs',
      points: [
        { label: 'W1', value: 6 }, { label: 'W2', value: 9 }, { label: 'W3', value: 5 },
        { label: 'W4', value: 14 }, { label: 'W5', value: 8 }, { label: 'W6', value: 11 },
      ],
    },
    segmentBreakdown: {
      title: 'Newly Discovered Items by Supplier',
      segments: [
        { label: 'Local Snack Co.', value: 6 },
        { label: 'National Beverage Corp.', value: 4 },
        { label: 'Regional Dairy', value: 3 },
        { label: 'Other', value: 1 },
      ],
    },
    metricSheet: {
      title: 'Schema Discovery Metrics',
      metrics: [
        { label: 'Auto-Mapped SKUs', value: '14 this week', status: 'good' },
        { label: 'Schema Conflicts', value: '1 price mismatch flagged', status: 'warn' },
        { label: 'New Attributes Added', value: '2', status: 'good' },
      ],
    },
  },

  watchtower: {
    hypothesisContext:
      'Active Hypothesis: Endcap Pricing Test — Watchtower pauses the test if a top-seller sells out too fast.',
    storeDefinition:
      'The automated alert system watching for critical operational risks, stockouts, or severe financial anomalies in real time.',
    primaryChart: {
      title: 'Real-Time Stock Depletion — Top-10 Fast-Moving Items',
      unit: '% remaining',
      points: [
        { label: '6am', value: 100 }, { label: '9am', value: 88 }, { label: '12pm', value: 61 },
        { label: '3pm', value: 34 }, { label: '6pm', value: 12 }, { label: '9pm', value: 4 },
      ],
    },
    segmentBreakdown: {
      title: 'Alerts by Severity',
      segments: [
        { label: 'Critical Stockouts', value: 2 },
        { label: 'Low Stock Warnings', value: 5 },
        { label: 'Cashier Overrides', value: 1 },
      ],
    },
    metricSheet: {
      title: 'Watchtower Guardrail Metrics',
      metrics: [
        { label: 'Active Stockout Alerts', value: '2 SKUs', status: 'bad' },
        { label: 'High Void Rate Alerts', value: 'Register 3 flagged', status: 'warn' },
        { label: 'Guardrail Status', value: 'Secure', status: 'good' },
      ],
    },
  },
}
