---
name: Redline Engineering Ops
colors:
  surface: '#131315'
  surface-dim: '#131315'
  surface-bright: '#39393b'
  surface-container-lowest: '#0e0e10'
  surface-container-low: '#1c1b1d'
  surface-container: '#201f22'
  surface-container-high: '#2a2a2c'
  surface-container-highest: '#353437'
  on-surface: '#e5e1e4'
  on-surface-variant: '#e4beba'
  inverse-surface: '#e5e1e4'
  inverse-on-surface: '#313032'
  outline: '#ab8986'
  outline-variant: '#5b403e'
  surface-tint: '#ffb3ad'
  primary: '#ffb3ad'
  on-primary: '#68000a'
  primary-container: '#ff5451'
  on-primary-container: '#5c0008'
  inverse-primary: '#b91a24'
  secondary: '#4edea3'
  on-secondary: '#003824'
  secondary-container: '#00a572'
  on-secondary-container: '#00311f'
  tertiary: '#d0bcff'
  on-tertiary: '#3c0091'
  tertiary-container: '#a078ff'
  on-tertiary-container: '#340080'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#ffdad7'
  primary-fixed-dim: '#ffb3ad'
  on-primary-fixed: '#410004'
  on-primary-fixed-variant: '#930013'
  secondary-fixed: '#6ffbbe'
  secondary-fixed-dim: '#4edea3'
  on-secondary-fixed: '#002113'
  on-secondary-fixed-variant: '#005236'
  tertiary-fixed: '#e9ddff'
  tertiary-fixed-dim: '#d0bcff'
  on-tertiary-fixed: '#23005c'
  on-tertiary-fixed-variant: '#5516be'
  background: '#131315'
  on-background: '#e5e1e4'
  surface-variant: '#353437'
typography:
  headline-xl:
    fontFamily: Geist
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.03em
  headline-xl-mobile:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Geist
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 26px
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Geist
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 22px
  body-md:
    fontFamily: Geist
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 18px
  code-lg:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 20px
  code-md:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 18px
  code-sm:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '400'
    lineHeight: 16px
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.04em
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 10px
    fontWeight: '500'
    lineHeight: 12px
    letterSpacing: 0.06em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1rem
  gutter-compact: 0.5rem
  margin: 1.5rem
  margin-mobile: 1rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1rem
  space-xl: 1.5rem
  space-2xl: 2rem
---

## Brand & Style

This design system embodies the ethos: *"AI-generated code is guilty until proven safe."* It establishes an ultra-precise, cyber-technical developer environment engineered for high-concurrency mission control, adversarial code testing, agentic orchestration, and automated remediation.

The style merges **Modern Cyber-Minimalism** with **High-Density Technical Telemetry**:
- **Atmosphere:** Deep void foundations, obsidian surfaces, and sharp optical contrasts.
- **Visual Tenor:** Surgical, high-stakes, uncompromising, and developer-first.
- **Emotional Resonance:** Total oversight, speed, rigorous security, and deterministic confidence.
- **Signature Aesthetics:** Precision terminal-inspired borders, hairline grid separation, faint red laser highlights, and focused neon status indicators.

## Colors

The palette relies on a disciplined dark-spectrum core punctuated by razor-sharp functional status colors:

- **Primary (`#ef4444` / Crimson Red):** Anchors brand presence, mission-critical attacks, fatal regressions, critical errors, and focal actions. Supported by `#dc2626` for active states and subtle radiant crimson glows (`rgba(239, 68, 68, 0.15)`).
- **Secondary (`#10b981` / Emerald Green):** Denotes verified deterministic runs, active agents, healthy telemetry, and secure pull requests.
- **Tertiary (`#8b5cf6` / Neural Violet):** Reserved for agent reasoning, LLM inference, memory allocation, and context windows.
- **Accent - Cyan (`#06b6d4`):** Used for pipeline flow stages, runtime execution, and branch pointers.
- **Accent - Amber (`#f59e0b`):** Warning states, flaky unit tests, and security review flags.
- **Surfaces & Borders:** 
  - Base canvas: `#09090b`
  - Container / Card background: `#0d0e12`
  - Elevated surfaces / Inset code boxes: `#13141b`
  - Structural strokes & Dividers: `#222430`
  - Text Primary: `#f4f4f5`
  - Text Muted: `#71717a`

## Typography

Typography prioritizes extreme legibility for high-density code reviews, telemetry logs, and multi-agent execution feeds:

- **Primary Interface Font (`Geist`):** Delivers clean neo-grotesque authority with optimized tabular digits and tight tracking for high-information density.
- **Monospace Font (`JetBrains Mono`):** Applied to code blocks, git hashes, pipeline IDs, latency gauges, agent states, and terminal readouts.
- **Hierarchy:** All micro-labels, section numbers (e.g., `01. Home`, `04. Session Detail`), and breadcrumbs are styled using uppercase `JetBrains Mono` with subtle letter spacing for an authenticated military-developer finish.

## Layout & Spacing

The layout utilizes a strict, data-dense **Fluid Grid System** tailored for mission-control workflows:

- **Desktop (1440px+):** 12-column adaptive layout with 240px persistent collapsible sidebar, `1rem` gutters, and `1.5rem` outer canvas padding.
- **Tablet / Split View (768px - 1439px):** 8-column layout with icon-rail navigation (64px width) and stacked execution panes.
- **Mobile (< 768px):** 4-column layout; telemetry panes and dual-agent diff viewers transition to full-width tabbed panels with `1rem` margins.
- **Spacing Rhythm:** Micro increments of `4px` (`0.25rem`) and `8px` (`0.5rem`) keep component padding tight, maximizing usable screen estate for code diffs, logs, and agent state graphs.

## Elevation & Depth

Visual depth is achieved through **Tonal Layering** and **Hairline Luminescence** rather than traditional drop shadows:

- **Base Layer (Canvas):** `#09090b` flat ground.
- **Layer 1 (Card & Module Shells):** `#0d0e12` surrounded by a crisp `1px` border of `#222430`.
- **Layer 2 (Terminal Views, Code Insets, Nested Agents):** `#13141b` with inner inset border `rgba(255, 255, 255, 0.03)`.
- **Neon Laser Accents:** Critical focus zones (such as active red team cards or running pipelines) incorporate a 1px top highlight or perimeter glow using `0 0 12px -2px rgba(239, 68, 68, 0.3)`.
- **Modals & Overlays:** Solid dark surfaces with backdrop blur (`backdrop-filter: blur(12px)`) at `rgba(9, 9, 11, 0.85)` with a structural border of `#222430`.

## Shapes

The interface uses a **Soft Tactical (`roundedness: 1`)** geometry:
- Standard buttons, badges, inputs, and tab items use `0.25rem` (4px).
- Content cards, modals, terminal containers, and agent cards use `rounded-lg` (`0.5rem` / 8px).
- Pipeline node dots, live status beacons, and user avatars retain a true circular profile (`rounded-full`).

## Components

### Buttons
- **Primary Action (Brand / Attack / Run):** `#ef4444` background with white text, font `JetBrains Mono` or `Geist` semi-bold, subtle top inner-bevel, and crimson hover glow.
- **Secondary / Ghost:** Transparent background, `1px solid #222430`, hover state `#13141b` with text brightening to `#ffffff`.
- **Icon Buttons:** Fixed 32x32px or 28x28px squares, center-aligned, hairline stroke borders.

### Telemetry Gauges & Progress Bars
- Dual-color segmented progress tracks using `#13141b` as the trough and `#222430` inner track.
- Filled indicators utilize functional accent fills: `#ef4444` (CPU/Load), `#8b5cf6` (Memory/VRAM), and `#10b981` (Storage/Verification).
- Accompanied by inline `JetBrains Mono` label readouts (`6.4 / 16 GB`, `22%`).

### Pipeline Stage Steppers
- Linear multi-step progress bar connected by 1px muted `#222430` links.
- Nodes represent discrete stages: `Recon`, `Plan`, `Build`, `Test`, `Attack`, `Repair`, `Verify`.
- Active nodes feature pulsing concentric rings and status pills (`In Progress`, `Pending`, `Verified`).

### Code Diffs & Terminal Containers
- Top titlebar containing filepath, language tag (`Python`), line counts, and copy/action toggles.
- Left-gutter line numbering in `#71717a`.
- Added lines highlighted with `rgba(16, 185, 129, 0.1)` and green line prefix.
- Subtracted/vulnerable lines highlighted with `rgba(239, 68, 68, 0.12)` and red line prefix.

### Status Chips & Badges
- Pill-shaped or soft-rect mini badges (`space-xs` vertical, `space-sm` horizontal).
- Background set to 10% opacity of the status color with full-saturation text and an optional pulsing 6px radial dot:
  - **Verified / Online:** `#10b981`
  - **Failed / Attack Detected:** `#ef4444`
  - **Running / Neural:** `#8b5cf6`
  - **Building / Processing:** `#06b6d4`

### Input Fields & Search Bars
- Background `#0d0e12` with `1px solid #222430`.
- Integrated monospace command prompt prefix (`> ` or search icon).
- Focus state activates an accent stroke of `#ef4444` with zero displacement.