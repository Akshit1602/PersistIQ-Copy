import { useState } from 'react'
import { Archive, Home, Settings, type LucideIcon } from 'lucide-react'
import matchViewLogo from '../../assets/matchview_logo.svg'
import { useMatchView } from '../../context/MatchViewContext'
import { AppIcon } from '../shared/AppIcon'
import { RailUserFooter } from './RailUserFooter'

const NAV_ITEMS: { id: 'home' | 'archive' | 'settings'; icon: LucideIcon; label: string }[] = [
  { id: 'home', icon: Home, label: 'Home' },
  { id: 'archive', icon: Archive, label: 'Knowledge Archive' },
  { id: 'settings', icon: Settings, label: 'Settings' },
]

export function GlobalRail() {
  const { goHome, activeGlobalPage, setActiveGlobalPage, knowledgeArchiveOpen, openKnowledgeArchive, closeKnowledgeArchive } =
    useMatchView()
  const [hovered, setHovered] = useState(false)

  return (
    <aside
      className={`rail-panel relative inset-y-0 left-0 z-50 flex flex-col overflow-hidden border-r border-rail-border/30 transition-[width] duration-instant ease-in-out shrink-0 ${
        hovered ? 'w-60' : 'w-16'
      }`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      aria-label="Global navigation"
    >
      <div
        className={`flex py-4 ${hovered ? 'items-center px-3' : 'justify-center px-0'}`}
      >
        <div
          className={`flex h-10 shrink-0 items-center rounded-xs text-rail-text-primary ${
            hovered ? 'w-full gap-2.5 px-2' : 'w-10 justify-center px-0'
          }`}
        >
          <img
            src={matchViewLogo}
            alt=""
            className="h-7 w-auto shrink-0"
            aria-hidden="true"
          />
          {hovered ? (
            <span className="truncate text-base font-bold tracking-tight text-rail-text-primary">
              MatchView
            </span>
          ) : null}
        </div>
      </div>

      <nav className={`flex flex-1 flex-col gap-1 ${hovered ? 'px-2' : 'items-center px-0'}`}>
        {NAV_ITEMS.map((item) => {
          const isActive =
            (item.id === 'home' && activeGlobalPage === 'workspace' && !knowledgeArchiveOpen) ||
            (item.id === 'archive' && knowledgeArchiveOpen) ||
            (item.id === 'settings' && activeGlobalPage === 'settings' && !knowledgeArchiveOpen)
          return (
            <button
              key={item.id}
              type="button"
              title={!hovered ? item.label : undefined}
              onClick={() => {
                if (item.id === 'home') {
                  closeKnowledgeArchive()
                  goHome()
                } else if (item.id === 'archive') {
                  openKnowledgeArchive()
                } else {
                  closeKnowledgeArchive()
                  setActiveGlobalPage(item.id)
                }
              }}
              className={`focus-ring-rail flex items-center rounded-xs py-2.5 text-sm transition-colors duration-instant hover:bg-rail-hover hover:text-rail-text-primary ${
                isActive ? 'bg-rail-hover text-rail-text-primary' : 'text-rail-text-secondary'
              } ${hovered ? 'w-full gap-3 px-3' : 'h-10 w-10 justify-center px-0'}`}
            >
              <span className="flex h-6 w-6 shrink-0 items-center justify-center">
                <AppIcon icon={item.icon} size="sm" />
              </span>
              {hovered && <span className="truncate">{item.label}</span>}
            </button>
          )
        })}
      </nav>

      <div
        className={`mt-auto border-t border-rail-border/30 p-2 ${hovered ? '' : 'flex flex-col items-center'}`}
      >
        <RailUserFooter expanded={hovered} />
      </div>
    </aside>
  )
}
