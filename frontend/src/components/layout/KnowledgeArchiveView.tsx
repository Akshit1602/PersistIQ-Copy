import { useEffect, useMemo, useState } from 'react'
import { X, BookOpen, FileText, ClipboardList, Search, Database, Table, BarChart2 } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { AppIcon } from '../shared/AppIcon'
import { fetchLoadedDatasets, type LoadedDataset } from '../../services/api'
import {
  GLOSSARY_TERMS,
  GLOSSARY_CATEGORIES,
  MANUAL_SECTIONS,
  SOP_ENTRIES,
} from '../../data/storeKnowledgeArchive'

type ArchiveTab = 'datasets' | 'manual' | 'sop' | 'glossary'

const inputClass =
  'focus-ring box-border w-full min-w-0 rounded-xs border border-border-muted/25 bg-surface-base px-2.5 py-1.5 text-xs text-text-primary placeholder:text-text-secondary'
const selectClass = `${inputClass} appearance-none bg-[length:12px_12px] bg-[right_0.65rem_center] bg-no-repeat pr-8`
const selectChevronBg =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%2364748b' stroke-width='2.25' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E\")"

export function KnowledgeArchiveView() {
  const { knowledgeArchiveOpen, closeKnowledgeArchive } = useMatchView()
  const [tab, setTab] = useState<ArchiveTab>('datasets')
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState<'all' | (typeof GLOSSARY_CATEGORIES)[number]>('all')

  const [datasets, setDatasets] = useState<LoadedDataset[]>([])
  const [selectedTable, setSelectedTable] = useState<string>('')
  const [loadingDatasets, setLoadingDatasets] = useState<boolean>(false)
  const [datasetError, setDatasetError] = useState<string | null>(null)

  useEffect(() => {
    if (knowledgeArchiveOpen && tab === 'datasets') {
      setLoadingDatasets(true)
      setDatasetError(null)
      fetchLoadedDatasets()
        .then((res) => {
          setDatasets(res.datasets)
          if (res.datasets.length > 0 && !selectedTable) {
            setSelectedTable(res.datasets[0].table_name)
          }
        })
        .catch((err) => setDatasetError(err.message))
        .finally(() => setLoadingDatasets(false))
    }
  }, [knowledgeArchiveOpen, tab])

  const currentDataset = useMemo(() => {
    return datasets.find((d) => d.table_name === selectedTable) || datasets[0]
  }, [datasets, selectedTable])

  const filteredTerms = useMemo(() => {
    const q = query.trim().toLowerCase()
    return GLOSSARY_TERMS.filter((t) => {
      const matchesCategory = category === 'all' || t.category === category
      const matchesQuery = !q || t.term.toLowerCase().includes(q) || t.definition.toLowerCase().includes(q)
      return matchesCategory && matchesQuery
    })
  }, [query, category])

  if (!knowledgeArchiveOpen) return null

  return (
    <div className="flex min-h-0 flex-1 overflow-hidden bg-surface-raised">
      <div className="mx-auto flex h-full w-full max-w-5xl flex-col">
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-border-muted/20 px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold text-text-primary">Knowledge Archive</h2>
            <p className="mt-0.5 text-xs text-text-secondary">Explore dataset snippets, operational manuals, SOPs, and experimentation glossary.</p>
          </div>
          <button
            type="button"
            onClick={closeKnowledgeArchive}
            className="focus-ring flex h-8 w-8 shrink-0 items-center justify-center rounded-xs text-text-secondary hover:bg-surface-hover hover:text-text-primary"
            aria-label="Close"
          >
            <AppIcon icon={X} size="sm" />
          </button>
        </header>

        <div className="flex shrink-0 gap-1 border-b border-border-muted/15 px-6 pt-3">
          {(
            [
              { id: 'datasets' as ArchiveTab, label: 'Loaded Datasets', icon: Database },
              { id: 'manual' as ArchiveTab, label: 'Manual', icon: BookOpen },
              { id: 'sop' as ArchiveTab, label: 'SOP', icon: ClipboardList },
              { id: 'glossary' as ArchiveTab, label: 'Glossary', icon: FileText },
            ]
          ).map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`focus-ring flex items-center gap-1.5 rounded-t-xs px-3 py-2 text-xs font-medium transition-colors ${
                tab === t.id
                  ? 'border-b-2 border-border-muted text-text-primary'
                  : 'text-text-secondary hover:text-text-primary'
              }`}
            >
              <AppIcon icon={t.icon} size="xs" />
              {t.label}
            </button>
          ))}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
          {tab === 'datasets' && (
            <div className="flex flex-col gap-4">
              {loadingDatasets ? (
                <div className="flex h-48 items-center justify-center text-xs text-text-secondary">
                  Loading dataset statistics and row samples...
                </div>
              ) : datasetError ? (
                <div className="rounded-xs bg-red-500/10 p-4 text-xs text-red-400">
                  Failed to load dataset statistics: {datasetError}
                </div>
              ) : (
                <div className="flex flex-col gap-4">
                  <div className="flex flex-wrap gap-2 border-b border-border-muted/15 pb-3">
                    {datasets.map((d) => (
                      <button
                        key={d.table_name}
                        type="button"
                        onClick={() => setSelectedTable(d.table_name)}
                        className={`flex items-center gap-1.5 rounded-xs px-2.5 py-1 text-xs font-mono transition-colors ${
                          selectedTable === d.table_name
                            ? 'bg-blue-600 text-white'
                            : 'bg-surface-base text-text-secondary hover:bg-surface-hover hover:text-text-primary'
                        }`}
                      >
                        <AppIcon icon={Table} size="xs" />
                        {d.table_name}
                      </button>
                    ))}
                  </div>

                  {currentDataset && (
                    <div className="flex flex-col gap-4">
                      <div className="grid grid-cols-3 gap-3">
                        <div className="rounded-xs border border-border-muted/20 bg-surface-base/50 p-3">
                          <p className="text-micro font-medium uppercase tracking-wider text-text-secondary">Selected Table</p>
                          <p className="mt-1 text-sm font-semibold font-mono text-text-primary">{currentDataset.table_name}</p>
                        </div>
                        <div className="rounded-xs border border-border-muted/20 bg-surface-base/50 p-3">
                          <p className="text-micro font-medium uppercase tracking-wider text-text-secondary">Total Rows</p>
                          <p className="mt-1 text-sm font-semibold text-text-primary">{currentDataset.total_rows.toLocaleString()}</p>
                        </div>
                        <div className="rounded-xs border border-border-muted/20 bg-surface-base/50 p-3">
                          <p className="text-micro font-medium uppercase tracking-wider text-text-secondary">Columns Count</p>
                          <p className="mt-1 text-sm font-semibold text-text-primary">{currentDataset.column_count}</p>
                        </div>
                      </div>

                      <div className="rounded-xs border border-border-muted/20 bg-surface-base/40 p-3">
                        <div className="flex items-center gap-2 mb-2">
                          <AppIcon icon={BarChart2} size="xs" className="text-text-secondary" />
                          <p className="text-xs font-semibold text-text-primary">Column Schema & Summary Statistics</p>
                        </div>
                        <div className="overflow-x-auto">
                          <table className="w-full text-left text-xs border-collapse">
                            <thead>
                              <tr className="border-b border-border-muted/20 text-text-secondary">
                                <th className="py-1.5 px-2 font-mono">Column</th>
                                <th className="py-1.5 px-2 font-mono">Type</th>
                                <th className="py-1.5 px-2">Nulls</th>
                                <th className="py-1.5 px-2">Unique</th>
                                <th className="py-1.5 px-2">Min / Max / Avg</th>
                              </tr>
                            </thead>
                            <tbody>
                              {currentDataset.columns.map((col) => (
                                <tr key={col.name} className="border-b border-border-muted/10 hover:bg-surface-hover/50">
                                  <td className="py-1.5 px-2 font-mono text-text-primary font-medium">{col.name}</td>
                                  <td className="py-1.5 px-2 font-mono text-text-secondary text-micro">{col.type}</td>
                                  <td className="py-1.5 px-2 text-text-secondary">{col.null_count}</td>
                                  <td className="py-1.5 px-2 text-text-secondary">{col.unique_count}</td>
                                  <td className="py-1.5 px-2 text-text-secondary font-mono text-micro">
                                    {col.min !== undefined ? 'Min: ' + col.min + ' | Max: ' + col.max + ' | Avg: ' + col.avg : '-'}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>

                      <div className="rounded-xs border border-border-muted/20 bg-surface-base/40 p-3">
                        <p className="text-xs font-semibold text-text-primary mb-2">Dataset Sample Rows (Top 15)</p>
                        <div className="overflow-x-auto max-h-80 overflow-y-auto">
                          <table className="w-full text-left text-micro border-collapse whitespace-nowrap">
                            <thead>
                              <tr className="border-b border-border-muted/20 bg-surface-base text-text-secondary font-mono">
                                {currentDataset.columns.map((col) => (
                                  <th key={col.name} className="py-1.5 px-2">{col.name}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {currentDataset.sample_data.map((row, idx) => (
                                <tr key={idx} className="border-b border-border-muted/10 hover:bg-surface-hover/50">
                                  {currentDataset.columns.map((col) => (
                                    <td key={col.name} className="py-1.5 px-2 text-text-primary font-mono">
                                      {row[col.name] !== undefined && row[col.name] !== null ? String(row[col.name]) : <span className="text-text-secondary italic">null</span>}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {tab === 'manual' && (
            <div className="flex flex-col gap-3">
              {MANUAL_SECTIONS.map((s) => (
                <div key={s.title} className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-3">
                  <p className="text-sm font-semibold text-text-primary">{s.title}</p>
                  <p className="mt-1 text-xs text-text-secondary leading-relaxed">{s.content}</p>
                </div>
              ))}
            </div>
          )}

          {tab === 'sop' && (
            <div className="flex flex-col gap-3">
              {SOP_ENTRIES.map((sop) => (
                <div key={sop.title} className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-3">
                  <p className="text-sm font-semibold text-text-primary">{sop.title}</p>
                  <ol className="mt-2 list-decimal space-y-1 pl-4">
                    {sop.steps.map((step, i) => (
                      <li key={i} className="text-xs text-text-secondary leading-relaxed">{step}</li>
                    ))}
                  </ol>
                </div>
              ))}
            </div>
          )}

          {tab === 'glossary' && (
            <div className="flex flex-col gap-3">
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <AppIcon icon={Search} size="xs" className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-text-secondary" />
                  <input
                    className={`${inputClass} pl-7`}
                    placeholder="Search terms…"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                </div>
                <select
                  className={`${selectClass} w-48`}
                  style={{ backgroundImage: selectChevronBg }}
                  value={category}
                  onChange={(e) => setCategory(e.target.value as typeof category)}
                >
                  <option value="all">All categories</option>
                  {GLOSSARY_CATEGORIES.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>

              <div className="flex flex-col gap-2">
                {filteredTerms.map((t) => (
                  <div key={t.term} className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-3">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-semibold text-text-primary">{t.term}</p>
                      <span className="rounded-xs bg-surface-hover px-1.5 py-0.5 text-micro text-text-secondary">{t.category}</span>
                    </div>
                    <p className="mt-1 text-xs text-text-secondary leading-relaxed">{t.definition}</p>
                  </div>
                ))}
                {filteredTerms.length === 0 && (
                  <p className="px-1 text-xs text-text-secondary">No terms match your search.</p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
