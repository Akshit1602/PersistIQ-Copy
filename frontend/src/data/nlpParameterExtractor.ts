import type { ModuleId } from '../context/types'
import { fillModuleDefaults } from './experimentBaselines'
import { MODULE_BY_ID, MODULE_LIST } from './moduleRegistry'

export interface NlpExtractionResult {
  moduleId: ModuleId
  params: Record<string, unknown>
  touchedFields: string[]
  autoFilledFields: string[]
}

const MODULE_ALIASES: [RegExp, ModuleId][] = [
  [/power\s*calc(ulator)?|sample\s*size|statistical\s*power/i, 'power-calculator'],
  [/causal\s*(did|difference)/i, 'causal-did'],
  [/simpson'?s?\s*paradox/i, 'simpsons-paradox'],
  [/schema\s*(discovery|scan)/i, 'schema-discovery'],
  [/data\s*validat/i, 'data-validation'],
  [/health\s*monitor|srm|sample\s*ratio/i, 'health-monitor'],
  [/opportun(ity)?\s*siz|size\s+(the\s+)?(market|opportunity)|validate\s+hypothesis/i, 'opportunity-sizing'],
  [/brief\s*generat/i, 'brief-generator'],
  [/approv(e|ing)?\s+metrics|primary\s*,?\s*secondary|guardrail\s+metrics|metrics?\s*track/i, 'metrics-tracking'],
  [/experiment\s*type|a\/b\/c|recommend\s+(a\/b|type)/i, 'experiment-type'],
  [/audience\s*select|traffic\s*(split|alloc)/i, 'audience-selection'],
  [/compute|calculat|required\s*sample/i, 'power-calculator'],
]

function findModuleInText(text: string): ModuleId | null {
  for (const [pattern, moduleId] of MODULE_ALIASES) {
    if (pattern.test(text)) return moduleId
  }
  const lower = text.toLowerCase()
  for (const mod of MODULE_LIST) {
    if (lower.includes(mod.label.toLowerCase())) return mod.id
  }
  return null
}

function extractPowerCalculatorParams(text: string): Record<string, unknown> {
  const params: Record<string, unknown> = {}

  const alphaMatch =
    text.match(/alpha\s*[=:]\s*(0\.\d+)/i) ??
    text.match(/α\s*[=:]\s*(0\.\d+)/i) ??
    text.match(/at\s+alpha\s*(0\.\d+)/i)
  if (alphaMatch?.[1]) params.alpha = parseFloat(alphaMatch[1])

  const powerMatch =
    text.match(/(\d{2,3})\s*%\s*power/i) ??
    text.match(/power\s*(?:of|at)\s*(\d{2,3})\s*%/i) ??
    text.match(/(\d{2,3})\s*%\s*statistical\s*power/i) ??
    text.match(/1\s*[-−]\s*β\s*[=:]\s*(0\.\d+)/i) ??
    text.match(/statistical\s*power\s*[=:]\s*(0\.\d+)/i)
  if (powerMatch?.[1]) {
    const raw = parseFloat(powerMatch[1])
    params.statisticalPower = raw > 1 ? raw / 100 : raw
  }

  const mdeMatch =
    text.match(/mde\s*[=:]\s*([\d.]+)\s*%?/i) ??
    text.match(/minimum\s+detectable\s+effect\s*[=:]?\s*([\d.]+)/i)
  if (mdeMatch?.[1]) params.mdePercent = parseFloat(mdeMatch[1])

  const baselineMatch =
    text.match(/baseline\s*(?:ior)?\s*[=:]\s*(0\.\d+)/i) ??
    text.match(/ior\s*(?:rate)?\s*[=:]\s*(0\.\d+)/i)
  if (baselineMatch?.[1]) params.baselineIor = parseFloat(baselineMatch[1])

  const variantsMatch = text.match(/(\d+)\s*variants?/i)
  if (variantsMatch?.[1]) params.variants = parseInt(variantsMatch[1], 10)

  const trafficMatch =
    text.match(/(\d[\d,]*)\s*daily\s*(?:eligible\s*)?(?:traffic|inquiries)/i) ??
    text.match(/daily\s*(?:traffic|inquiries)\s*[=:]?\s*(\d[\d,]*)/i)
  if (trafficMatch?.[1]) {
    params.dailyTraffic = parseInt(trafficMatch[1].replace(/,/g, ''), 10)
  }

  const fractionMatch = text.match(/traffic\s*fraction\s*[=:]\s*(0\.\d+|1(?:\.0+)?)/i)
  if (fractionMatch?.[1]) params.trafficFraction = parseFloat(fractionMatch[1])

  return params
}

function extractOpportunitySizingParams(text: string): Record<string, unknown> {
  const params: Record<string, unknown> = {}

  const volumeMatch =
    text.match(/(\d[\d,]*)\s*(k|m)?\s*(?:\/\s*week|weekly|volume)/i) ??
    text.match(/volume\s*[=:]?\s*(\d[\d,]*)\s*(k|m)?/i)
  if (volumeMatch?.[1]) {
    let n = parseInt(volumeMatch[1].replace(/,/g, ''), 10)
    const unit = (volumeMatch[2] ?? '').toLowerCase()
    if (unit === 'k') n *= 1000
    if (unit === 'm') n *= 1_000_000
    params.addressableVolume = n
  }

  const liftMatch =
    text.match(/(\d+(?:\.\d+)?)\s*%\s*lift/i) ??
    text.match(/expected\s+lift\s*[=:]?\s*(\d+(?:\.\d+)?)/i)
  if (liftMatch?.[1]) params.expectedLift = parseFloat(liftMatch[1])

  const ciMatch = text.match(/(\d{2})\s*%\s*(ci|confidence)/i)
  if (ciMatch?.[1]) {
    const pct = parseInt(ciMatch[1], 10)
    if (pct >= 90) params.confidenceBand = '0.90'
    else if (pct >= 80) params.confidenceBand = '0.80'
    else params.confidenceBand = '0.70'
  }

  if (/digital/i.test(text)) params.channelScope = 'digital'

  return params
}

function isAnalyticalCommand(text: string): boolean {
  return (
    /compute|calculat|sample\s*size|power|alpha|beta|mde|configure|adjust|set\s+|size\s+|approv|proceed|suggest|recommend|validate\s+hypothesis/i.test(
      text,
    ) || findModuleInText(text) !== null
  )
}

export function extractNlpParameters(
  text: string,
  experiment: string,
  activeModuleId: ModuleId | null,
): NlpExtractionResult | null {
  if (!isAnalyticalCommand(text)) return null

  const moduleId = findModuleInText(text) ?? activeModuleId ?? 'opportunity-sizing'
  let partial: Record<string, unknown> = {}

  if (moduleId === 'power-calculator') {
    partial = extractPowerCalculatorParams(text)
  } else if (moduleId === 'opportunity-sizing') {
    partial = extractOpportunitySizingParams(text)
  } else if (moduleId === 'metrics-tracking') {
    if (/mvp|iteration|critical/i.test(text)) {
      const maturity = text.match(/\b(mvp|iteration|critical)\b/i)?.[1]?.toLowerCase()
      if (maturity) partial = { ...partial, experimentMaturity: maturity }
    }
    const featureMatch = text.match(/feature[:\s]+(.+)/i)
    if (featureMatch?.[1]) {
      partial = { ...partial, featureDescription: featureMatch[1].trim() }
    }
  }

  const touchedFields = Object.keys(partial)
  const { values, autoFilled } = fillModuleDefaults(moduleId, experiment, partial)

  return {
    moduleId,
    params: values,
    touchedFields,
    autoFilledFields: autoFilled,
  }
}

export function buildNlpSyncReply(
  moduleId: ModuleId,
  touchedFields: string[],
  autoFilledFields: string[],
): string {
  const mod = MODULE_BY_ID[moduleId]
  const parsed =
    touchedFields.length > 0
      ? `Parsed ${touchedFields.join(', ')} from your prompt`
      : `Opened ${mod.label}`
  const filled =
    autoFilledFields.length > 0
      ? ` — suggested inputs applied for ${autoFilledFields.join(', ')}`
      : ''
  return `${parsed}${filled}. Review the Analytics Lab panel and click Run Analytical Model (or press Ctrl+Enter) when ready.`
}
