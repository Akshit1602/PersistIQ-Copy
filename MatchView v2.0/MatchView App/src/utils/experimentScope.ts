import type { ModuleId } from '../context/types'

export function experimentModuleKey(experiment: string, moduleId: ModuleId): string {
  return `${experiment}::${moduleId}`
}
