export type ReportDownloadFormat = 'md' | 'pdf' | 'doc'

function safeBaseName(filename: string): string {
  return (
    filename
      .replace(/\.md$/i, '')
      .replace(/[^\w\-]+/g, '-')
      .replace(/^-|-$/g, '') || 'experiment-brief'
  )
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

function stripMarkdown(text: string): string {
  return text
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
}

function markdownToHtml(markdown: string): string {
  const escaped = markdown
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  return escaped
    .split(/\n\n+/)
    .map((block) => {
      const lines = block.split('\n')
      if (lines.every((l) => /^[-*•]\s+/.test(l.trim()) || !l.trim())) {
        const items = lines
          .filter((l) => l.trim())
          .map((l) => `<li>${inlineHtml(l.replace(/^[-*•]\s+/, ''))}</li>`)
          .join('')
        return `<ul>${items}</ul>`
      }
      if (lines.every((l) => /^\d+\.\s+/.test(l.trim()) || !l.trim())) {
        const items = lines
          .filter((l) => l.trim())
          .map((l) => `<li>${inlineHtml(l.replace(/^\d+\.\s+/, ''))}</li>`)
          .join('')
        return `<ol>${items}</ol>`
      }
      const first = lines[0]?.trim() ?? ''
      if (/^###\s+/.test(first)) return `<h3>${inlineHtml(first.replace(/^###\s+/, ''))}</h3>`
      if (/^##\s+/.test(first)) return `<h2>${inlineHtml(first.replace(/^##\s+/, ''))}</h2>`
      if (/^#\s+/.test(first)) return `<h1>${inlineHtml(first.replace(/^#\s+/, ''))}</h1>`
      return `<p>${lines.map((l) => inlineHtml(l)).join('<br/>')}</p>`
    })
    .join('\n')
}

function inlineHtml(text: string): string {
  return text
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
}

function escapePdfText(text: string): string {
  return text.replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)')
}

/** Minimal multi-page text PDF (no external deps). */
function buildSimplePdf(title: string, markdown: string): Blob {
  const plain = stripMarkdown(markdown)
  const maxWidth = 90
  const wrapLine = (line: string): string[] => {
    if (line.length <= maxWidth) return [line || ' ']
    const out: string[] = []
    let rest = line
    while (rest.length > maxWidth) {
      let breakAt = rest.lastIndexOf(' ', maxWidth)
      if (breakAt < 40) breakAt = maxWidth
      out.push(rest.slice(0, breakAt))
      rest = rest.slice(breakAt).trimStart()
    }
    if (rest) out.push(rest)
    return out
  }

  const lines = plain.split('\n').flatMap(wrapLine)
  const linesPerPage = 48
  const pages: string[][] = []
  for (let i = 0; i < lines.length; i += linesPerPage) {
    pages.push(lines.slice(i, i + linesPerPage))
  }
  if (pages.length === 0) pages.push([' '])

  const objects: string[] = []
  const add = (body: string) => {
    objects.push(body)
    return objects.length
  }

  const contentIds: number[] = []

  for (const pageLines of pages) {
    const streamLines = [
      'BT',
      '/F1 11 Tf',
      '50 780 Td',
      '14 TL',
      `(${escapePdfText(title)}) Tj`,
      'T*',
      'T*',
      '/F1 10 Tf',
      '12 TL',
      ...pageLines.flatMap((line) => [`(${escapePdfText(line)}) Tj`, 'T*']),
      'ET',
    ]
    const stream = streamLines.join('\n')
    const contentId = add(
      `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
    )
    contentIds.push(contentId)
  }

  const fontId = add('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
  const pageIds: number[] = []
  for (const contentId of contentIds) {
    pageIds.push(
      add(
        `<< /Type /Page /Parent 0 0 R /MediaBox [0 0 612 792] /Contents ${contentId} 0 R /Resources << /Font << /F1 ${fontId} 0 R >> >> >>`,
      ),
    )
  }

  const kidsRef = pageIds.map((id) => `${id} 0 R`).join(' ')
  const pagesId = add(`<< /Type /Pages /Kids [ ${kidsRef} ] /Count ${pageIds.length} >>`)

  // Patch parent refs in page objects
  for (let i = 0; i < pageIds.length; i++) {
    const id = pageIds[i]
    objects[id - 1] = objects[id - 1].replace('/Parent 0 0 R', `/Parent ${pagesId} 0 R`)
  }

  const catalogId = add(`<< /Type /Catalog /Pages ${pagesId} 0 R >>`)

  let pdf = '%PDF-1.4\n'
  const offsets: number[] = [0]
  for (let i = 0; i < objects.length; i++) {
    offsets.push(pdf.length)
    pdf += `${i + 1} 0 obj\n${objects[i]}\nendobj\n`
  }
  const xrefStart = pdf.length
  pdf += `xref\n0 ${objects.length + 1}\n`
  pdf += '0000000000 65535 f \n'
  for (let i = 1; i <= objects.length; i++) {
    pdf += `${String(offsets[i]).padStart(10, '0')} 00000 n \n`
  }
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root ${catalogId} 0 R >>\n`
  pdf += `startxref\n${xrefStart}\n%%EOF`

  return new Blob([pdf], { type: 'application/pdf' })
}

export function downloadReportFile(
  filename: string,
  markdown: string,
  format: ReportDownloadFormat,
) {
  const base = safeBaseName(filename)

  if (format === 'md') {
    triggerDownload(
      new Blob([markdown], { type: 'text/markdown;charset=utf-8' }),
      `${base}.md`,
    )
    return
  }

  if (format === 'doc') {
    const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${base}</title></head><body>${markdownToHtml(markdown)}</body></html>`
    triggerDownload(new Blob(['\ufeff', html], { type: 'application/msword' }), `${base}.doc`)
    return
  }

  triggerDownload(buildSimplePdf(base.replace(/-/g, ' '), markdown), `${base}.pdf`)
}

export const REPORT_DOWNLOAD_OPTIONS: {
  format: ReportDownloadFormat
  label: string
}[] = [
  { format: 'md', label: '.md' },
  { format: 'pdf', label: 'PDF' },
  { format: 'doc', label: '.doc' },
]
