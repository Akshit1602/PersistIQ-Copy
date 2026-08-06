import type { ReactNode } from 'react'

type Block =
  | { type: 'heading'; level: 1 | 2 | 3; text: string }
  | { type: 'paragraph'; text: string }
  | { type: 'list'; ordered: boolean; items: string[] }

function parseBlocks(content: string): Block[] {
  const lines = content.replace(/\r\n/g, '\n').split('\n')
  const blocks: Block[] = []
  let paragraph: string[] = []
  let list: { ordered: boolean; items: string[] } | null = null

  const flushParagraph = () => {
    if (paragraph.length === 0) return
    const text = paragraph.join(' ').trim()
    if (text) blocks.push({ type: 'paragraph', text })
    paragraph = []
  }

  const flushList = () => {
    if (!list || list.items.length === 0) return
    blocks.push({ type: 'list', ordered: list.ordered, items: list.items })
    list = null
  }

  for (const raw of lines) {
    const line = raw.trimEnd()
    const trimmed = line.trim()

    if (!trimmed) {
      flushParagraph()
      flushList()
      continue
    }

    const headingMatch = trimmed.match(/^(#{1,3})\s+(.+)$/)
    if (headingMatch) {
      flushParagraph()
      flushList()
      blocks.push({
        type: 'heading',
        level: headingMatch[1].length as 1 | 2 | 3,
        text: headingMatch[2].trim(),
      })
      continue
    }

    const orderedMatch = trimmed.match(/^(\d+)\.\s+(.+)$/)
    const bulletMatch = trimmed.match(/^[-*•]\s+(.+)$/)

    if (orderedMatch) {
      flushParagraph()
      if (!list || !list.ordered) {
        flushList()
        list = { ordered: true, items: [] }
      }
      list.items.push(orderedMatch[2])
      continue
    }

    if (bulletMatch) {
      flushParagraph()
      if (!list || list.ordered) {
        flushList()
        list = { ordered: false, items: [] }
      }
      list.items.push(bulletMatch[1])
      continue
    }

    flushList()
    paragraph.push(trimmed)
  }

  flushParagraph()
  flushList()
  return blocks
}

function renderMarks(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = []
  const token = /\*\*([^*]+)\*\*|\*([^*]+)\*/g
  let last = 0
  let match: RegExpExecArray | null
  let i = 0

  while ((match = token.exec(text)) !== null) {
    if (match.index > last) nodes.push(text.slice(last, match.index))
    if (match[1] != null) {
      nodes.push(
        <strong key={`${keyPrefix}-b-${i++}`} className="font-semibold text-text-primary">
          {match[1]}
        </strong>,
      )
    } else if (match[2] != null) {
      nodes.push(
        <em key={`${keyPrefix}-m-${i++}`} className="not-italic font-medium text-text-primary">
          {match[2]}
        </em>,
      )
    }
    last = match.index + match[0].length
  }

  if (last < text.length) nodes.push(text.slice(last))
  return nodes
}

function renderInline(
  text: string,
  keyPrefix: string,
  onExperimentLink?: (name: string) => void,
): ReactNode[] {
  const nodes: ReactNode[] = []
  const token = /\[([^\]]+)\]\((experiment:[^)]+|https?:\/\/[^)]+)\)/g
  let last = 0
  let match: RegExpExecArray | null
  let i = 0

  while ((match = token.exec(text)) !== null) {
    if (match.index > last) {
      nodes.push(...renderMarks(text.slice(last, match.index), `${keyPrefix}-t${i}`))
    }

    const label = match[1]
    const href = match[2]
    if (href.startsWith('experiment:')) {
      const name = href.slice('experiment:'.length)
      nodes.push(
        <button
          key={`${keyPrefix}-exp-${i++}`}
          type="button"
          onClick={() => onExperimentLink?.(name)}
          className="font-semibold text-border-muted underline decoration-border-muted/40 underline-offset-2 transition-colors hover:text-rail-hover hover:decoration-rail-hover"
        >
          {label}
        </button>,
      )
    } else {
      nodes.push(
        <a
          key={`${keyPrefix}-a-${i++}`}
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="font-semibold text-border-muted underline decoration-border-muted/40 underline-offset-2 hover:text-rail-hover"
        >
          {label}
        </a>,
      )
    }

    last = match.index + match[0].length
  }

  if (last < text.length) {
    nodes.push(...renderMarks(text.slice(last), `${keyPrefix}-end`))
  }
  return nodes
}

const HEADING_CLASS: Record<1 | 2 | 3, string> = {
  1: 'text-sm font-semibold tracking-tight text-text-primary',
  2: 'text-xs font-semibold tracking-tight text-text-primary',
  3: 'text-xs font-medium text-text-primary',
}

interface ChatRichTextProps {
  content: string
  className?: string
  onExperimentLink?: (name: string) => void
}

/** Lightweight formatter: headings, paragraphs, lists, bold, medium, links. */
export function ChatRichText({ content, className = '', onExperimentLink }: ChatRichTextProps) {
  const blocks = parseBlocks(content)

  if (blocks.length === 0) {
    return <p className={`text-xs leading-relaxed text-text-primary ${className}`} />
  }

  return (
    <div className={`space-y-2 text-xs leading-relaxed text-text-primary ${className}`}>
      {blocks.map((block, bi) => {
        if (block.type === 'heading') {
          const Tag = (`h${block.level}` as 'h1' | 'h2' | 'h3')
          return (
            <Tag key={`h-${bi}`} className={HEADING_CLASS[block.level]}>
              {renderInline(block.text, `h-${bi}`, onExperimentLink)}
            </Tag>
          )
        }

        if (block.type === 'paragraph') {
          return (
            <p key={`p-${bi}`} className="text-xs leading-relaxed text-text-primary">
              {renderInline(block.text, `p-${bi}`, onExperimentLink)}
            </p>
          )
        }

        const ListTag = block.ordered ? 'ol' : 'ul'
        return (
          <ListTag
            key={`l-${bi}`}
            className={
              block.ordered
                ? 'list-decimal space-y-1.5 pl-4 marker:font-semibold marker:text-border-muted'
                : 'list-disc space-y-1.5 pl-4 marker:text-border-muted'
            }
          >
            {block.items.map((item, ii) => (
              <li key={`li-${bi}-${ii}`} className="pl-0.5 text-xs leading-relaxed text-text-secondary">
                {renderInline(item, `li-${bi}-${ii}`, onExperimentLink)}
              </li>
            ))}
          </ListTag>
        )
      })}
    </div>
  )
}
