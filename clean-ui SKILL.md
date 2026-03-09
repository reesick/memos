---
name: clean-ui
description: Design and build clean, functional, minimal UI interfaces inspired by developer/research tools — light gray backgrounds, subtle borders, no gradients, no neon colors, no decorative fluff. Use this skill whenever the user asks for a "clean UI", "minimal design", "no neon", "supermemory style", "developer tool aesthetic", "research tool interface", or explicitly says they hate flashy AI design. Also use when building dashboards, data tools, memory interfaces, conversation UIs, panels, or any app where clarity and information density matter more than visual drama.
---

# Clean UI Design Skill

This skill builds clean, functional interfaces that look like real developer/research tools — not AI-generated portfolio pieces. Think Supermemory, Linear, Notion, Raycast, or Vercel's dashboard. Clarity over decoration.

## Core Aesthetic Principles

**This design system has ONE goal: make information easy to read and act on.**

### Color System
Use a tight palette with almost no variation:

```css
--bg:          #f5f5f5   /* page background — light gray, not white */
--surface:     #ffffff   /* cards, panels */
--surface-2:   #f9f9f9   /* nested surfaces, hover states */
--border:      #e5e5e5   /* all borders — consistent, subtle */
--border-dark: #d0d0d0   /* dividers, stronger separators */
--text-primary:   #111111  /* headings, important labels */
--text-secondary: #555555  /* body text, descriptions */
--text-muted:     #999999  /* timestamps, metadata, placeholders */
--accent:      #16a34a   /* ONE accent — green (like status indicators) */
--accent-soft: #dcfce7   /* light accent for backgrounds */
--danger:      #ef4444   /* destructive actions only */
```

**NEVER USE:**
- Purple, pink, teal, orange, or any gradient combinations
- `box-shadow` with color — only `rgba(0,0,0,0.06)` max
- Glassmorphism, blur effects, backdrop-filter
- Neon or high-saturation colors of any kind
- Dark mode unless explicitly requested

### Typography
Pick one clean, readable font — NOT Inter, NOT Roboto.

Good choices:
- `Geist` (Vercel's font — clean, technical)
- `IBM Plex Mono` or `IBM Plex Sans` (research tool feel)
- `DM Sans` (neutral, clean)
- `Instrument Sans` (subtle character)

Font scale — keep it tight:
```css
--text-xs:   11px  /* labels, tags, metadata */
--text-sm:   12px  /* secondary content, timestamps */
--text-base: 13px  /* body text */
--text-md:   14px  /* default UI text */
--text-lg:   16px  /* section headers */
--text-xl:   20px  /* page titles */
```

Weights: 400 (body), 500 (labels), 600 (headings). Never 700+ in UI.

Letter spacing: `0.01em` on labels and small caps. `normal` everywhere else.

### Spacing System
Everything on an 8px grid. Be generous — whitespace is the design.

```
4px   — icon padding, tag gaps
8px   — tight component padding
12px  — card inner padding (top/bottom)
16px  — standard padding
24px  — section gaps
32px  — panel gaps
48px  — page-level breathing room
```

### Components

#### Cards / Panels
```css
.card {
  background: #ffffff;
  border: 1px solid #e5e5e5;
  border-radius: 8px;
  padding: 12px 16px;
}

.card:hover {
  background: #f9f9f9;
}
```
No shadow on cards. Border only. Hover = background shift, not lift.

#### Buttons
```css
/* Primary */
.btn-primary {
  background: #111111;
  color: #ffffff;
  border: none;
  border-radius: 6px;
  padding: 7px 14px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
}

/* Secondary */
.btn-secondary {
  background: transparent;
  color: #111111;
  border: 1px solid #e5e5e5;
  border-radius: 6px;
  padding: 6px 14px;
  font-size: 13px;
  cursor: pointer;
}

/* Danger */
.btn-danger {
  border: 1px solid #ef4444;
  color: #ef4444;
  background: transparent;
}
```

No gradient buttons. No pill buttons unless it's a tag/badge.

#### Labels / Section Headers
```css
.label {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #999999;
}
```

Used for panel titles like "MEMORIES", "CONTEXT", "PROFILE", "SESSION".

#### Input / Search
```css
.input {
  background: #ffffff;
  border: 1px solid #e5e5e5;
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 13px;
  color: #111111;
  outline: none;
  width: 100%;
}

.input:focus {
  border-color: #d0d0d0;
}
```

No colored focus rings. No box shadows on focus.

#### Status Indicators
```css
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #16a34a;  /* green = active/live */
  display: inline-block;
}

/* Pulse for "recording" or "live" state */
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
.dot-live { animation: pulse 2s ease-in-out infinite; }
```

#### Tags / Badges
```css
.tag {
  background: #f5f5f5;
  border: 1px solid #e5e5e5;
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 11px;
  color: #555555;
}
```

#### Dividers
```css
hr {
  border: none;
  border-top: 1px solid #e5e5e5;
  margin: 0;
}
```

No fancy dividers. Plain 1px lines.

## Layout Patterns

### Multi-Panel Layout (like Supermemory)
```
[Left: Conversation / Main Content] [Middle: Data / List] [Right: Meta / Profile]
        ~35%                              ~40%                    ~25%
```

Use `display: grid; grid-template-columns: ...` not flexbox for multi-panel.

Each panel:
- Separated by a 1px `#e5e5e5` border-right
- Full height: `height: 100vh; overflow-y: auto`
- Own internal scroll

### Top Bar
```css
.topbar {
  height: 48px;
  border-bottom: 1px solid #e5e5e5;
  display: flex;
  align-items: center;
  padding: 0 16px;
  gap: 16px;
  background: #ffffff;
}
```

Clean, flat, no shadow. Logo left. Tabs or actions right.

### Chat Bubbles (conversation UIs)
```css
/* User message */
.msg-user {
  background: #f5f5f5;
  border: 1px solid #e5e5e5;
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 13px;
  max-width: 280px;
  align-self: flex-end;
}

/* AI message */
.msg-ai {
  background: #ffffff;
  border: 1px solid #e5e5e5;
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 13px;
  max-width: 380px;
}

/* Small speaker label above bubble */
.msg-label {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #999999;
  margin-bottom: 3px;
}
```

## Animations

Keep them minimal and functional:
- No entrance animations on cards or panels
- Hover transitions: `transition: background 0.1s ease` — fast, subtle
- Pulse on live indicators only
- Loading states: simple opacity fade, no spinners with color

```css
.fade-in {
  animation: fadeIn 0.2s ease;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(4px); }
  to   { opacity: 1; transform: translateY(0); }
}
```

## What To Avoid (Non-Negotiable)

- ❌ Gradient backgrounds
- ❌ box-shadow with color tints (purple glow, blue halo, etc.)
- ❌ Neon, electric blue, hot pink, or any fluorescent color
- ❌ Glassmorphism (backdrop-filter: blur)
- ❌ Border radius > 12px on panels, > 8px on cards
- ❌ Font sizes above 20px for anything except a hero title
- ❌ Bold > 600 weight in UI labels
- ❌ Colored section backgrounds (keep them white or #f9f9f9 max)
- ❌ Animations longer than 300ms
- ❌ Icon libraries with thick/chunky icons — use Lucide or Heroicons (stroke width 1.5)
- ❌ Emoji in UI labels or buttons
- ❌ Centered-alignment for multi-line body text

## Reference Apps to Emulate

Study these when in doubt:
- **Supermemory** — panel layout, memory cards, status dots
- **Linear** — typography density, muted colors, keyboard-first
- **Raycast** — monospace accents, minimal chrome
- **Vercel Dashboard** — data tables, status indicators
- **Notion** — whitespace, hierarchy without decoration

## Implementation Notes

When building in React:
- Use Tailwind utility classes that match this system (`gray-100`, `gray-200`, `gray-500`, `green-600`)
- Map to: `bg-gray-100` = `#f5f5f5`, `border-gray-200` = `#e5e5e5`
- For text: `text-gray-900` (primary), `text-gray-500` (secondary), `text-gray-400` (muted)
- Accent: `text-green-600`, `bg-green-50`

When building in plain HTML/CSS:
- Use CSS custom properties from the Color System above
- Single stylesheet, no frameworks needed for simple UIs

Always test: does it look like a tool a developer would actually use, or does it look like an AI made a "beautiful dashboard"? If the latter — strip it down.