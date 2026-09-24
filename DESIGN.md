# Rewind design system

## Direction
A personal record shelf. Restrained product UI with a dark green navigation rail, neutral near-white content, decade sleeves, serif editorial headline, and a persistent stereo-like player. Desktop browsing becomes horizontal navigation on tablet; phone layouts simplify track columns and use system volume.

## Palette
All CSS colors use OKLCH. Primary hue is 150 degrees: `oklch(.34 .065 150)`. Background is neutral `oklch(.979 0 0)`, surfaces white, primary ink `oklch(.24 .015 150)`, secondary ink `oklch(.47 .015 150)`. Pastel green, apricot and lavender distinguish the three decades. Color supplements labeled selected states, never replaces them.

## Typography
Arial/system sans for controls and song metadata; Georgia for the main title, decade numerals and the record sleeve. Fixed, responsive type sizes. Long song titles truncate visually while keeping the full text in their accessible name and title attribute.

## Components
Six-pixel button radii, 7–10px panels, no external fonts or imagery. Header search, compact navigation, inline upload, native edit and delete dialogs, semantic track articles and native HTML audio. Icon controls all have text labels for assistive technology. Native focus behavior and visible focus rings. Motion limited to hover/press feedback and upload scrolling; reduced-motion is honored.

## Layout
Wide: 224px sidebar plus flexible main content. Below 1100px: 190px rail. At 820px navigation moves above content and the player recomposes. At 560px track metadata and volume simplify. At 370px illustration is omitted and filter tools use a separate row. Body and player accommodate safe-area insets.

## Admin controls
Guest header shows Admin login. Admin session reveals Add music, editing controls and Sign out. Login uses a labeled native dialog. Signed-in phone header places search on its own row. Upload and destructive management are also protected by the backend.

## Listening categories
Ghazal, Travel and Party appear as three horizontally aligned choices beneath decade browsing. At phone widths they stack as full-width touch rows. Active selection is expressed through a tinted surface and aria-pressed. Upload and edit forms expose the same category vocabulary.
