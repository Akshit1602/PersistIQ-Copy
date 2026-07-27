import type { ModuleId } from '../context/types'

export interface ExperimentBaselines {
  baselineIor: number
  mdePercent: number
  alpha: number
  statisticalPower: number
  variants: number
  dailyTraffic: number
  trafficFraction: number
}

const EXPERIMENT_BASELINES: Record<string, ExperimentBaselines> = {
  'Walmart Banner Redesign': {
    baselineIor: 0.18,
    mdePercent: 10,
    alpha: 0.05,
    statisticalPower: 0.8,
    variants: 2,
    dailyTraffic: 500,
    trafficFraction: 1,
  },
  'Cart Flow Optimization': {
    baselineIor: 0.22,
    mdePercent: 8,
    alpha: 0.05,
    statisticalPower: 0.8,
    variants: 2,
    dailyTraffic: 750,
    trafficFraction: 1,
  },
  'Holiday Promo Lift Test': {
    baselineIor: 0.15,
    mdePercent: 12,
    alpha: 0.01,
    statisticalPower: 0.9,
    variants: 3,
    dailyTraffic: 1200,
    trafficFraction: 0.5,
  },
}

export function getExperimentBaselines(experiment: string): ExperimentBaselines {
  const stored = EXPERIMENT_BASELINES[experiment]
  if (stored) return { ...stored }

  return {
    baselineIor: 0.18,
    mdePercent: 10,
    alpha: 0.05,
    statisticalPower: 0.8,
    variants: 2,
    dailyTraffic: 500,
    trafficFraction: 1,
  }
}

export function fillModuleDefaults(
  moduleId: ModuleId,
  experiment: string,
  partial: Record<string, unknown>,
): { values: Record<string, unknown>; autoFilled: string[] } {
  const baselines = getExperimentBaselines(experiment)
  const autoFilled: string[] = []
  const values = { ...partial }

  if (moduleId === 'power-calculator') {
    const defaults: Record<string, unknown> = {
      baselineIor: baselines.baselineIor,
      mdePercent: baselines.mdePercent,
      alpha: baselines.alpha,
      statisticalPower: baselines.statisticalPower,
      variants: baselines.variants,
      dailyTraffic: baselines.dailyTraffic,
      trafficFraction: baselines.trafficFraction,
    }
    for (const [key, value] of Object.entries(defaults)) {
      if (values[key] === undefined || values[key] === null || values[key] === '') {
        values[key] = value
        autoFilled.push(key)
      }
    }
  }

  if (moduleId === 'opportunity-sizing') {
    if (values.channelScope === undefined || values.channelScope === '') {
      values.channelScope = 'digital'
      autoFilled.push('channelScope')
    }
  }

  if (moduleId === 'experiment-type') {
    if (values.channelScope === undefined || values.channelScope === '') {
      values.channelScope = 'digital'
      autoFilled.push('channelScope')
    }
  }

  return { values, autoFilled }
}
