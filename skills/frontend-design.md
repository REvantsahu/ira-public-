# Frontend Design
description: Create distinctive, production-grade frontend interfaces — websites, landing pages, dashboards, components
when_to_use: User asks to build web UI — HTML/CSS/JS, React, landing pages, components, or beautify any frontend

## Instructions
### Design Thinking First
Before coding, commit to a BOLD aesthetic direction:
- Purpose: what problem does this solve? Who uses it?
- Tone: pick an extreme — minimal, maximalist, retro, organic, luxury, playful, brutalist, editorial
- Differentiation: what makes it unforgettable?

### Aesthetic Guidelines
- **Typography**: Use distinctive fonts. Never default to Inter/Roboto/Arial. Pair a display font with a refined body font.
- **Color**: Commit to a cohesive palette. Dominant color (60-70%) with sharp accents. CSS variables for consistency.
- **Motion**: CSS animations for micro-interactions. Staggered reveals on load. Scroll-triggered + hover states.
- **Layout**: Unexpected compositions — asymmetry, overlap, grid-breaking elements, generous negative space.
- **Details**: Gradient meshes, noise textures, geometric patterns, layered transparencies, custom cursors.

### NEVER Use (AI Slop)
- Inter, Roboto, Arial, system-ui as default fonts
- Purple gradients on white backgrounds
- Same layout repeated across sections
- Accent lines under titles (generic)
- Cream/beige backgrounds (`#F5F5DC`, `#FAF0E6`) unless intentional
- Space Grotesk in every project (vary your choices)

### Revant's Brand Palette
| Site | Primary | BG | Fonts |
|------|---------|----|-------|
| Edlix AI | `#6d28d9` violet | `#060610` | Outfit + Space Grotesk |
| Nagchetra Labs | `#FF6A00` orange | `#0B0B0B` | Orbitron + Rajdhani |
| Nagchetra Classes | `#FF6A00` orange | black | Orbitron + Rajdhani |
| Profilo | `#00f2ff` cyan | `#03050c` | Orbitron + Poppins |

### Implementation
Write production-grade code. Match complexity to the vision — maximalist = elaborate code, minimalist = precision and restraint.

## Examples
- User: "make a landing page for my startup" → HTML/CSS/JS with distinctive design
- User: "build a dashboard" → component-based UI with cohesive aesthetic
