import { useEffect, useRef, useState } from 'react'
import { ChevronDown, ChevronRight, Wand2 } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { useConversationalLoop } from '../../context/ConversationalLoopContext'
import type { ModuleId, Phase } from '../../context/types'
import {
  buildAnalystPhaseOptions,
  EXECUTIVE_PHASES,
  isModuleId,
  PHASE_LABELS,
  type PhaseOption,
} from '../../data/moduleRegistry'
import { AppIcon } from '../shared/AppIcon'

export function PhaseDropdown() {
  const { currentPersona, activePhase, activeModuleId, setActivePhase } = useMatchView()
  const { activeModuleContext, activateModuleContext } = useConversationalLoop()
  const [open, setOpen] = useState(false)
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const phases =
    currentPersona === 'executive' ? EXECUTIVE_PHASES : buildAnalystPhaseOptions()

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
        setExpandedGroup(null)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const selectPhase = (phase: Phase) => {
    if (isModuleId(phase) && currentPersona === 'analyst') {
      activateModuleContext(phase as ModuleId)
    } else {
      setActivePhase(phase)
    }
    setOpen(false)
    setExpandedGroup(null)
  }

  const displayLabel =
    activeModuleContext?.label ??
    (activeModuleId && PHASE_LABELS[activeModuleId]
      ? PHASE_LABELS[activeModuleId]
      : activePhase === 'auto'
        ? 'Auto-Detect'
        : PHASE_LABELS[activePhase] ?? activePhase)

  const renderOption = (option: PhaseOption, depth = 0) => {
    if (option.children && currentPersona === 'analyst') {
      const isExpanded = expandedGroup === option.value
      return (
        <div key={option.value}>
          <button
            type="button"
            onClick={() => setExpandedGroup(isExpanded ? null : option.value)}
            className="focus-ring flex w-full items-center justify-between px-2.5 py-1.5 text-left text-xs text-text-primary transition-colors hover:bg-surface-hover"
            style={{ paddingLeft: `${12 + depth * 12}px` }}
          >
            <span>{option.label}</span>
            <AppIcon
              icon={isExpanded ? ChevronDown : ChevronRight}
              size="xs"
              className="text-text-secondary"
            />
          </button>
          {isExpanded &&
            option.children.map((child) => (
              <button
                key={child.value}
                type="button"
                onClick={() => selectPhase(child.value)}
                className={`focus-ring flex w-full items-center px-2.5 py-1.5 text-left text-xs transition-colors hover:bg-surface-hover ${
                  activePhase === child.value ||
                  activeModuleId === child.value ||
                  activeModuleContext?.moduleId === child.value
                    ? 'text-border-muted'
                    : 'text-text-secondary'
                }`}
                style={{ paddingLeft: `${24 + depth * 12}px` }}
              >
                {child.label}
              </button>
            ))}
        </div>
      )
    }

    return (
      <button
        key={option.value}
        type="button"
        onClick={() => selectPhase(option.value)}
        className={`focus-ring flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-xs transition-colors hover:bg-surface-hover ${
          activePhase === option.value ? 'text-border-muted' : 'text-text-primary'
        }`}
        style={{ paddingLeft: `${12 + depth * 12}px` }}
      >
        {option.value === 'auto' && <AppIcon icon={Wand2} size="xs" />}
        <span>{option.label}</span>
      </button>
    )
  }

  return (
    <div ref={containerRef} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="focus-ring flex items-center gap-1 rounded-xs border border-border-muted/30 bg-surface-base px-2 py-1 text-xs font-medium text-text-primary transition-colors duration-instant hover:border-border-muted"
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        {(activePhase === 'auto' && !activeModuleId && !activeModuleContext) && (
          <AppIcon icon={Wand2} size="xs" className="text-border-muted" />
        )}
        <span className="max-w-[140px] truncate">{displayLabel}</span>
        <AppIcon icon={ChevronDown} size="xs" className="text-text-secondary" />
      </button>

      {open && (
        <div
          className="absolute bottom-full left-0 z-50 mb-2 max-h-64 min-w-[260px] overflow-y-auto rounded-xs border border-border-muted/30 glass-panel py-1 shadow-glow"
          role="listbox"
        >
          {phases.map((option) => renderOption(option))}
        </div>
      )}
    </div>
  )
}
