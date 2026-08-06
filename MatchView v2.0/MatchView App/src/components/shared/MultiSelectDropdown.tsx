import { Check, ChevronDown, X } from 'lucide-react'
import { useEffect, useId, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react'
import { AppIcon } from './AppIcon'

export interface MultiSelectOption {
  id: string
  label: string
  description?: string
  disabled?: boolean
  /** Intent-based search synonyms (e.g. ["cvr", "conversion"] for
   * "Transaction Conversion Rate") — matched and ranked above plain
   * label/description substring matches. */
  keywords?: string[]
}

interface MultiSelectDropdownProps {
  options: MultiSelectOption[]
  value: string[]
  onChange: (next: string[]) => void
  placeholder?: string
  searchPlaceholder?: string
  disabled?: boolean
  className?: string
  'aria-label'?: string
}

export function MultiSelectDropdown({
  options,
  value,
  onChange,
  placeholder = 'Select…',
  searchPlaceholder = 'Search metrics…',
  disabled = false,
  className = '',
  'aria-label': ariaLabel = 'Multi select',
}: MultiSelectDropdownProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const rootRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  const listId = useId()

  const selectedSet = useMemo(() => new Set(value), [value])
  const selectedOptions = useMemo(
    () => options.filter((o) => selectedSet.has(o.id)),
    [options, selectedSet],
  )

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return options

    // Rank each option so the most relevant matches surface first — a
    // customer searching "cvr" shouldn't have to know the exact catalog
    // label to find "Transaction Conversion Rate".
    const scored = options
      .map((o) => {
        const label = o.label.toLowerCase()
        const description = o.description?.toLowerCase() ?? ''
        const keywords = o.keywords?.map((k) => k.toLowerCase()) ?? []

        let score = 0
        if (label === q) score = 100
        else if (keywords.some((k) => k === q)) score = 95
        else if (label.startsWith(q)) score = 80
        else if (keywords.some((k) => k.startsWith(q))) score = 75
        else if (keywords.some((k) => k.includes(q))) score = 60
        else if (label.includes(q)) score = 50
        else if (description.includes(q)) score = 20

        return { option: o, score }
      })
      .filter((s) => s.score > 0)

    scored.sort((a, b) => b.score - a.score)
    return scored.map((s) => s.option)
  }, [options, query])

  useEffect(() => {
    if (!open) return
    const onPointer = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  useEffect(() => {
    if (open) {
      window.setTimeout(() => searchRef.current?.focus(), 0)
    } else {
      setQuery('')
    }
  }, [open])

  const toggle = (id: string) => {
    const opt = options.find((o) => o.id === id)
    if (!opt || opt.disabled) return
    if (selectedSet.has(id)) onChange(value.filter((v) => v !== id))
    else onChange([...value, id])
  }

  const remove = (id: string, e: ReactMouseEvent) => {
    e.stopPropagation()
    onChange(value.filter((v) => v !== id))
  }

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <button
        type="button"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-label={ariaLabel}
        onClick={() => !disabled && setOpen((o) => !o)}
        className={`focus-ring flex min-h-[38px] w-full items-start gap-2 rounded-[8px] border border-border-muted/25 bg-surface-base px-2.5 py-1.5 text-left transition-colors hover:border-border-muted/40 disabled:cursor-not-allowed disabled:opacity-50 ${
          open ? 'border-border-muted/50 ring-2 ring-border-muted/20' : ''
        }`}
      >
        <div className="flex min-w-0 flex-1 flex-wrap gap-1.5">
          {selectedOptions.length === 0 ? (
            <span className="py-0.5 text-xs text-text-secondary">{placeholder}</span>
          ) : (
            selectedOptions.map((opt) => (
              <span
                key={opt.id}
                className="inline-flex max-w-full items-center gap-1 rounded-[6px] bg-border-muted/10 px-1.5 py-0.5 text-micro font-medium text-border-muted"
              >
                <span className="truncate">{opt.label}</span>
                <span
                  role="button"
                  tabIndex={-1}
                  onClick={(e) => remove(opt.id, e)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      onChange(value.filter((v) => v !== opt.id))
                    }
                  }}
                  className="inline-flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-sm text-border-muted/80 hover:bg-border-muted/15 hover:text-border-muted"
                  aria-label={`Remove ${opt.label}`}
                >
                  <AppIcon icon={X} size="xs" />
                </span>
              </span>
            ))
          )}
        </div>
        <AppIcon
          icon={ChevronDown}
          size="xs"
          className={`mt-1 shrink-0 text-text-secondary transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {open ? (
        <div
          id={listId}
          role="listbox"
          aria-multiselectable="true"
          className="absolute left-0 right-0 z-30 mt-1 overflow-hidden rounded-[8px] border border-border-muted/20 bg-surface-raised shadow-[0_10px_28px_rgba(15,23,42,0.14)]"
        >
          <div className="border-b border-border-muted/10 p-2">
            <input
              ref={searchRef}
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={searchPlaceholder}
              className="focus-ring w-full rounded-[6px] border border-border-muted/20 bg-surface-base px-2.5 py-1.5 text-xs text-text-primary placeholder:text-text-secondary"
            />
          </div>
          <ul className="max-h-52 overflow-y-auto py-1">
            {filtered.length === 0 ? (
              <li className="px-3 py-2 text-xs text-text-secondary">No metrics match</li>
            ) : (
              filtered.map((opt) => {
                const checked = selectedSet.has(opt.id)
                return (
                  <li key={opt.id} role="option" aria-selected={checked}>
                    <button
                      type="button"
                      disabled={opt.disabled}
                      onClick={() => toggle(opt.id)}
                      className={`flex w-full items-start gap-2.5 px-3 py-2 text-left transition-colors hover:bg-surface-hover disabled:cursor-not-allowed disabled:opacity-40 ${
                        checked ? 'bg-border-muted/[0.06]' : ''
                      }`}
                    >
                      <span
                        className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-[4px] border ${
                          checked
                            ? 'border-border-muted bg-border-muted text-white'
                            : 'border-border-muted/35 bg-surface-base'
                        }`}
                        aria-hidden="true"
                      >
                        {checked ? <AppIcon icon={Check} size="xs" /> : null}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-xs font-medium text-text-primary">
                          {opt.label}
                        </span>
                        {opt.description ? (
                          <span className="mt-0.5 block text-micro leading-snug text-text-secondary">
                            {opt.description}
                          </span>
                        ) : null}
                        {opt.disabled ? (
                          <span className="mt-0.5 block text-micro text-amber-700">
                            Already selected in another metric group
                          </span>
                        ) : null}
                      </span>
                    </button>
                  </li>
                )
              })
            )}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
