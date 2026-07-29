import { useState } from 'react'
import { Settings, Database, Cpu, Key, Check, Info } from 'lucide-react'
import { AppIcon } from '../shared/AppIcon'

export function SettingsView() {
  const [dbUri, setDbUri] = useState('duckdb:///continum_warehouse.db')
  const [statSigKey, setStatSigKey] = useState('secret-statsig-live-pulse-********')
  const [llmProvider, setLlmProvider] = useState<'gemini' | 'azure_openai'>('gemini')
  const [cacheExpiry, setCacheExpiry] = useState('10 minutes')
  const [saveSuccess, setSaveSuccess] = useState(false)

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault()
    setSaveSuccess(true)
    setTimeout(() => setSaveSuccess(false), 3000)
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-surface-base">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between gap-4 border-b border-border-muted/12 px-6 py-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <AppIcon icon={Settings} size="sm" className="text-border-muted" />
            <h2 className="type-title">Settings</h2>
          </div>
          <p className="type-subtitle mt-0.5">
            Configure MatchView platform environments, analytical integrations, and LLM providers.
          </p>
        </div>
      </div>

      {/* Main Form Area */}
      <div className="flex-1 overflow-y-auto p-6 max-w-4xl">
        <form onSubmit={handleSave} className="space-y-6">
          {/* Section 1: Database & Telemetry */}
          <section className="glass-panel rounded-[8px] border border-border-muted/12 bg-surface-raised/40 p-5 space-y-4">
            <div className="flex items-center gap-2 border-b border-border-muted/10 pb-2">
              <AppIcon icon={Database} size="xs" className="text-border-muted" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-text-primary">
                Analytical Database & Cache
              </h3>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="db_uri" className="block text-xs font-semibold text-text-secondary mb-1">
                  Local Database Connection URI
                </label>
                <input
                  id="db_uri"
                  type="text"
                  value={dbUri}
                  onChange={(e) => setDbUri(e.target.value)}
                  className="focus-ring w-full rounded-xs border border-border-muted/20 bg-surface-base px-3 py-2 text-xs text-text-primary font-mono"
                />
                <p className="mt-1 text-[10px] text-text-secondary">
                  DuckDB or conformed CSV database engine path.
                </p>
              </div>

              <div>
                <label htmlFor="cache_expiry" className="block text-xs font-semibold text-text-secondary mb-1">
                  Schema Metadata Cache Lifetime
                </label>
                <select
                  id="cache_expiry"
                  value={cacheExpiry}
                  onChange={(e) => setCacheExpiry(e.target.value)}
                  className="focus-ring w-full rounded-xs border border-border-muted/20 bg-surface-base px-3 py-2 text-xs text-text-primary"
                >
                  <option value="5 minutes">5 minutes</option>
                  <option value="10 minutes">10 minutes</option>
                  <option value="1 hour">1 hour</option>
                  <option value="No cache">No cache (Fetch live)</option>
                </select>
                <p className="mt-1 text-[10px] text-text-secondary">
                  Prevents unnecessary re-scanning of DuckDB/Snowflake schema.
                </p>
              </div>
            </div>
          </section>

          {/* Section 2: LLM Agent Model Configuration */}
          <section className="glass-panel rounded-[8px] border border-border-muted/12 bg-surface-raised/40 p-5 space-y-4">
            <div className="flex items-center gap-2 border-b border-border-muted/10 pb-2">
              <AppIcon icon={Cpu} size="xs" className="text-border-muted" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-text-primary">
                Copilot AI LLM Configuration
              </h3>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-text-secondary mb-1">
                  Primary LLM Provider
                </label>
                <div className="flex items-center gap-4">
                  <label className="flex items-center gap-2 text-xs text-text-primary cursor-pointer">
                    <input
                      type="radio"
                      name="llm_provider"
                      value="gemini"
                      checked={llmProvider === 'gemini'}
                      onChange={() => setLlmProvider('gemini')}
                      className="accent-border-muted"
                    />
                    Gemini (GEMINI_API_KEY)
                  </label>
                  <label className="flex items-center gap-2 text-xs text-text-primary cursor-pointer">
                    <input
                      type="radio"
                      name="llm_provider"
                      value="azure_openai"
                      checked={llmProvider === 'azure_openai'}
                      onChange={() => setLlmProvider('azure_openai')}
                      className="accent-border-muted"
                    />
                    Azure OpenAI Fallback
                  </label>
                </div>
              </div>

              <div className="bg-surface-base/50 border border-border-muted/10 rounded-[6px] p-3 flex items-start gap-2.5">
                <AppIcon icon={Info} size="xs" className="text-border-muted mt-0.5 shrink-0" />
                <p className="text-[11px] text-text-secondary leading-relaxed">
                  The LLM setup strictly follows settings declared in <code className="font-mono bg-surface-hover px-1 rounded">continum/__init__.py</code>.
                  It prioritizes Google Gemini, failing back to Azure OpenAI if Gemini keys are missing, and raising a RuntimeError if neither is found.
                </p>
              </div>
            </div>
          </section>

          {/* Section 3: SaaS integrations */}
          <section className="glass-panel rounded-[8px] border border-border-muted/12 bg-surface-raised/40 p-5 space-y-4">
            <div className="flex items-center gap-2 border-b border-border-muted/10 pb-2">
              <AppIcon icon={Key} size="xs" className="text-border-muted" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-text-primary">
                SaaS Integrations & Telemetry
              </h3>
            </div>

            <div>
              <label htmlFor="statsig_key" className="block text-xs font-semibold text-text-secondary mb-1">
                StatSig Secret Console API Key
              </label>
              <input
                id="statsig_key"
                type="password"
                value={statSigKey}
                onChange={(e) => setStatSigKey(e.target.value)}
                className="focus-ring w-full rounded-xs border border-border-muted/20 bg-surface-base px-3 py-2 text-xs text-text-primary font-mono"
              />
              <p className="mt-1 text-[10px] text-text-secondary">
                For fetching live exposure telemetry and pulse health in real-time.
              </p>
            </div>
          </section>

          {/* Submit/Save button */}
          <div className="flex items-center gap-3 pt-2">
            <button
              type="submit"
              className="focus-ring rounded-xs bg-border-muted px-4 py-2 text-xs font-medium text-white shadow-glow transition-opacity hover:opacity-95"
            >
              Save Configuration
            </button>

            {saveSuccess && (
              <div className="flex items-center gap-1.5 text-xs text-emerald-600 font-semibold animate-fade-in">
                <AppIcon icon={Check} size="xs" />
                Settings updated successfully!
              </div>
            )}
          </div>
        </form>
      </div>
    </div>
  )
}
