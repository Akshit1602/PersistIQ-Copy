import type { ModuleRunsByExperiment } from '../context/types'

export const INITIAL_MODULE_RUNS: ModuleRunsByExperiment = {
  'Walmart Banner Redesign': [
    {
      id: 'run-seed-1',
      moduleId: 'power-calculator',
      experiment: 'Walmart Banner Redesign',
      params: { baseline: 8.6, mde: 2.5, alpha: '0.05', beta: '0.20' },
      completedAt: 'Yesterday 4:32 PM',
      duration: '3.88s',
      status: 'success',
    },
    {
      id: 'run-seed-2',
      moduleId: 'data-validation',
      experiment: 'Walmart Banner Redesign',
      params: {},
      completedAt: '2 days ago',
      duration: '2.14s',
      status: 'success',
    },
  ],
  'Cart Flow Optimization': [
    {
      id: 'run-seed-3',
      moduleId: 'health-monitor',
      experiment: 'Cart Flow Optimization',
      params: {},
      completedAt: '1 week ago',
      duration: '1.12s',
      status: 'success',
    },
  ],
}
