# UI design notes

## Idea
The product reads annual reports, so the interface behaves like a **research note with footnotes**, not a chat window.
An answer is typeset text with numbered sources; clicking a source opens the actual passage beside it, with the figures
that appear in the answer highlighted.

## Layout
- Left rail: history grouped by day, library link, theme switch.
- Centre: the question as a headline, then the answer, verification badge, sources list, "how this was answered".
- Right (opens on demand): evidence pane. A drawer on mobile.
- URL-driven: `/` is a new question, `/:id` a saved thread, `/library` the reports.

## Colour (cream "paper" / blue-black "ink", switchable, follows the system by default)
| Token | Light | Dark |
|---|---|---|
| bg / surface / raised | `#F6F3EC` / `#FBF9F4` / `#FFFFFF` | `#0E1218` / `#131923` / `#1A2230` |
| ink / muted | `#1B1A17` / `#6B675D` | `#E8E5DA` / `#9AA3B0` |
| primary (ink navy) | `#1F3A5F` | `#8DB3EA` |
| accent (saffron, citations and highlights only) | `#C97A12` (text `#8A4F06`) | `#F2A33A` |
| danger | `#B84A32` | `#E07A5F` |

Tokens are CSS variables in `src/index.css`; Tailwind maps to them, so a theme change is one attribute on `<html>`.
An inline script in `index.html` sets the theme before first paint (no flash).

## Type
Newsreader (serif) for questions and answers, IBM Plex Sans for UI, IBM Plex Mono with tabular figures for numbers so
columns line up like a financial statement. Fonts are bundled via fontsource (no external requests).

## States and details
- Loading: a live ticker ("Searching the reports…", elapsed time, completed steps) over a skeleton shaped like the answer.
- Skeletons for the history rail, saved threads, library and coverage grid.
- Error states with retry (including "model unavailable"); Stop button aborts a streaming answer.
- "Figures verified" badge comes from the backend verification step, never from the UI guessing.
- Empty state shows a company × year coverage grid and questions built from the reports actually loaded.
- Keyboard: Enter send, Shift+Enter newline, Ctrl/Cmd+K new question, Esc closes the evidence pane.
- Accessibility: labelled controls, radio-group semantics for theme and mode, focus rings, live regions for status,
  reduced-motion respected, contrast checked for both themes.
- Responsive: rail becomes a drawer, evidence becomes a sheet.

## Swapping the palette
All colours live in `src/index.css`. Change `--primary`, `--primary-soft` (and the dark equivalents) to re-theme. Ready-made options:

| Name | Light primary / soft | Dark primary / soft |
|---|---|---|
| Navy (current) | `#1F3A5F` / `#E5EBF3` | `#8DB3EA` / `#172840` |
| Oxblood | `#7A2E34` / `#F3E4E4` | `#E49A9F` / `#3A1A1D` |
| Teal | `#0E5E6F` / `#DFEEF1` | `#6CC3D5` / `#12303A` |
| Ink green (previous) | `#0F5B4A` / `#E3EFEA` | `#5FB89A` / `#17302A` |
