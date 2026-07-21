---
name: html-to-exact-pdf
description: Convert a local HTML page into a visually faithful PDF by rendering it with Chromium using screen media, preserving backgrounds and images, freezing viewport-relative CSS, and matching the PDF page to the full rendered document. Use when a user asks for HTML-to-PDF conversion that should look like the browser page rather than a conventional paginated printout, especially for travel guides, portfolios, reports, landing pages, or long-form designed web pages.
---

# HTML to Exact PDF

Render a local HTML file as a continuous long-page PDF while preserving its browser appearance. Always render-check the result before delivery.

## Workflow

1. Resolve the input HTML and desired output PDF to absolute paths.
2. Inspect the HTML for remote images, lazy loading, print-only CSS, viewport units, fixed elements, and animations.
3. Locate the bundled Node.js runtime and Playwright. In Codex desktop, call `codex_app__load_workspace_dependencies` first; otherwise use an available Node.js installation that can import Playwright.
4. Run `scripts/render_exact_pdf.mjs` with the bundled Node executable:

   ```bash
   /absolute/path/to/node scripts/render_exact_pdf.mjs \
     --input /absolute/path/to/page.html \
     --output /absolute/path/to/page.pdf \
     --width 1440 \
     --viewport-height 900
   ```

5. Run `scripts/verify_pdf.py` to inspect page count, dimensions, and produce a preview PNG:

   ```bash
   python3 scripts/verify_pdf.py \
     --input /absolute/path/to/page.pdf \
     --preview /absolute/path/to/page-preview.png
   ```

6. Open the preview with an image-viewing tool. Check the top, middle, and bottom for missing images, blank bands, clipped sections, unexpected page headers, excessive whitespace, stretched `vh` sections, and font substitution.
7. Iterate until the PDF is visually faithful. Deliver the PDF and keep temporary embedded HTML only when it helps debugging.

## Renderer Behavior

The renderer:

- uses Chromium with `screen` media instead of print media;
- loads lazy images by scrolling through the page;
- embeds HTTP(S) `<img>` sources as data URIs when possible without sending URLs to a third-party proxy;
- preserves the original document base URL so relative CSS, images, fonts, and scripts keep working from the temporary HTML;
- freezes active `vh`, `vw`, `vmin`, and `vmax` declarations at their browser-computed sizes before PDF layout;
- disables animations and smooth scrolling for deterministic output;
- creates a zero-margin PDF whose width matches the requested viewport and whose height matches the full document;
- omits browser-added headers, footers, dates, URLs, and page numbers.

## Options

Use `--no-embed-images` when all resources are local or embedding is undesirable. Use `--chrome /absolute/path/to/browser` to select a browser. Use `--keep-temp` to retain the generated embedded HTML. Use `--timeout-ms` for slow pages. Run the renderer with `--help` for the complete option list.

The default width is `1440` CSS pixels and the default viewport height is `900` CSS pixels. Match the width to the page's intended desktop breakpoint. A different viewport height changes `vh`-based design, so preserve the height used when the HTML was reviewed in-browser.

## Quality Rules

- Do not use the browser's ordinary **Print → Save as PDF** result as the final artifact when the user asks for the original web appearance.
- Do not silently accept failed remote images. Report how many images were discovered, embedded, and still failed.
- Do not add site-specific CSS overrides unless visual verification proves they are needed. Put any necessary override in a copied working HTML file, not the user's original, unless the user asked to edit it.
- Do not overwrite the source HTML.
- Treat one continuous PDF page as intentional. If the rendered height exceeds Chromium's practical page limit, ask whether to split into multiple pages or produce a screenshot-backed PDF.
- Verify the final PDF, not only the HTML.

## Troubleshooting

- **Hero section becomes extremely tall:** rerun at the intended `--viewport-height`; verify that the renderer reports frozen viewport-unit declarations.
- **Images are blank:** rerun with network access, inspect failed URLs, or replace them with local copies. Keep `--no-embed-images` off.
- **External fonts differ:** download and reference local font files or wait for `document.fonts.ready`; the renderer already waits for fonts but cannot embed a blocked font response.
- **Repeated navigation or fixed buttons:** add a narrowly scoped override to the working HTML that changes the specific element from `position: fixed` before rendering.
- **PDF unexpectedly has multiple pages:** inspect its height with the verifier. The document may exceed Chromium's maximum custom page size.

## Included Scripts

- `scripts/render_exact_pdf.mjs`: deterministic Chromium renderer and remote-image embedder.
- `scripts/verify_pdf.py`: PDF metadata check and low-resolution full-page preview renderer.
