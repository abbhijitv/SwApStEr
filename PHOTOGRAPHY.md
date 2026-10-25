# Marketplace photography update

This update changes only local image assets, image selection, presentation styles, and visual tests. The existing housing work and all backend changes already present in the workspace are preserved.

## Images and attribution

16 locally stored WebP photographs replace the calculator, book, electronics, drafting, and housing illustrations:

- Calculators: `calculator-ti84.webp`, `calculator-ti84-red.webp`, `calculator-nspire.webp`, `calculator-nspire-cx.webp`.
- Study materials: `books-study.webp`, `books-open.webp`.
- Electronics: `electronics-breadboard.webp`, `electronics-sensors.webp`.
- Drafting: `drafting-tools.webp`, `drafting-compass.webp`.
- Housing: `housing-living.webp`, `housing-kitchen.webp`, `housing-bedroom.webp`, `housing-bedroom-desk.webp`, `housing-room.webp`, `housing-room-simple.webp`.

Assets live in `frontend/public/images/marketplace/`. Wikimedia Commons photos retain their individual CC BY or CC BY-SA licenses. Housing photos use the Pexels License. Exact original pages, photographers, license links, and adaptation notes appear in [LICENSES.md](frontend/public/images/marketplace/LICENSES.md) and `sources.json`. Each visible **Illustrative photo** label links directly to that image's entry in the public `credits.html` page.

The complete optimized set is approximately **731 KB**, with the largest photo approximately **101 KB**. Source files are resized, orientation-corrected, metadata-stripped, and encoded to WebP. Portrait calculators and instruments are padded to preserve the whole object; the resulting landscape assets use `object-fit: cover` in consistently sized containers. Original full-resolution downloads are not shipped.

## Selection and display

`frontend/app/listing-photo.tsx` centralizes mapping. The category and housing subtype select a relevant pool; TI-Nspire titles select their own calculator pool. Persisted listing IDs deterministically select variants, so sorting and refreshes never randomize images. Apartment subleases, private rooms, and room rentals use separate housing pools.

The reusable component appears on cards, listing details, and negotiation summaries. Next.js Image supplies responsive sources, lazy loading, and asynchronous decoding. The container reserves space before load, with a neutral placeholder, brief fade, subtle hover zoom, and reduced-motion support. Failed loads and unsupported categories show a category-appropriate neutral fallback without retry loops.

There is no upload infrastructure to prioritize in the current API. Generic photographs are deliberately labeled illustrative; they do not verify the actual item, textbook edition, calculator variant, furnishings, location, or student property. The two general study photos do not assert a specific calculus or physics edition. A finite photo library means listings in the same category may share an image.

## Files changed by this task

- `frontend/app/listing-photo.tsx` — reusable mapping, images, stock disclosure, and failure handling.
- `frontend/app/page.tsx` — replace the old illustration component at its three presentation locations.
- `frontend/app/globals.css` — image sizing, captions, loading, hover, and mobile styles.
- `frontend/public/images/marketplace/` — 16 WebP files plus `LICENSES.md`, `sources.json`, and `credits.html`.
- `frontend/tests/photography.spec.ts` — read-only fixture-based visual and approval-control regression checks.
- `frontend/next-env.d.ts` — regenerated production type references from Next.js build.
- `PHOTOGRAPHY.md` — this report.

No backend code, pricing, listing ownership, API contracts, agent decisions, validation, or approval logic is changed by this task. Visual browser tests intercept all API traffic; backend tests use their existing isolated temporary database.

## Screenshots

Screenshots are local artifacts (not committed):

- `artifacts/photography/before-desktop.png`
- `artifacts/photography/before-mobile.png`
- `artifacts/photography/after-desktop.png`
- `artifacts/photography/after-housing-desktop.png`
- `artifacts/photography/after-housing-mobile.png`

The before screenshots show the existing marketplace. The automated after screenshots use representative API fixtures so all photo types can be reviewed without adding live listings.

## Verification commands

```sh
npm run typecheck --prefix frontend
npm run build --prefix frontend
# Serve the completed build before running browser checks:
npm run start --prefix frontend
npm run test:e2e --prefix frontend -- tests/photography.spec.ts
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q
```

No deployment, Git push, new dependency, image-service integration, or API key is required.

## Verification results

- TypeScript check and final production build: passed.
- Existing backend regression suite: **126 passed** in its temporary test database.
- Three focused Chrome checks cover all 16 image sources, deterministic refresh behavior, desktop/mobile layout, failed-image fallback, detail imagery, and independent approval controls using intercepted API fixtures.
- All backend Python file hashes match the start-of-task baseline. All pre-existing listings remain byte-for-byte unchanged; no original records were removed, and SQLite integrity is OK.
- The live application remained active during this task: a pre-existing Ollama negotiation progressed and subsequent live negotiation/session activity appeared. Those records were left intact. The verification suite itself does not send writes to the live backend.
- Initial browser checks revealed a broad selector that also matched SVG icons, and stale JavaScript while a build was replacing a running server's assets. The selector was narrowed and the final build served from a restarted server before the clean rerun.
- Final restarted-production Chrome rerun: **3 passed, 0 failed**. All 16 photos loaded and stayed stable after refresh; no mobile horizontal overflow was detected. Final photo assets total approximately **731 KB**.
