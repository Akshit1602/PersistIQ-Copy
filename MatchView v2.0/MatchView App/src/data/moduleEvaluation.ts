import type { ModuleId } from '../context/types'
import { MODULE_BY_ID } from './moduleRegistry'

export interface PowerCurvePoint {
  sampleSize: number
  power: number
}

export interface PowerCurveEvaluation {
  targetSampleSize: number
  achievedPower: number
  alpha: number
  beta: number
  mde: number
  baseline: number
  curvePoints: PowerCurvePoint[]
  durationDays?: number
}

export function computePowerCurveEvaluation(
  params: Record<string, unknown>,
): PowerCurveEvaluation {
  const baselineIor = Number(params.baselineIor ?? params.baseline ?? 0.18)
  // Treat percent-scale baselines (legacy) as rates for the curve formula
  const baseline = baselineIor > 1 ? baselineIor / 100 : baselineIor
  const mde = Number(params.mdePercent ?? params.mde ?? 10)
  const alpha = Number(params.alpha ?? 0.05)
  const statisticalPower = Number(
    params.statisticalPower ?? (params.beta !== undefined ? 1 - Number(params.beta) : 0.8),
  )
  const beta = 1 - statisticalPower
  const variants = Math.max(2, Number(params.variants ?? 2))
  const dailyTraffic = Number(params.dailyTraffic ?? 500)
  const trafficFraction = Number(params.trafficFraction ?? 1)

  const targetSampleSize = Math.round(
    ((16 * baseline * (1 - baseline)) / ((mde / 100) * (mde / 100))) *
      Math.log(1 / alpha) *
      (1 / statisticalPower) *
      variants,
  )

  const dailyEligible = Math.max(1, dailyTraffic * trafficFraction)
  const durationDays = Math.ceil(targetSampleSize / dailyEligible)

  const minN = Math.round(targetSampleSize * 0.45)
  const maxN = Math.round(targetSampleSize * 1.15)
  const curvePoints: PowerCurvePoint[] = Array.from({ length: 24 }, (_, i) => {
    const sampleSize = Math.round(minN + (i / 23) * (maxN - minN))
    const progress = (sampleSize - minN) / (maxN - minN)
    const power = Math.min(0.995, 0.35 + progress * (statisticalPower - 0.35) * 1.05)
    return { sampleSize, power: Number(power.toFixed(3)) }
  })

  return {
    targetSampleSize,
    achievedPower: statisticalPower,
    alpha,
    beta,
    mde,
    baseline,
    curvePoints,
    durationDays,
  }
}

export function buildModuleEvaluation(
  moduleId: ModuleId,
  params: Record<string, unknown>,
): import('../context/types').ModuleEvaluationPayload {
  const mod = MODULE_BY_ID[moduleId]

  if (moduleId === 'power-calculator') {
    const powerCurve = computePowerCurveEvaluation(params)
    const durationNote =
      powerCurve.durationDays !== undefined
        ? ` · ~${powerCurve.durationDays} day${powerCurve.durationDays === 1 ? '' : 's'}`
        : ''
    return {
      type: 'power-curve',
      powerCurve,
      summary: `${mod.label}: ${(powerCurve.achievedPower * 100).toFixed(0)}% power at n=${powerCurve.targetSampleSize.toLocaleString()} (α=${powerCurve.alpha}, MDE=${powerCurve.mde}%)${durationNote}.`,
    }
  }

  if (moduleId === 'opportunity-sizing') {
    const inquiries = Number(params.monthlyInquiries ?? 0)
    const current = Number(params.currentIor ?? 0)
    const target = Number(params.targetIor ?? 0)
    const aov = Number(params.aov ?? 0)
    const margin = Number(params.grossMargin ?? 0)
    const horizon = Number(params.timeHorizonMonths ?? 12)
    const liftPts = target > current ? Math.round((target - current) * 1000) / 10 : 0
    const monthlyRevenue = Math.round(inquiries * (target - current) * aov * margin)
    return {
      type: 'generic',
      summary: `${mod.label}: IOR ${current} → ${target} (+${liftPts} pts) on ${inquiries.toLocaleString()} monthly inquiries · ~$${monthlyRevenue.toLocaleString()}/mo at ${horizon} months.`,
    }
  }

  if (moduleId === 'metrics-tracking') {
    const feature = String(params.featureDescription ?? '').trim()
    const maturity = String(params.experimentMaturity ?? 'mvp')
    return {
      type: 'generic',
      summary: feature
        ? `${mod.label}: ${maturity} maturity — ${feature}`
        : `${mod.label}: Add a feature description and experiment maturity to continue.`,
    }
  }

  if (moduleId === 'experiment-type') {
    return {
      type: 'generic',
      summary: `${mod.label}: Recommended ${params.experimentType} digital design — ${params.typeRationale ?? 'see rationale in lab.'}`,
    }
  }

  if (moduleId === 'audience-selection') {
    return {
      type: 'generic',
      summary: `${mod.label}: ${params.segment} at ${params.trafficPercent}% traffic (digital). Exclusions: ${params.exclusions || 'none'}.`,
    }
  }

  if (moduleId === 'brief-generator') {
    const body = String(params.briefBody ?? '')
    const preview = body.length > 120 ? `${body.slice(0, 120)}…` : body
    return {
      type: 'generic',
      summary: `${mod.label}: Brief drafted — ${preview || 'open Analytics Lab for full handoff artifact.'}`,
    }
  }

  return {
    type: 'generic',
    summary: `${mod.label} completed with the locked parameter snapshot.`,
  }
}
