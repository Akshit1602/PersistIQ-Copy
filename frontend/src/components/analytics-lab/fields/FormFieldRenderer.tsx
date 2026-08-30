import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { AlignLeft, Hash, List, Percent, ToggleLeft } from 'lucide-react'
import type { FormFieldSchema } from '../../../data/moduleFormSchemas'
import type { FieldSuggestion } from '../../../data/inputSuggestions'
import { AppIcon } from '../../shared/AppIcon'
import { SuggestedValueBadge } from '../../shared/SuggestedValueBadge'
import { NumberField } from './NumberField'
import { SelectField } from './SelectField'
import { SliderField } from './SliderField'
import { TextAreaField } from './TextAreaField'
import { TextField } from './TextField'
import { ToggleField } from './ToggleField'

const FIELD_ICONS: Partial<Record<FormFieldSchema['type'], LucideIcon>> = {
  number: Hash,
  slider: Percent,
  select: List,
  textarea: AlignLeft,
  text: AlignLeft,
  toggle: ToggleLeft,
}

interface FormFieldRendererProps {
  field: FormFieldSchema
  value: unknown
  onChange: (key: string, value: unknown) => void
  highlighted?: boolean
  /** Provenance for this field, when the suggestion engine has one. */
  suggestion?: FieldSuggestion
}

function FieldGroup({
  highlighted,
  children,
}: {
  highlighted?: boolean
  children: ReactNode
}) {
  return (
    <div
      className={`transition-all duration-500 ${
        highlighted ? 'rounded-xs ring-2 ring-border-muted/40 ring-offset-1 ring-offset-surface-base' : ''
      }`}
    >
      {children}
    </div>
  )
}

function FieldLabel({ field }: { field: FormFieldSchema }) {
  const Icon = FIELD_ICONS[field.type]
  return (
    <div className="mb-1">
      <div className="flex items-center gap-1">
        {Icon && <AppIcon icon={Icon} size="xs" className="text-text-secondary" />}
        <label className="type-overline">
          {field.label}
        </label>
      </div>
      {field.helpText ? (
        <p className="mt-0.5 text-micro text-text-secondary">{field.helpText}</p>
      ) : null}
    </div>
  )
}

export function FormFieldRenderer({
  field,
  value,
  onChange,
  highlighted,
  suggestion,
}: FormFieldRendererProps) {
  return (
    <div>
      <FieldControl field={field} value={value} onChange={onChange} highlighted={highlighted} />
      {suggestion ? (
        <SuggestedValueBadge
          suggestion={suggestion}
          value={value}
          onApply={(next) => onChange(field.key, next)}
          onRevert={() => onChange(field.key, field.defaultValue)}
        />
      ) : null}
    </div>
  )
}

function FieldControl({ field, value, onChange, highlighted }: FormFieldRendererProps) {
  switch (field.type) {
    case 'number':
      return (
        <FieldGroup highlighted={highlighted}>
          <FieldLabel field={field} />
          <NumberField
            value={Number(value ?? field.defaultValue)}
            min={field.min}
            max={field.max}
            step={field.step}
            placeholder={field.placeholder}
            onChange={(v) => onChange(field.key, v)}
          />
        </FieldGroup>
      )
    case 'slider':
      return (
        <FieldGroup highlighted={highlighted}>
          <FieldLabel field={field} />
          <SliderField
            value={Number(value ?? field.defaultValue)}
            min={field.min ?? 0}
            max={field.max ?? 100}
            step={field.step}
            onChange={(v) => onChange(field.key, v)}
          />
        </FieldGroup>
      )
    case 'select':
      return (
        <FieldGroup highlighted={highlighted}>
          <FieldLabel field={field} />
          <SelectField
            value={String(value ?? field.defaultValue)}
            options={field.options ?? []}
            onChange={(v) => onChange(field.key, v)}
          />
        </FieldGroup>
      )
    case 'textarea':
      return (
        <FieldGroup highlighted={highlighted}>
          <FieldLabel field={field} />
          <TextAreaField
            value={String(value ?? '')}
            placeholder={field.placeholder}
            rows={field.rows}
            onChange={(v) => onChange(field.key, v)}
          />
        </FieldGroup>
      )
    case 'text':
      return (
        <FieldGroup highlighted={highlighted}>
          <FieldLabel field={field} />
          <TextField
            value={String(value ?? '')}
            placeholder={field.placeholder}
            onChange={(v) => onChange(field.key, v)}
          />
        </FieldGroup>
      )
    case 'toggle':
      return (
        <FieldGroup highlighted={highlighted}>
          <ToggleField
            label={field.label}
            description={field.toggleLabel}
            value={Boolean(value ?? field.defaultValue)}
            onChange={(v) => onChange(field.key, v)}
          />
        </FieldGroup>
      )
    case 'readonly':
      return (
        <FieldGroup highlighted={highlighted}>
          <FieldLabel field={field} />
          <p className="text-xs text-text-primary">{String(value ?? field.defaultValue)}</p>
        </FieldGroup>
      )
    default:
      return null
  }
}
