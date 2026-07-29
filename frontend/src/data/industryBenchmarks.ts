import type { FunnelStage } from './metricClassifier'

export interface OpportunityBenchmarkValues {
  addressableVolume: number
  monthlyInquiries: number
  currentInteractionRate: number
  targetInteractionRate: number
  aov: number
  grossMargin: number
  timeHorizonWeeks: number
}

const INDUSTRY_BY_STAGE: Record<FunnelStage, OpportunityBenchmarkValues> = {
  acquisition: {
    addressableVolume: 400000,
    monthlyInquiries: 120000,
    currentInteractionRate: 2.4,
    targetInteractionRate: 3.1,
    aov: 68,
    grossMargin: 32,
    timeHorizonWeeks: 8,
  },
  activation: {
    addressableVolume: 180000,
    monthlyInquiries: 45000,
    currentInteractionRate: 18,
    targetInteractionRate: 22,
    aov: 55,
    grossMargin: 34,
    timeHorizonWeeks: 8,
  },
  retention: {
    addressableVolume: 220000,
    monthlyInquiries: 80000,
    currentInteractionRate: 28,
    targetInteractionRate: 34,
    aov: 72,
    grossMargin: 36,
    timeHorizonWeeks: 12,
  },
  monetization: {
    addressableVolume: 250000,
    monthlyInquiries: 95000,
    currentInteractionRate: 8.6,
    targetInteractionRate: 10.5,
    aov: 84,
    grossMargin: 38,
    timeHorizonWeeks: 8,
  },
  engagement: {
    addressableVolume: 300000,
    monthlyInquiries: 110000,
    currentInteractionRate: 12,
    targetInteractionRate: 15,
    aov: 48,
    grossMargin: 30,
    timeHorizonWeeks: 4,
  },
}

function blend(industry: number, current: number | undefined, weightIndustry = 0.8): number {
  if (current === undefined || current === 0 || Number.isNaN(current)) return industry
  return Math.round((industry * weightIndustry + current * (1 - weightIndustry)) * 10) / 10
}

/** ~80% industry benchmark / ~20% blend toward existing user values. */
export function suggestIndustryBenchmarks(
  funnelStage: FunnelStage,
  existing?: Partial<OpportunityBenchmarkValues>,
): OpportunityBenchmarkValues {
  const industry = INDUSTRY_BY_STAGE[funnelStage] ?? INDUSTRY_BY_STAGE.monetization
  return {
    addressableVolume: Math.round(
      blend(industry.addressableVolume, existing?.addressableVolume, 0.8),
    ),
    monthlyInquiries: Math.round(
      blend(industry.monthlyInquiries, existing?.monthlyInquiries, 0.8),
    ),
    currentInteractionRate: blend(
      industry.currentInteractionRate,
      existing?.currentInteractionRate,
      0.8,
    ),
    targetInteractionRate: blend(
      industry.targetInteractionRate,
      existing?.targetInteractionRate,
      0.8,
    ),
    aov: blend(industry.aov, existing?.aov, 0.8),
    grossMargin: blend(industry.grossMargin, existing?.grossMargin, 0.8),
    timeHorizonWeeks: industry.timeHorizonWeeks,
  }
}
