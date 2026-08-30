import { useEffect, useRef } from 'react'
import { useMatchView } from '../../context/MatchViewContext'
import {
  getMessageKind,
  isBriefHandoffMessage,
  isModuleConfigMessage,
  isModuleRunMessage,
} from '../../context/types'
import noMessageImg from '../../assets/NoMessage.png'
import { InteractiveEvaluationCard } from './InteractiveEvaluationCard'
import { BriefHandoffCard } from './BriefHandoffCard'
import { ArtifactCardList } from './ArtifactCard'
import { ChatRichText } from './ChatRichText'
import type { ModuleConfigChatMessage } from '../../context/types'
import { MODULE_BY_ID } from '../../data/moduleRegistry'
import { AppIcon } from '../shared/AppIcon'
import { PanelRight } from 'lucide-react'

function LegacyLabSyncNotice({ message }: { message: ModuleConfigChatMessage }) {
  const mod = MODULE_BY_ID[message.moduleId]

  return (
    <div className="glass-panel max-w-[75%] rounded-sm px-3 py-2">
      <div className="flex items-center gap-1.5">
        <AppIcon icon={PanelRight} size="xs" className="text-border-muted" />
        <span className="text-xs font-medium text-text-primary">
          Configuration synced to Analytics Lab — {mod.label}
        </span>
      </div>
      <div className="mt-1">
        <ChatRichText content={message.content} className="text-xs text-text-secondary" />
      </div>
      <time className="mt-1.5 block text-micro text-text-secondary">{message.timestamp}</time>
    </div>
  )
}

export function ChatStream() {
  const {
    messagesByThread,
    activeThreadId,
    highlightedMessageId,
    threadGroups,
    selectThread,
  } = useMatchView()
  const messages = messagesByThread[activeThreadId] ?? []
  const bottomRef = useRef<HTMLDivElement>(null)
  const hasRunning = messages.some(
    (m) => isModuleRunMessage(m) && m.status === 'running',
  )

  const openExperiment = (name: string) => {
    const group = threadGroups.find((g) => g.experiment === name)
    const thread = group?.threads[0]
    if (thread) selectThread(thread.id, name)
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: hasRunning ? 'smooth' : 'auto' })
  }, [messages, hasRunning])

  useEffect(() => {
    if (!highlightedMessageId) return
    const el = document.getElementById(`chat-msg-${highlightedMessageId}`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [highlightedMessageId])

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center px-6 py-12 text-center">
        <img
          src={noMessageImg}
          alt=""
          className="mb-6 w-full max-w-[280px] object-contain"
          aria-hidden="true"
        />
        <p className="text-sm font-semibold text-text-primary">No messages yet</p>
        <p className="mt-1.5 max-w-sm text-xs leading-relaxed text-text-secondary">
          Open Initiative Setup & Benchmarking from the sidebar to set up a digital experiment, then Get
          Started to begin chat with your brief.
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-1 flex-col gap-3 overflow-y-auto px-5 py-3">
      {messages.map((msg) => {
        const kind = getMessageKind(msg)
        const isHighlighted = msg.id === highlightedMessageId
        const alignment = msg.role === 'user' ? 'justify-end' : 'justify-start'

        if (kind === 'module-run' && isModuleRunMessage(msg)) {
          return (
            <div
              key={msg.id}
              id={`chat-msg-${msg.id}`}
              className={`flex ${alignment} ${isHighlighted ? 'rounded-sm ring-2 ring-border-muted/40' : ''}`}
            >
              <InteractiveEvaluationCard message={msg} />
            </div>
          )
        }

        if (kind === 'brief-handoff' && isBriefHandoffMessage(msg)) {
          return (
            <div
              key={msg.id}
              id={`chat-msg-${msg.id}`}
              className={`flex ${alignment} ${isHighlighted ? 'rounded-sm ring-2 ring-border-muted/40' : ''}`}
            >
              <BriefHandoffCard message={msg} />
            </div>
          )
        }

        if (kind === 'module-config' && isModuleConfigMessage(msg)) {
          return (
            <div
              key={msg.id}
              id={`chat-msg-${msg.id}`}
              className={`flex ${alignment}`}
            >
              <LegacyLabSyncNotice message={msg} />
            </div>
          )
        }

        const isSystem = kind === 'system'
        const artifacts = msg.artifacts ?? []

        return (
          <div
            key={msg.id}
            id={`chat-msg-${msg.id}`}
            className={`flex ${alignment} ${isHighlighted ? 'rounded-sm ring-2 ring-border-muted/40' : ''}`}
          >
            <div
              className={`${
                // A chart squeezed into a 75% bubble loses its axis labels.
                artifacts.length > 0 ? 'w-[92%] max-w-[92%]' : 'max-w-[75%]'
              } rounded-sm px-3 py-2 ${
                msg.role === 'user'
                  ? 'border border-border-muted/25 bg-surface-hover'
                  : isSystem
                    ? 'border border-border-muted/15 bg-surface-raised'
                    : 'glass-panel'
              }`}
            >
              {isSystem && (
                <span className="mb-0.5 block text-micro font-semibold uppercase tracking-wider text-text-secondary">
                  System
                </span>
              )}
              <ChatRichText
                content={msg.content}
                onExperimentLink={msg.role === 'assistant' ? openExperiment : undefined}
              />
              <ArtifactCardList artifacts={artifacts} />
              <time className="mt-1 block text-micro text-text-secondary">{msg.timestamp}</time>
            </div>
          </div>
        )
      })}
      <div ref={bottomRef} aria-hidden="true" />
    </div>
  )
}
