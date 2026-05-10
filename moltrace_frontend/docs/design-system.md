# MolTrace UI Design System

Reference for the module-coded visual identity used across the MolTrace frontend.
Captures what the design system codifies, where the tokens live, and the patterns
to use when adding or extending a surface.

The design system applies the user-facing instruction:
> Build each tab, section, button, card, and module to be user-friendly,
> easy to visualize, easy to click and navigate, and simple to manage —
> without changing the application's data, workflows, or behavior.

---

## 1. Module color palette

Each MolTrace persona / module gets a single accent color. The accent identifies
which module a surface belongs to and signals what kind of work happens there.

| Token | Hex | Soft variant | Used for |
|---|---|---|---|
| `--mt-teal` | `#00DFA0` | `--mt-teal-soft` | Spectroscopy, AI, ML, Knowledge, Compounds (primary brand) |
| `--mt-cyan` | `#00B8D9` | `--mt-cyan-soft` | Regulatory Hub, Validation Dashboard, Validation Center, all validation sub-workspaces |
| `--mt-violet` | `#6B3FE0` | `--mt-violet-soft` | Reaction Optimization, optimization signals |
| `--mt-amber` | `#E8A030` | `--mt-amber-soft` | Warnings, deviations, drift alerts, severity-elevated cards |
| `--mt-red` | `#E84040` | `--mt-red-soft` | Errors, failed tests, critical alerts |
| `--mt-green` | `#22C55E` | `--mt-green-soft` | Success, passed validation, recorded states |
| `--mt-slate` | `#64748B` | `--mt-slate-soft` | Admin, tenant ops, all `/settings/*` workspaces |

All tokens live in `app/globals.css` under `:root`. They are additive; they do
not override the existing semantic tokens (`--background`, `--foreground`,
`--primary`, etc.). Tailwind code accesses them via arbitrary value syntax:
`text-[color:var(--mt-teal)]`, `[background-color:var(--mt-teal-soft)]`, etc.
Inline styles use them directly: `style={{ color: "var(--mt-teal)" }}`.

### Persona / module → accent map

| Surface group | Accent | Examples |
|---|---|---|
| Dashboard | teal | `/dashboard` |
| SpectraCheck | teal | `/spectracheck` and all 12 inner tabs |
| Reports / Review Queue | teal | `/reports`, `/actions` |
| ML Model Factory | teal | `/ml`, `/ml/calibration`, `/ml/deployment-candidates`, `/ml/evaluation` |
| AI Services | teal | `/ai`, `/ai/predictions` |
| Knowledge Library | teal | `/knowledge` and all knowledge sub-routes |
| Compounds / Batches | teal | `/compounds`, `/batches` |
| Regulatory Hub | cyan | `/regulatory`, Regulatory Dossier (7+11 tabs) |
| Validation Dashboard | cyan | `/validation`, `/validation/[runId]` |
| Validation Center | cyan | `/validation-center` and all 9 sub-workspaces |
| Reaction Optimization | violet | `/reactions`, program-level + project-level (11 tabs) |
| Settings | slate | `/settings/*` (Method Registry, Connectors, Watch Folders, Mapping Templates, Team, Deployment) |
| Admin | slate | `/admin/*` |

When a single workspace touches multiple modules (e.g. severity-coded KPIs in a
cyan workspace), the workspace identity stays cyan and individual KPIs may
adopt amber/red/green/violet for severity. See §4.

---

## 2. Page chrome pattern

Every top-level workspace uses the same header structure. This is what makes
navigation feel cohesive — a user can tell at a glance which module they are in.

```tsx
<div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
  <div className="space-y-1">
    <p
      className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
      style={{ color: "var(--mt-cyan)" }}        {/* module accent */}
    >
      MolTrace · Validation Center               {/* eyebrow */}
    </p>
    <h1 className="font-mono text-2xl font-bold tracking-tight">
      Validation Center                           {/* page title */}
    </h1>
    <p className="text-sm text-muted-foreground">
      Build validation projects, risk assessments, ...
    </p>
  </div>
  <BackendStatusIndicator />
</div>
```

Rules:

- **Eyebrow** uses module-accent color, `MOLTRACE · <SECTION>` for top-level
  surfaces, `MOLTRACE · <SECTION> · <SUB>` for sub-routes
  (e.g. `MOLTRACE · SETTINGS · METHOD REGISTRY`).
- **H1** is always `font-mono text-2xl font-bold tracking-tight`. Never use
  `text-2xl font-semibold` — that is the legacy pattern and was swept globally.
- **Description paragraph** is `text-sm text-muted-foreground` (not the default
  size).
- `BackendStatusIndicator` aligns right; for project-detail surfaces, a `Back`
  button sits above the eyebrow.

---

## 3. Component primitives

All five primitives live under `components/dashboard/` (and `components/science/`
for the ring). They are stable reskinning targets — sweep once, propagate everywhere.

### `ModuleCard` — `components/dashboard/module-card.tsx`

Replaces the `<Card><CardHeader><CardTitle>...</CardTitle></CardHeader><CardContent>...</CardContent></Card>`
pattern for any "detail" card on a workspace.

```tsx
<ModuleCard
  accent="cyan"            // teal | cyan | violet | amber | slate
  eyebrow="Detail"         // optional mono caps eyebrow above the title
  title="Selected CAPA"
  icon={FileText}          // optional Lucide icon, tinted with accent
  description="Selected CAPA details — update status, ..."
  badge={<Badge>open</Badge>}   // optional, top-right
  href="/...detail"        // optional, makes the card hoverable + a CTA footer
  ctaLabel="Open detail"   // shown in CTA footer when `href` set
>
  {/* card body */}
</ModuleCard>
```

Adds a 3px top stripe in the accent color and the standard mono header chrome.
**Title accepts `ReactNode`**, so `<InfoTooltip>` can sit beside it via
`<span className="flex items-center gap-2">…</span>`.

### `AlertCard` — `components/dashboard/alert-card.tsx`

Replaces all `<Alert variant="destructive">...</Alert>` patterns and the inline
`<p className="text-xs text-warning">` banners.

```tsx
<AlertCard
  variant="warning"    // info | success | warning | error
  title="Locked records require a new version"
  description="Locked controlled records cannot be edited directly. ..."
  action={<Button>Acknowledge</Button>}   // optional right-side button
  icon={ServerOff}                         // optional override; defaults match variant
>
  {/* optional richer body — use children instead of `description` for multi-line content */}
</AlertCard>
```

Renders with a left accent border (4px) and tinted background using the soft
variant. Use `description` for short single-line text and `children` for
breakdowns (a `<div className="space-y-1 text-xs text-foreground/90">…</div>`
typically). **`description` is wrapped in a `<p>` tag**, so it cannot contain
block elements — use `children` if you need a list or multiple paragraphs.

### `KpiCard` — `components/dashboard/kpi-card.tsx`

The numeric KPI tile. Drives the dashboard summary grids.

```tsx
<KpiCard
  title="Open risks"
  icon={AlertTriangle}
  value={42}
  sub={<p className="text-xs text-muted-foreground">From open deviations</p>}
  severity="warning"     // neutral | warning | critical | success → drives stripe color
  accent="cyan"          // only used when severity === "neutral"
  href="/..."            // optional, makes the card a link
/>
```

When `severity === "neutral"` the stripe uses `accent`. Otherwise the stripe
uses the severity color (warning → amber, critical → red, success → green).
Value renders in mono `text-3xl` colored with the stripe.

### `DashboardSection` — `components/dashboard/dashboard-section.tsx`

Collapsible section wrapper for grouping subsections inside a workspace. Has its
own mono caps eyebrow and accent left-stripe trigger.

```tsx
<DashboardSection
  accent="teal"
  eyebrow="Trust signals"
  title="Confidence & calibration"
  icon={ShieldCheck}
  description="Cross-cohort drift and calibration summary"
  defaultOpen
>
  {/* nested cards */}
</DashboardSection>
```

### `ConfidenceRing` — `components/science/confidence-ring.tsx`

SVG ring with a centered mono percentage label. Used in evidence cards to show
match confidence at a glance.

```tsx
<ConfidenceRing value={87} accent="teal" size={64} />
```

---

## 4. KPI severity coding

When a workspace has a row of KPI cards, the stripe color carries semantic
meaning beyond module identity. The pattern, used uniformly in
Validation Dashboard / Validation Center / Connectors Center:

| KPI meaning | Stripe color |
|---|---|
| Total / count / module-identity neutral | module accent (cyan / teal / etc.) |
| Successful outcomes (Passed) | `var(--mt-green)` |
| Errors / failures (Failed tests) | `var(--mt-red)` |
| Warnings / attention (Open risks, Open drift, Warnings) | `var(--mt-amber)` |
| Optimization signals (CAPA items, Experimental methods) | `var(--mt-violet)` |

Manual implementation pattern (used directly when not using `KpiCard`):

```tsx
<Card
  className="overflow-hidden rounded-xl py-0"
  style={{ borderTop: "3px solid var(--mt-amber)" }}
>
  <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
    <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
      Open risks
    </CardTitle>
    <AlertTriangle className="h-4 w-4" style={{ color: "var(--mt-amber)" }} aria-hidden />
  </CardHeader>
  <CardContent className="pb-5">
    <div
      className="font-mono text-3xl font-bold tabular-nums leading-none"
      style={{ color: "var(--mt-amber)" }}
    >
      {summary.openRisks}
    </div>
  </CardContent>
</Card>
```

---

## 5. Tab pill styling

Workspaces with their own internal tab strip apply module-coded active tab
pills. Pattern, used in ML/AI Workspace and Validation Project Detail:

```tsx
<TabsTrigger
  value="overview"
  className="font-mono data-[state=active]:[background-color:var(--mt-cyan)] data-[state=active]:[color:#04080F] data-[state=active]:font-bold data-[state=active]:shadow-sm data-[state=inactive]:text-muted-foreground"
>
  Overview
</TabsTrigger>
```

The active state uses the workspace's module accent as the background and a
near-black foreground (`#04080F`) for legibility. Inactive tabs render as
muted text. The `font-mono` is uniform across active and inactive states.

---

## 6. Application chrome

### Sidebar (`components/app/app-sidebar.tsx`)

- Active nav item gets a 3px **left** accent stripe in `var(--mt-teal)` via
  `boxShadow: inset 3px 0 0 0 var(--mt-teal)`. The icon also tints to teal.
- Section eyebrows above each nav group: `font-mono text-[9px] font-bold
  uppercase tracking-[0.18em] text-muted-foreground/70` — `WORKSPACE`, `TEAM`,
  `ADMIN`, `SETTINGS`. Visible only when sidebar is expanded.
- Collapsed sidebar shows a thinner 2px stripe to remain visible.

### Topbar (`components/app/app-topbar.tsx`)

- AI Queue button: mono caps text, teal Sparkles icon, count badge with
  `var(--mt-teal-soft)` background and `var(--mt-teal)` text.
- Notifications bell: count badge uses `var(--mt-amber)` to signal
  "you have unread items" rather than a generic accent.
- Tenant selector / theme toggle / user avatar: stay neutral.

### Mobile bottom nav (`src/components/app-shell/MobileBottomNav.tsx`)

- Primary nav (5 buttons across the bottom): 2px teal **top** stripe on the
  active item (matches the bottom-edge nav direction) + teal icon.
- "More" sheet items: 3px teal left stripe + teal icon, mirroring the desktop
  sidebar's active-state language.

---

## 7. Status row stripes

For tables or lists where each row has a status, the row gets a 3px left stripe
in the status color via inline `boxShadow`:

```tsx
<TableRow style={{ boxShadow: `inset 3px 0 0 0 ${rowStripeColor}` }}>
  …
</TableRow>
```

Status → color mapping for evidence rows (used in SpectraCheck MS Evidence,
Confidence Suite, Evidence Queue):

| Status | Color |
|---|---|
| `pass`, `match`, `accepted` | `var(--mt-green)` |
| `fail`, `error`, `rejected` | `var(--mt-red)` |
| `warning`, `requires_review`, `needs_changes` | `var(--mt-amber)` |
| `pending`, `not_run`, neutral | `var(--mt-cyan)` |

---

## 8. Adding a new accent or surface

### Adding a new color token

1. Add `--mt-<name>: #<hex>;` and `--mt-<name>-soft: rgba(<r>, <g>, <b>, 0.10);`
   to `:root` in `app/globals.css`.
2. Extend `ModuleCardAccent` in `components/dashboard/module-card.tsx`:
   add `"name"` to the union type and `name: "var(--mt-<name>)"` to
   `ACCENT_VAR`.
3. Optionally extend `AlertCardVariant` (only if the color maps to a new
   semantic state — error, success, warning, info are usually enough).

### Adding a new top-level workspace

1. Pick the module accent based on the persona/section (see §1 map).
2. Apply the page chrome pattern (§2).
3. Wrap the alerts using `AlertCard` (§3).
4. Wrap each detail card using `ModuleCard` (§3).
5. If there is a KPI grid, use `KpiCard` or the manual KPI pattern (§4) with
   severity coding.
6. If there is a tab strip, apply the tab pill styling (§5).

### Adding a sub-workspace under an existing section

Mirror the parent workspace's accent. Use a longer eyebrow path:
`MolTrace · <Parent> · <Sub>` — e.g. `MolTrace · Settings · Method Registry`.

---

## 9. Common pitfalls

- **`AlertCard` `description` cannot contain block elements.** It is wrapped in
  a `<p>`. For multi-line breakdowns use `children` instead.
- **Custom icon components may not accept `style`.** When working with
  `SpectraCheckLogoIcon` / `ProgramsLogoIcon` etc., apply color via Tailwind
  `text-[color:var(--mt-teal)]` className instead of inline `style`.
  Lucide icons accept both.
- **Don't `replace_all` an unanchored class string.** When sweeping KPI patterns
  across a file, anchor the replacement to the surrounding `<Card>` opener so
  detail cards aren't accidentally swept.
- **iframes inside `ModuleCard`.** `ModuleCard` adds `CardContent` padding by
  default. For edge-flush iframe content, use a plain `Card` with manual
  `style={{ borderTop: "3px solid var(--mt-teal)" }}` and a manual mono caps
  eyebrow (the Confidence Suite HTML preview uses this pattern).
- **Don't mix `text-2xl font-semibold tracking-tight` with the new mono H1.**
  The legacy pattern was swept globally on 2026-05-10. Always use
  `font-mono text-2xl font-bold tracking-tight` for new H1s.

---

## 10. Files to touch when extending the system

| Concern | File |
|---|---|
| New color tokens | `app/globals.css` |
| ModuleCard accent enum | `components/dashboard/module-card.tsx` |
| AlertCard variant enum | `components/dashboard/alert-card.tsx` |
| KpiCard accent / severity | `components/dashboard/kpi-card.tsx` |
| ConfidenceRing accent | `components/science/confidence-ring.tsx` |
| DashboardSection accent | `components/dashboard/dashboard-section.tsx` |
| Sidebar nav structure | `components/app/app-sidebar.tsx` |
| Topbar buttons | `components/app/app-topbar.tsx` |
| Mobile bottom nav | `src/components/app-shell/MobileBottomNav.tsx` |
| AppShell layout | `src/components/app-shell/ResponsiveAppShell.tsx` |
