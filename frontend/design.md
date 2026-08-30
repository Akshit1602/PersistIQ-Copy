# MatchView — Design System & Style Guide

> **Audience:** Engineers and AI agents extending this application.  
> **Goal:** Every new screen, component, and flow should look and behave like it shipped with MatchView on day one.

MatchView is a B2B experimentation workspace (hypothesis validation, analytics lab, chat, insights, reports). The visual language is **light, airy, and blue-forward** — soft surfaces, pill-like controls, Manrope typography, and a dark navy global rail.

---

## 1. Tech stack (do not diverge without reason)

| Layer | Choice |
|-------|--------|
| Framework | React 19 + TypeScript |
| Build | Vite 8 |
| Styling | Tailwind CSS v4 (`@import "tailwindcss"`) |
| Font | Manrope (`@fontsource/manrope` weights 400–700) |
| Icons | `lucide-react` via `AppIcon` wrapper |
| State | React Context (`MatchViewContext`, `ConversationalLoopContext`) |

**Rules**

- Use Tailwind utility classes and tokens from `src/index.css` — not inline hex in components.
- Do **not** add CSS-in-JS, styled-components, or a second UI kit.
- Prefer extending existing shared components before creating one-offs.

---

## 2. Repository structure

```
MatchView App/
├── public/                 # Static assets served at /
│   ├── favicon.svg         # MatchView spinner mark
│   └── *.svg               # Partner / brand marks
├── src/
│   ├── assets/             # Bundled images, SVGs, video (import in TS)
│   ├── components/
│   │   ├── analytics-lab/  # Right-rail lab panel, module forms, field primitives
│   │   ├── auth/           # Login screen, brand lockup, hero illustration
│   │   ├── chat/           # Chat stream, pills, evaluation cards, messaging bar
│   │   ├── insights/       # Dashboard cards, chart drawer, metric sheets
│   │   ├── layout/         # App shell, global rail, sidebar, knowledge archive
│   │   ├── shared/         # Cross-feature primitives (icons, sliders, overlays)
│   │   └── workspace/      # Project home, validators, wizards, reports, headers
│   ├── constants/          # Layout dimensions, magic numbers (not design tokens)
│   ├── context/            # Global app state + hooks
│   ├── data/               # Mock data, schemas, builders, registries (no JSX)
│   ├── services/           # Backend HTTP/SSE client (api.ts)
│   ├── utils/              # Pure helpers
│   ├── index.css           # ★ Single source of design tokens & global utilities
│   ├── App.tsx
│   └── main.tsx
└── design.md               # This file
```

### Channels: digital vs store

Projects carry a `channel` (`ProjectChannel = 'digital' | 'store'`), and experiments
inherit it from their project. The store channel covers retail concurrent-impact
testing — panel matching, rollout waves, store-level guardrails — and reuses the
same 21 Analytics Lab modules rather than adding new ones.

Store-specific surfaces are **sibling components prefixed `Store*`**, selected at
render time by channel; the digital component stays untouched:

```tsx
const channel = projects.find((p) => p.id === activeExperimentProjectId)?.channel ?? 'digital'
{channel === 'store' ? <StoreInsightsDashboard /> : <InsightsDashboardGrid />}
```

Families: `analytics-lab/Store*Panel.tsx` (per-module store panels),
`workspace/Store*Step.tsx` + `StorePanelMatchingWizard.tsx` (setup flow),
`insights/Store*.tsx` and the chart components (store readouts), with their
domain calculators in `data/store*.ts`.

**Do not branch on channel inside a shared component.** Add a `Store*` sibling and
switch at the call site, so each file stays readable and one channel can never
break the other.

### Folder placement rules

| If you are building… | Put it in… |
|----------------------|------------|
| Reusable UI used in 2+ features | `components/shared/` |
| Feature-specific screen or panel | `components/workspace/`, `chat/`, `insights/`, or `analytics-lab/` |
| App chrome (nav, shell) | `components/layout/` |
| Types, mock data, form schemas | `context/types.ts` or `data/` |
| Fixed widths / panel sizes | `constants/layout.ts` |

### File naming

| Pattern | Example |
|---------|---------|
| React components | `PascalCase.tsx` — `HypothesisValidatorPanel.tsx` |
| Hooks | `useCamelCase.ts` — `useAnalyticsLab.ts` |
| Data / pure TS | `camelCase.ts` — `hypothesisValidatorDraft.ts` |
| Constants | `camelCase.ts` inside `constants/` |
| One default export component per file | `export function Foo()` (named exports preferred) |

**Do not** use `index.tsx` barrel files unless the folder already uses that pattern.

---

## 3. Design tokens

All tokens live in `src/index.css` inside `@theme { }`. Tailwind maps them automatically (e.g. `--color-surface-base` → `bg-surface-base`).

### 3.1 Color — light workspace

| Token | Hex | Tailwind | Usage |
|-------|-----|----------|-------|
| `surface-base` | `#f0f8ff` | `bg-surface-base` | Page canvas, input backgrounds |
| `surface-raised` | `#ffffff` | `bg-surface-raised` | Cards, panels, dropdowns |
| `surface-hover` | `#e8f0fe` | `bg-surface-hover` | Hover states, chips, value badges |
| `text-primary` | `#0a1628` | `text-text-primary` | Headings, body, input text |
| `text-secondary` | `#475569` | `text-text-secondary` | Captions, labels, placeholders |
| `border-muted` | `#3b82f6` | `border-border-muted`, `bg-border-muted` | Borders, primary buttons, active tabs |
| `brand-blue` | `#3b82f6` | `text-brand-blue` | Accents (same family as border) |

**Border opacity convention:** Use `border-border-muted/15` to `/40` for subtle hierarchy — never solid heavy borders on light surfaces.

### 3.2 Color — global rail (dark)

| Token | Usage |
|-------|-------|
| `rail-base` | Rail background (`#0a1628`) |
| `rail-raised` | History / sidebar panel |
| `rail-hover` | Active & hover nav items |
| `rail-text-primary` | White labels on rail |
| `rail-text-secondary` | Muted rail labels |
| `rail-border` | Rail dividers |
| `rail-accent` | Rail accent blue |

Apply via utility classes: `text-rail-text-primary`, `bg-rail-hover`, `focus-ring-rail`.

### 3.3 Brand spinner gradients (logo / loading)

From `src/assets/spinner.svg` — use for loading states and favicon only:

| Stop | Colors | Meaning |
|------|--------|---------|
| Blue | `#0900FB` → `#00C3FF` | Primary mark |
| Pink | `#DC003E` → `#FF6D98` | Secondary facet |
| Gold | `#CA880F` → `#FFE115` / `#F7A000` | Highlight facet |

Use `MatchViewSpinner` + `StepTransitionOverlay` / `SynthesisProgressOverlay` for branded loading — do not invent new spinners.

### 3.4 Typography

**Font:** Manrope only. Body default is `text-sm` (14px).

| Scale token | Size | Tailwind class | Use for |
|-------------|------|----------------|---------|
| `text-micro` | 10px | `text-micro` | Badges, timestamps, overlines, chips |
| `text-xs` | 12px | `text-xs` | Captions, dense UI, form labels, chat |
| `text-sm` | 14px | `text-sm` | Body, inputs (default) |
| `text-base` | 16px | `text-base` | Panel titles |
| `text-lg` | 18px | `text-lg` | Section emphasis |
| `text-display` | 24px | `text-display` | Login hero |
| `text-display-lg` | 28px | `text-display-lg` | Large login headline |

**Semantic type classes** (prefer over ad-hoc size + weight):

```tsx
.type-display    // login hero
.type-title      // text-base font-semibold — panel headings
.type-subtitle   // text-xs text-secondary — under titles
.type-body       // text-sm — default content
.type-caption    // text-xs font-medium secondary
.type-micro      // text-micro secondary
.type-overline   // text-micro uppercase tracking-wide — field labels
```

**Avoid:** `text-[10px]`, `text-[11px]`, or arbitrary pixel font sizes.

**Numbers:** Add `tabular-nums` for metrics, sliders, and counters.

### 3.5 Spacing

Custom spacing scale (slightly tighter than default Tailwind):

| Token | Value |
|-------|-------|
| `spacing-1` | 6px |
| `spacing-2` | 8px |
| `spacing-3` | 10px |
| `spacing-4` | 12px |
| `spacing-5` | 14px |
| `spacing-6` | 16px |
| `spacing-7` | 18px |
| `spacing-8` | 20px |

**Common gaps:** `gap-3` (12px) in form grids, `gap-3.5` (14px) in vertical stacks, `px-4 py-3` in panel footers.

### 3.6 Border radius

| Token | Value | Tailwind | Use |
|-------|-------|----------|-----|
| `radius-xs` | 12px | `rounded-xs` | Inputs, buttons, cards, nav items |
| `radius-sm` | 20px | `rounded-sm` | Larger containers (rare) |
| `radius-md` | 50px | `rounded-md` | Pills |
| `radius-lg` | 9999px | `rounded-lg` | Fully round |

**Also used in code:** `rounded-[8px]` for project cards, multi-select, and module list containers — treat **8px** as the “compact card” radius when `rounded-xs` (12px) feels too soft.

### 3.7 Shadows & elevation

| Class | Usage |
|-------|-------|
| `shadow-glow` | `0 4px 15px rgba(59,130,246,0.25)` — dropdowns, active emphasis |
| `glass-panel` | White card + subtle border + light shadow |
| `rail-panel` | Dark gradient rail |
| `history-panel` | Sidebar thread tree |
| `lab-panel` | Analytics lab right rail |
| `canvas-bg` | App background with soft blue radial washes |

### 3.8 Motion

| Token | Value |
|-------|-------|
| `duration-instant` | 300ms |
| `duration-fast` | 500ms |

Use `transition-colors duration-instant` on interactive elements. Respect `prefers-reduced-motion: reduce` — decorative animations are disabled in `index.css`.

---

## 4. Layout system

### 4.1 App shell hierarchy

```
AppShell (canvas-bg, h-screen)
├── GlobalRail (fixed left, w-16 collapsed / w-60 expanded)
├── StaticSidebar (history tree — hidden on Projects Home)
├── Main content
│   ├── ProjectsHome (no project selected)
│   └── MainWorkspace (project selected)
│       ├── WorkspaceHeader (tabs: Chat | Insights | Reports)
│       ├── Tab content (ChatView / InsightsView / ReportsView)
│       └── AnalyticsLabPanel (analyst persona only, right rail)
└── Overlays: NewProjectPanel, HypothesisValidatorPanel, AudienceSelectionWizard, ExperimentDataSourcesDialog
```

**Spacer:** A `w-16 shrink-0` div reserves space for the collapsed global rail.

### 4.2 Key dimensions (`constants/layout.ts`)

| Constant | Value | Usage |
|----------|-------|-------|
| `ANALYTICS_LAB_WIDTH` | 340px | Expanded lab panel |
| `ANALYTICS_LAB_COLLAPSED_WIDTH` | 44px | Collapsed lab strip |

Global rail: `w-16` / `w-60` in `GlobalRail.tsx`.

### 4.3 Grid patterns

- **Two-column forms:** `grid grid-cols-2 gap-3`
- **Project cards:** responsive grid on `ProjectsHome`
- **Insights:** dashboard grid in `InsightsDashboardGrid`

Always wrap grid children with `min-w-0` to prevent overflow in narrow panels.

---

## 5. Component catalog

### 5.1 Shared primitives (`components/shared/`)

| Component | Purpose |
|-----------|---------|
| `AppIcon` | **Required** wrapper for all Lucide icons — sizes `xs`–`lg`, stroke 1.75 |
| `GlassPanel` | White elevated surface |
| `MatchViewLogo` / `MatchViewSpinner` | Brand mark & animated loader |
| `NumericSliderField` | Bounded numeric slider + value badge (hypothesis validator) |
| `MultiSelectDropdown` | Searchable multi-select with chips |
| `PersonaSwitcher` | Executive / Analyst toggle |
| `StepTransitionOverlay` | Step-to-step loading (2–3s) with spinner |
| `SynthesisProgressOverlay` | Full-panel synthesis loading |
| `DownloadAsMenu` | Export menu (.md / PDF / .doc) |

### 5.2 Analytics Lab fields (`components/analytics-lab/fields/`)

Schema-driven via `FormFieldRenderer` + `moduleFormSchemas.ts`:

`TextField`, `TextAreaField`, `NumberField`, `SelectField`, `SliderField`, `ToggleField`

Use these for **lab module forms** — not for hypothesis validator (which uses inline patterns).

### 5.3 Layout (`components/layout/`)

`AppShell`, `GlobalRail`, `StaticSidebar`, `ChatHistoryTree`, `MainWorkspace`, `RailUserFooter`

### 5.4 When to create a new shared component

Create in `shared/` when:

1. The pattern appears twice, or
2. It encodes design tokens (slider, dropdown, overlay), or
3. Agents would otherwise copy-paste 10+ Tailwind classes.

Keep feature-specific markup in `workspace/` or `chat/`.

---

## 6. Form & input patterns

### 6.1 Standard text/number input

Canonical class string (from `HypothesisValidatorPanel`):

```tsx
const inputClass =
  'focus-ring box-border w-full min-w-0 rounded-xs border border-border-muted/25 bg-surface-base px-2.5 py-1.5 text-xs text-text-primary placeholder:text-text-secondary'
```

Textarea: append `resize-none`.  
Select: append `appearance-none` + custom chevron background.

### 6.2 Field labels

| Context | Component / class |
|---------|-------------------|
| Opportunity sizing (step 2) | `FieldLabel` → `type-overline` |
| Power / metrics (steps 3–4) | `SoftFieldLabel` → `type-caption` + optional info tooltip |
| Required fields | Red asterisk `text-red-600` with `aria-label="required"` |

### 6.3 Auto-detect inputs

`AutoDetectNumberInput` — number field + sparkle button to apply/clear mock detected baselines. Use for fields backed by `OPPORTUNITY_AUTO_DETECTED` / `POWER_AUTO_DETECTED`.

### 6.4 Numeric sliders

Use `NumericSliderField` for **bounded ratios and percentages** where dragging is intuitive:

- Gross margin (0–1) → display as `%`
- Time horizon (months)
- Significance α (0.01–0.20) → display as decimal `0.05`
- Statistical power (0.5–0.99) → display as `%`

Keep free-form or high-precision fields as `input type="number"`.

Slider styling uses `.numeric-slider` in `index.css` — do not duplicate.

### 6.5 Multi-select

`MultiSelectDropdown`:

- Trigger: `min-h-[38px]`, `rounded-[8px]`, `border-border-muted/25`
- Chips: `rounded-[6px] bg-border-muted/10 text-micro text-border-muted`
- Menu: `bg-surface-raised shadow-glow`

### 6.6 Section containers

Grouped fields (e.g. KPI inputs):

```tsx
className="rounded-[8px] border border-border-muted/15 bg-surface-base/70 px-3 py-3"
```

Review / summary blocks:

```tsx
className="rounded-xs border border-border-muted/25 bg-surface-base px-3 py-3"
```

---

## 7. Buttons & actions

### 7.1 Primary (filled blue)

```tsx
className="focus-ring rounded-xs bg-border-muted px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
```

### 7.2 Secondary (outline)

```tsx
className="focus-ring rounded-xs border border-border-muted/25 px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-surface-hover hover:text-text-primary disabled:opacity-40"
```

### 7.3 Destructive

`text-red-500 hover:bg-red-50 hover:text-red-600` on icon buttons (delete project).

### 7.4 Tab / segment control (active)

Active tab (see `WorkspaceHeader`):

```tsx
bg-border-muted text-white shadow-glow
```

Inactive: `text-text-secondary hover:bg-surface-hover`.

### 7.5 Icon-only

`focus-ring flex h-8 w-8 items-center justify-center rounded-xs` + `AppIcon`.

**Always** use `type="button"` unless submitting a form.

---

## 8. Focus & accessibility

| Class | Context |
|-------|---------|
| `focus-ring` | Light surfaces (workspace) |
| `focus-ring-rail` | Dark global rail |

Pattern: `outline-none focus-visible:ring-2 focus-visible:ring-border-muted focus-visible:ring-offset-2`.

- Icons: `aria-hidden="true"` on decorative icons; meaningful `aria-label` on icon-only buttons.
- Overlays: `role="status"`, `aria-live="polite"`, `aria-busy="true"` on loading overlays.
- Tabs: `role="tablist"`, `role="tab"`, `aria-selected`.
- Tooltips: hover + `focus-within` reveal (see `SoftFieldLabel` info pattern).

---

## 9. Icons

- **Library:** Lucide React only.
- **Wrapper:** `AppIcon` with `size="xs" | "sm" | "md" | "lg"`.
- **Stroke:** Default `1.75` — do not pass random sizes to raw `<Icon />`.
- **Semantic icons:** Module icons mapped in `data/moduleIcons.ts`.

Common icons: `Sparkles` (auto-detect), `Info` (tooltips), `ChevronLeft/Right` (navigation), `Check` (completed steps).

---

## 10. Panels, wizards & modals

### Hypothesis Validator (`HypothesisValidatorPanel`)

- 5-step stepper: Hypothesis → Sizing → Metrics → Power → Review
- Step transition: `StepTransitionOverlay` (spinner, 2–3s)
- Finalize: `SynthesisProgressOverlay`
- Footer: Back / Skip / Continue / Finalize pattern
- Content: `max-w` constrained, `overflow-hidden` on power step

### Side panels

`NewProjectPanel`, `AudienceSelectionWizard` — slide-over pattern with header, scroll body, footer actions. Match padding: `px-4 py-4` body, `border-t` footer.

### Dialogs

`ExperimentDataSourcesDialog` — centered modal, same input classes as validator.

---

## 11. Chat & rich content

- Formatted assistant text: `ChatRichText` (markdown-like: headings, lists, bold, links).
- Evaluation cards: `InteractiveEvaluationCard`, `PowerEvaluationCard`, `BriefHandoffCard`.
- Action chips: `ActionPills`, `SmartActionPhasePills` — small rounded pills, blue active state.

---

## 12. Analytics Lab UI rules

- Module tree: category cards `rounded-[8px]`; active module = square selection, blue dot on right (no icon chip background).
- Panel: `lab-panel` class, collapsible to 44px.
- View tabs: Modules | Results — same segment style as workspace tabs but smaller.
- Forms: render via `ModuleConfigForm` + schema — do not hand-roll duplicate fields.

---

## 13. Data layer conventions

- **No JSX in `data/`** — only types, mocks, builders, registries.
- Module IDs: kebab-case strings (`'power-calculator'`, `'opportunity-sizing'`).
- Context types: `src/context/types.ts` — extend here for new global state.
- Mock/auto-detect values: colocate with feature (`hypothesisValidatorDraft.ts`).

---

## 14. Agent checklist (before opening a PR)

- [ ] Uses tokens from `index.css` — no hardcoded `#3b82f6` in TSX unless SVG.
- [ ] Typography uses `text-micro` / `text-xs` / semantic `type-*` classes.
- [ ] Icons go through `AppIcon`.
- [ ] Interactive elements have `focus-ring` or `focus-ring-rail`.
- [ ] Forms use `inputClass` pattern or existing field components.
- [ ] `min-w-0` on flex/grid children in panels.
- [ ] Loading states use `MatchViewSpinner` or existing overlays.
- [ ] New file is in the correct folder per §2.
- [ ] Component name is `PascalCase` and describes role (`*Panel`, `*View`, `*Dialog`, `*Card`).
- [ ] `prefers-reduced-motion` respected for new animations.

---

## 15. Quick reference — copy/paste

### Page background

```tsx
<div className="canvas-bg flex h-screen flex-col">
```

### Card

```tsx
<article className="glass-panel rounded-[8px] border border-border-muted/15 p-4">
```

### Panel title block

```tsx
<div>
  <p className="text-sm font-semibold text-text-primary">Section Title</p>
  <p className="mt-0.5 text-xs text-text-secondary">Supporting description.</p>
</div>
```

### Two-column form row

```tsx
<div className="grid grid-cols-2 gap-3">
  <div className="min-w-0">{/* field */}</div>
  <div className="min-w-0">{/* field */}</div>
</div>
```

---

## 16. Related files (source of truth)

| Concern | File |
|---------|------|
| Design tokens & utilities | `src/index.css` |
| Layout widths | `src/constants/layout.ts` |
| Global state / types | `src/context/types.ts`, `MatchViewContext.tsx` |
| Module form schemas | `src/data/moduleFormSchemas.ts` |
| Validator steps & validation | `src/data/hypothesisValidatorDraft.ts` |
| Brand assets | `src/assets/matchview_logo.svg`, `src/assets/spinner.svg` |

---

*Last updated to match the codebase as of the hypothesis validator slider work and global navigation structure. When tokens or patterns change, update this document in the same PR.*
