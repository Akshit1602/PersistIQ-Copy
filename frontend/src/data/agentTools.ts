/**
 * Agent tool definitions for the MatchView intelligent chat interface.
 * These tools are passed to the FMAPI chat completion endpoint so the LLM
 * can call them when it detects user intent to run an analytical module.
 */

import type { ModuleId } from '../context/types'

// ─── OpenAI-compatible tool schema types ────────────────────────────────────

export interface ToolParameterProperty {
  type: string
  description: string
  enum?: (string | number)[]
  minimum?: number
  maximum?: number
  default?: unknown
}

export interface ToolFunctionDefinition {
  name: string
  description: string
  parameters: {
    type: 'object'
    properties: Record<string, ToolParameterProperty>
    required: string[]
  }
}

export interface AgentTool {
  type: 'function'
  function: ToolFunctionDefinition
}

// ─── Tool → Module mapping ──────────────────────────────────────────────────

export interface ToolModuleMapping {
  toolName: string
  moduleId: ModuleId
  displayLabel: string
}

export const TOOL_MODULE_MAP: ToolModuleMapping[] = [
  { toolName: 'run_causal_inference', moduleId: 'causal-did', displayLabel: 'Causal Inference Engine' },
  { toolName: 'run_forecasting', moduleId: 'forecasting', displayLabel: 'Forecasting & Counterfactual Predictor' },
  { toolName: 'run_learnings_repository', moduleId: 'learnings-repository', displayLabel: 'Learnings & Meta-Analysis Repository' },
  { toolName: 'run_roi_synthesis', moduleId: 'roi-synthesis', displayLabel: 'ROI Synthesis (P&L Money Waterfall)' },
  { toolName: 'run_simpsons_paradox', moduleId: 'simpsons-paradox', displayLabel: "Simpson's Paradox & Heterogeneity Checker" },
]

export function getModuleForTool(toolName: string): ToolModuleMapping | undefined {
  return TOOL_MODULE_MAP.find((m) => m.toolName === toolName)
}

// ─── Tool definitions (OpenAI function-calling schema) ──────────────────────

export const AGENT_TOOLS: AgentTool[] = [
  {
    type: 'function',
    function: {
      name: 'run_causal_inference',
      description:
        'Run the Causal Inference Engine (Difference-in-Differences) module to estimate the true incremental store lift. ' +
        'Use when the user asks about treatment effects, causal impact, net lift, DiD, SDID, attribution, or isolating impact.',
      parameters: {
        type: 'object',
        properties: {
          estimator: {
            type: 'string',
            description: 'The causal estimator methodology to use.',
            enum: ['sdid', 'staggered_did', 'dml', 'its', 'causal_forests'],
            default: 'sdid',
          },
          pre_period_weeks: {
            type: 'number',
            description: 'Number of pre-treatment weeks for the parallel trends estimation.',
            minimum: 4,
            maximum: 52,
            default: 12,
          },
          post_period_weeks: {
            type: 'number',
            description: 'Number of post-treatment weeks to measure.',
            minimum: 1,
            maximum: 52,
            default: 8,
          },
          confidence_level: {
            type: 'number',
            description: 'Statistical confidence level (0-1).',
            minimum: 0.8,
            maximum: 0.99,
            default: 0.95,
          },
          confounder_adjustment: {
            type: 'string',
            description: 'How to handle confounders in the model.',
            enum: ['none', 'weather', 'stockouts', 'full'],
            default: 'full',
          },
        },
        required: [],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'run_forecasting',
      description:
        'Run the Forecasting & Counterfactual Predictor module to generate counterfactual projections and future lift estimates. ' +
        'Use when the user asks about forecasts, predictions, projections, what-if scenarios, counterfactuals, or future lift/sales/impact.',
      parameters: {
        type: 'object',
        properties: {
          weeks_of_flight: {
            type: 'number',
            description: 'Observed flight window in weeks (how long the experiment has been running).',
            minimum: 1,
            maximum: 52,
            default: 8,
          },
          horizon_weeks: {
            type: 'number',
            description: 'Future projection horizon in weeks.',
            enum: [4, 8, 12, 26, 52],
            default: 12,
          },
          model: {
            type: 'string',
            description: 'Forecasting model to use for counterfactual prediction.',
            enum: ['arima', 'ets', 'prophet', 'lightgbm', 'xgboost', 'random_forest', 'var', 'dynamic_regression'],
            default: 'prophet',
          },
          include_confidence_band: {
            type: 'string',
            description: 'Whether to include prediction confidence intervals.',
            enum: ['true', 'false'],
            default: 'true',
          },
        },
        required: [],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'run_learnings_repository',
      description:
        'Query the Learnings & Meta-Analysis Repository to retrieve historical experiment results, prior knowledge, and meta-analyses. ' +
        'Use when the user asks about past experiments, historical results, what we learned before, meta-analysis, or institutional knowledge.',
      parameters: {
        type: 'object',
        properties: {
          query_type: {
            type: 'string',
            description: 'Type of learning to search for.',
            enum: ['similar_experiments', 'category_summary', 'effect_sizes', 'best_practices'],
            default: 'similar_experiments',
          },
          category_filter: {
            type: 'string',
            description: 'Filter learnings by initiative category.',
            enum: ['all', 'pricing', 'assortment', 'staffing', 'remodel', 'marketing'],
            default: 'all',
          },
          max_results: {
            type: 'number',
            description: 'Maximum number of prior learnings to return.',
            minimum: 1,
            maximum: 20,
            default: 5,
          },
        },
        required: [],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'run_roi_synthesis',
      description:
        'Run ROI Synthesis (P&L Money Waterfall) to translate causal lift into a full financial breakdown including halo effects, cannibalization, and net incremental margin. ' +
        'Use when the user asks about ROI, return on investment, P&L, margin, cost-benefit, payback period, or financial impact.',
      parameters: {
        type: 'object',
        properties: {
          include_halo_effects: {
            type: 'string',
            description: 'Whether to include halo/spillover effects in the P&L.',
            enum: ['true', 'false'],
            default: 'true',
          },
          include_cannibalization: {
            type: 'string',
            description: 'Whether to subtract cannibalization from adjacent categories.',
            enum: ['true', 'false'],
            default: 'true',
          },
          time_horizon_months: {
            type: 'number',
            description: 'Months over which to project ROI.',
            minimum: 1,
            maximum: 36,
            default: 12,
          },
          cost_basis: {
            type: 'string',
            description: 'How to calculate implementation costs.',
            enum: ['per_store', 'total_fleet', 'marginal'],
            default: 'per_store',
          },
        },
        required: [],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'run_simpsons_paradox',
      description:
        "Run Simpson's Paradox & Heterogeneity Checker to identify whether aggregate results mask opposing effects across store segments. " +
        'Use when the user asks about heterogeneity, subgroup effects, paradox, segment-level differences, or HTE (heterogeneous treatment effects).',
      parameters: {
        type: 'object',
        properties: {
          segmentation_dims: {
            type: 'string',
            description: 'Dimensions to segment stores by for heterogeneity analysis.',
            enum: ['region', 'format_type', 'risk_tier', 'store_size', 'all'],
            default: 'all',
          },
          min_segment_size: {
            type: 'number',
            description: 'Minimum number of stores in a segment to analyze.',
            minimum: 10,
            maximum: 500,
            default: 50,
          },
          significance_threshold: {
            type: 'number',
            description: 'P-value threshold for reporting significant heterogeneity.',
            minimum: 0.01,
            maximum: 0.1,
            default: 0.05,
          },
        },
        required: [],
      },
    },
  },
]

// ─── Build human-readable summary of tool call ──────────────────────────────

export function buildToolCallSummary(toolName: string, args: Record<string, unknown>): string {
  const mapping = getModuleForTool(toolName)
  if (!mapping) return `Executing unknown tool: ${toolName}`

  const paramParts: string[] = []
  for (const [key, value] of Object.entries(args)) {
    if (value === undefined || value === null) continue
    const label = key.replace(/_/g, ' ')
    paramParts.push(`${label}: ${value}`)
  }

  const paramStr = paramParts.length > 0 ? ` (${paramParts.join(', ')})` : ''
  return `Analyzing request… running **${mapping.displayLabel}**${paramStr}`
}

// ─── Convert tool args to module form params ────────────────────────────────

export function toolArgsToModuleParams(
  toolName: string,
  args: Record<string, unknown>,
): Record<string, unknown> {
  switch (toolName) {
    case 'run_causal_inference':
      return {
        estimator: args.estimator ?? 'sdid',
        prePeriodWeeks: args.pre_period_weeks ?? 12,
        postPeriodWeeks: args.post_period_weeks ?? 8,
        confidenceLevel: args.confidence_level ?? 0.95,
        confounderAdjustment: args.confounder_adjustment ?? 'full',
      }
    case 'run_forecasting':
      return {
        weeksOfFlight: args.weeks_of_flight ?? 8,
        horizonWeeks: args.horizon_weeks ?? 12,
        model: args.model ?? 'prophet',
        includeConfidenceBand: args.include_confidence_band !== 'false',
      }
    case 'run_learnings_repository':
      return {
        queryType: args.query_type ?? 'similar_experiments',
        categoryFilter: args.category_filter ?? 'all',
        maxResults: args.max_results ?? 5,
      }
    case 'run_roi_synthesis':
      return {
        includeHaloEffects: args.include_halo_effects !== 'false',
        includeCannibalization: args.include_cannibalization !== 'false',
        timeHorizonMonths: args.time_horizon_months ?? 12,
        costBasis: args.cost_basis ?? 'per_store',
      }
    case 'run_simpsons_paradox':
      return {
        segmentationDims: args.segmentation_dims ?? 'all',
        minSegmentSize: args.min_segment_size ?? 50,
        significanceThreshold: args.significance_threshold ?? 0.05,
      }
    default:
      return args
  }
}
