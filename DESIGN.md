# Design System

**Register:** product (the design serves a developer tool; it is not the product).

**Scene:** a developer at a desk, mid-afternoon, reading results and scores to
judge whether semantic search is behaving. Calm, legible, information-dense.
Light-first; dark available.

## Intent

Sharp and technical (Vercel / Render lineage): tight spacing rhythm, real
hierarchy through weight and scale, one accent. No decorative gradients, no
glassmorphism, no side-stripe accents. Results and scores are the interface;
chrome stays quiet.

## Tokens (starter — refine with `/impeccable`)

Light is the default theme; dark mirrors it via `[data-theme="dark"]`.

| Role | Light | Dark |
|------|-------|------|
| `--bg` | `#ffffff` | `#0b0d12` |
| `--surface` | `#ffffff` | `#12151c` |
| `--surface-2` | `#f6f7f9` | `#1a1e27` |
| `--border` | `#e5e7eb` | `#262b36` |
| `--text` | `#0f1115` | `#e8eaed` |
| `--text-muted` | `#5b6470` | `#9aa3b2` |
| `--text-sub` | `#8b93a1` | `#6b7280` |
| `--blue` (accent) | `#2563eb` | `#3b82f6` |
| `--green` | `#16a34a` | `#22c55e` |
| `--red` | `#dc2626` | `#ef4444` |

## Typography

- One sans family in multiple weights (system stack is fine to start).
- Mono for scores, vector dimensions, and ids.
- Hierarchy through scale + weight contrast (≥1.25 step ratio), not many families.

## Notes

Starter system. The token values above are placeholders chosen to match the
operator's other projects; run `/impeccable init` then `/impeccable critique`
on the first real screen to lock the system in.
