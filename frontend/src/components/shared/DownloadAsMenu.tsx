import { ChevronDown, Download } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'
import {
  downloadReportFile,
  REPORT_DOWNLOAD_OPTIONS,
  type ReportDownloadFormat,
} from '../../data/reportDownload'
import { AppIcon } from '../shared/AppIcon'

interface DownloadAsMenuProps {
  filename: string
  markdown: string
  className?: string
}

export function DownloadAsMenu({ filename, markdown, className = '' }: DownloadAsMenuProps) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const menuId = useId()

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

  const handleSelect = (format: ReportDownloadFormat) => {
    downloadReportFile(filename, markdown, format)
    setOpen(false)
  }

  return (
    <div ref={rootRef} className={`relative inline-flex ${className}`}>
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((v) => !v)}
        className="focus-ring inline-flex items-center gap-1.5 rounded-[8px] border border-border-muted/30 bg-surface-raised px-2.5 py-1 text-xs font-medium text-text-primary transition-colors hover:border-border-muted hover:bg-surface-hover"
      >
        <AppIcon icon={Download} size="xs" />
        Download as
        <AppIcon
          icon={ChevronDown}
          size="xs"
          className={`text-text-secondary transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {open ? (
        <ul
          id={menuId}
          role="menu"
          className="absolute bottom-full left-0 z-30 mb-1 min-w-[7.5rem] overflow-hidden rounded-[8px] border border-border-muted/20 bg-surface-raised py-1 shadow-[0_8px_24px_rgba(15,23,42,0.12)]"
        >
          {REPORT_DOWNLOAD_OPTIONS.map((opt) => (
            <li key={opt.format} role="none">
              <button
                type="button"
                role="menuitem"
                onClick={() => handleSelect(opt.format)}
                className="focus-ring flex w-full px-3 py-1.5 text-left text-xs font-medium text-text-primary transition-colors hover:bg-surface-hover"
              >
                {opt.label}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
