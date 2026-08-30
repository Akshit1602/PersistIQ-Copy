import type { ModuleId } from '../context/types'
import {
  createSuggestionContext,
  prefillableValues,
  suggestFieldValues,
  type SuggestionContext,
} from './inputSuggestions'

export interface ExperimentBaselines {
  baselineIor: number
  mdePercent: number
  alpha: number
  statisticalPower: number
  variants: number
  dailyTraffic: number
  trafficFraction: number
}

/**
 * Conventions, not data. Significance, power, and traffic fraction are design
 * choices with no baseline to detect, so they stay fixed here; everything a
 * dataset can actually answer comes from the suggestion engine instead.
 */
const DESIGN_CONVENTIONS: ExperimentBaselines = {
  baselineIor: 0.18,
  mdePercent: 10,
  alpha: 0.05,
  statisticalPower: 0.8,
  variants: 2,
  dailyTraffic: 500,
  trafficFraction: 1,
}

/**
 * Power-calculator starting point for an experiment. Pass a suggestion context
 * (the app does, via MatchViewContext) to get values derived from the
 * experiment's own data; without one this returns the design conventions.
 */
export function getExperimentBaselines(
  experiment: string,
  ctx?: SuggestionContext,
): ExperimentBaselines {
  const suggestions = suggestFieldValues(
    'power-calculator',
    ctx ?? createSuggestionContext({ experiment }),
  )

  const numeric = (key: keyof ExperimentBaselines): number => {
    const value = suggestions[key]?.value
    return typeof value === 'number' && !Number.isNaN(value) ? value : DESIGN_CONVENTIONS[key]
  }

  return {
    baselineIor: numeric('baselineIor'),
    mdePercent: numeric('mdePercent'),
    alpha: DESIGN_CONVENTIONS.alpha,
    statisticalPower: DESIGN_CONVENTIONS.statisticalPower,
    variants: numeric('variants'),
    dailyTraffic: numeric('dailyTraffic'),
    trafficFraction: DESIGN_CONVENTIONS.trafficFraction,
  }
}

/**
 * Fills the blanks in a partially-specified module payload. Only high/medium
 * confidence suggestions are written; benchmark-grade values stay behind the
 * click-to-apply chip in the form UI.
 */
export function fillModuleDefaults(
  moduleId: ModuleId,
  experiment: string,
  partial: Record<string, unknown>,
  ctx?: SuggestionContext,
): { values: Record<string, unknown>; autoFilled: string[] } {
  const context = ctx ?? createSuggestionContext({ experiment })
  const suggestions = suggestFieldValues(moduleId, context)
  const { values: suggested, filledKeys } = prefillableValues(suggestions, partial)

  const values = { ...partial, ...suggested }
  const autoFilled = [...filledKeys]

  if (moduleId === 'power-calculator') {
    // Design conventions have no data source, so they are filled but never
    // badged as detected.
    const baselines = getExperimentBaselines(experiment, context)
    for (const key of ['alpha', 'statisticalPower', 'trafficFraction', 'mdePercent'] as const) {
      if (values[key] === undefined || values[key] === null || values[key] === '') {
        values[key] = baselines[key]
        autoFilled.push(key)
      }
    }
  }

  if (
    (moduleId === 'opportunity-sizing' || moduleId === 'experiment-type') &&
    (values.channelScope === undefined || values.channelScope === '')
  ) {
    values.channelScope = context.channel
    autoFilled.push('channelScope')
  }

  return { values, autoFilled: [...new Set(autoFilled)] }
}
