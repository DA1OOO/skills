#!/usr/bin/env node

import { access, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { constants as fsConstants } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { basename, dirname, extname, join, resolve, sep } from "node:path";
import { pathToFileURL } from "node:url";

function usage() {
  console.log(`Usage:
  node render_exact_pdf.mjs --input page.html --output page.pdf [options]

Options:
  --width N                 Viewport/PDF width in CSS px (default: 1440)
  --viewport-height N       Browser viewport height in CSS px (default: 900)
  --timeout-ms N            Navigation/resource timeout (default: 120000)
  --chrome PATH             Chromium/Chrome executable path
  --no-embed-images         Leave remote <img> URLs untouched
  --keep-temp               Keep the embedded temporary HTML
  --help                    Show this message`);
}

function parseArgs(argv) {
  const options = {
    width: 1440,
    viewportHeight: 900,
    timeoutMs: 120000,
    embedImages: true,
    keepTemp: false,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const value = () => {
      const next = argv[index + 1];
      if (!next || next.startsWith("--")) throw new Error(`Missing value for ${arg}`);
      index += 1;
      return next;
    };
    if (arg === "--input") options.input = value();
    else if (arg === "--output") options.output = value();
    else if (arg === "--width") options.width = Number(value());
    else if (arg === "--viewport-height") options.viewportHeight = Number(value());
    else if (arg === "--timeout-ms") options.timeoutMs = Number(value());
    else if (arg === "--chrome") options.chrome = value();
    else if (arg === "--no-embed-images") options.embedImages = false;
    else if (arg === "--keep-temp") options.keepTemp = true;
    else if (arg === "--help" || arg === "-h") options.help = true;
    else throw new Error(`Unknown option: ${arg}`);
  }
  if (!options.help && (!options.input || !options.output)) {
    throw new Error("Both --input and --output are required");
  }
  for (const [label, number] of [["width", options.width], ["viewport-height", options.viewportHeight], ["timeout-ms", options.timeoutMs]]) {
    if (!Number.isFinite(number) || number <= 0) throw new Error(`Invalid --${label}: ${number}`);
  }
  return options;
}

async function isReadable(path) {
  try {
    await access(path, fsConstants.R_OK);
    return true;
  } catch {
    return false;
  }
}

async function loadChromium() {
  const errors = [];
  try {
    const module = await import("playwright");
    return module.chromium;
  } catch (error) {
    errors.push(error.message);
  }

  const runtimeRoot = resolve(dirname(process.execPath), "..");
  const candidates = [
    join(runtimeRoot, "node_modules", "playwright", "index.mjs"),
    join(homedir(), ".cache", "codex-runtimes", "codex-primary-runtime", "dependencies", "node", "node_modules", "playwright", "index.mjs"),
  ];
  for (const candidate of candidates) {
    if (!(await isReadable(candidate))) continue;
    try {
      const module = await import(pathToFileURL(candidate).href);
      return module.chromium;
    } catch (error) {
      errors.push(`${candidate}: ${error.message}`);
    }
  }
  throw new Error(`Playwright could not be loaded. Use the Codex bundled Node runtime or install playwright. ${errors.join(" | ")}`);
}

async function findChrome(explicitPath) {
  if (explicitPath) {
    const absolute = resolve(explicitPath);
    if (!(await isReadable(absolute))) throw new Error(`Browser executable is not readable: ${absolute}`);
    return absolute;
  }
  const candidates = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    join(process.env.PROGRAMFILES || "C:\\Program Files", "Google", "Chrome", "Application", "chrome.exe"),
  ];
  for (const candidate of candidates) {
    if (await isReadable(candidate)) return candidate;
  }
  return undefined;
}

function remoteImageUrls(html) {
  const urls = [];
  const pattern = /<img\b[^>]*?\bsrc\s*=\s*(["'])(https?:\/\/[^"']+)\1/gi;
  for (const match of html.matchAll(pattern)) urls.push(match[2]);
  return [...new Set(urls)];
}

const imageHeaders = {
  "user-agent": "Mozilla/5.0 AppleWebKit/537.36 Chrome/130 Safari/537.36",
  accept: "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
};

async function fetchWithTimeout(url, timeoutMs) {
  return fetch(url, {
    redirect: "follow",
    headers: imageHeaders,
    signal: AbortSignal.timeout(timeoutMs),
  });
}

async function fetchImage(url, timeoutMs) {
  const response = await fetchWithTimeout(url, Math.min(timeoutMs, 20000));
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const mime = (response.headers.get("content-type") || "").split(";")[0];
  if (!mime.startsWith("image/")) throw new Error(`Unexpected content type: ${mime}`);
  return response;
}

function preserveDocumentBase(html, input) {
  const documentUrl = pathToFileURL(input).href;
  const baseTagPattern = /<base\b[^>]*>/i;
  const baseTagMatch = html.match(baseTagPattern);
  if (baseTagMatch) {
    const hrefPattern = /\bhref\s*=\s*(?:(["'])(.*?)\1|([^\s>]+))/i;
    const hrefMatch = baseTagMatch[0].match(hrefPattern);
    if (hrefMatch) {
      const rawHref = (hrefMatch[2] ?? hrefMatch[3])
        .replace(/&amp;/gi, "&")
        .replace(/&quot;/gi, '"')
        .replace(/&#(?:39|x27);/gi, "'");
      const absoluteHref = new URL(rawHref, documentUrl).href
        .replaceAll("&", "&amp;")
        .replaceAll('"', "&quot;");
      const rewrittenTag = baseTagMatch[0].replace(hrefPattern, `href="${absoluteHref}"`);
      return html.replace(baseTagPattern, rewrittenTag);
    }
  }

  const directoryUrl = pathToFileURL(`${dirname(input)}${sep}`).href
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;");
  const baseTag = `<base href="${directoryUrl}">`;
  if (/<head\b[^>]*>/i.test(html)) {
    return html.replace(/<head\b[^>]*>/i, (head) => `${head}\n    ${baseTag}`);
  }
  if (/<html\b[^>]*>/i.test(html)) {
    return html.replace(/<html\b[^>]*>/i, (root) => `${root}\n  <head>${baseTag}</head>`);
  }
  return `${baseTag}\n${html}`;
}

async function embedImages(html, timeoutMs) {
  const urls = remoteImageUrls(html);
  const replacements = new Map();
  const failed = [];

  let cursor = 0;
  async function worker() {
    while (cursor < urls.length) {
      const url = urls[cursor];
      cursor += 1;
      try {
        const response = await fetchImage(url, timeoutMs);
        const bytes = Buffer.from(await response.arrayBuffer());
        const mime = (response.headers.get("content-type") || "image/jpeg").split(";")[0];
        replacements.set(url, `data:${mime};base64,${bytes.toString("base64")}`);
      } catch (error) {
        failed.push({ url, error: error.message });
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(6, Math.max(1, urls.length)) }, worker));

  let embeddedHtml = html.replace(/\bloading\s*=\s*(["'])lazy\1/gi, 'loading="eager"');
  for (const [url, dataUri] of replacements) embeddedHtml = embeddedHtml.replaceAll(url, dataUri);
  return { html: embeddedHtml, discovered: urls.length, embedded: replacements.size, failed };
}

async function main() {
  let options;
  try {
    options = parseArgs(process.argv.slice(2));
  } catch (error) {
    console.error(error.message);
    usage();
    process.exitCode = 2;
    return;
  }
  if (options.help) {
    usage();
    return;
  }

  const input = resolve(options.input);
  const output = resolve(options.output);
  if (extname(input).toLowerCase() !== ".html" && extname(input).toLowerCase() !== ".htm") {
    throw new Error(`Input must be an HTML file: ${input}`);
  }
  if (extname(output).toLowerCase() !== ".pdf") throw new Error(`Output must end in .pdf: ${output}`);
  if (!(await isReadable(input))) throw new Error(`Input is not readable: ${input}`);

  await mkdir(dirname(output), { recursive: true });
  const workDir = join(tmpdir(), `html-to-exact-pdf-${process.pid}-${Date.now()}`);
  await mkdir(workDir, { recursive: true });
  const tempHtml = join(workDir, `${basename(input, extname(input))}-embedded.html`);

  let imageStats = { discovered: 0, embedded: 0, failed: [] };
  let browser;
  try {
    const sourceHtml = await readFile(input, "utf8");
    let renderHtml = sourceHtml.replace(/\bloading\s*=\s*(["'])lazy\1/gi, 'loading="eager"');
    if (options.embedImages) {
      const result = await embedImages(sourceHtml, options.timeoutMs);
      renderHtml = result.html;
      imageStats = { discovered: result.discovered, embedded: result.embedded, failed: result.failed };
    }
    renderHtml = preserveDocumentBase(renderHtml, input);
    await writeFile(tempHtml, renderHtml, "utf8");

    const chromium = await loadChromium();
    const chromePath = await findChrome(options.chrome);
    browser = await chromium.launch({
      headless: true,
      ...(chromePath ? { executablePath: chromePath } : {}),
    });
    const page = await browser.newPage({
      viewport: { width: options.width, height: options.viewportHeight },
      deviceScaleFactor: 1,
    });
    page.setDefaultTimeout(options.timeoutMs);
    await page.emulateMedia({ media: "screen", colorScheme: "light", reducedMotion: "reduce" });
    await page.goto(pathToFileURL(tempHtml).href, { waitUntil: "load", timeout: options.timeoutMs });
    await page.locator("img").evaluateAll((images) => images.forEach((image) => { image.loading = "eager"; }));

    await page.evaluate(async (timeoutMs) => {
      const delay = (milliseconds) => new Promise((resolveWait) => setTimeout(resolveWait, milliseconds));
      for (let y = 0; y < document.documentElement.scrollHeight; y += 700) {
        window.scrollTo(0, y);
        await delay(35);
      }
      const imageWaits = Array.from(document.images).map((image) => image.complete
        ? Promise.resolve()
        : new Promise((resolveImage) => {
            image.addEventListener("load", resolveImage, { once: true });
            image.addEventListener("error", resolveImage, { once: true });
          }));
      await Promise.race([Promise.all(imageWaits), delay(Math.min(timeoutMs, 30000))]);
      if (document.fonts?.ready) await Promise.race([document.fonts.ready, delay(Math.min(timeoutMs, 15000))]);
      window.scrollTo(0, 0);
    }, options.timeoutMs);

    const frozenViewportDeclarations = await page.evaluate(() => {
      const hasViewportUnit = /(-?\d*\.?\d+)\s*(dvh|svh|lvh|vh|dvw|svw|lvw|vw|vmin|vmax)\b/i;
      const replaceViewportUnits = /(-?\d*\.?\d+)\s*(dvh|svh|lvh|vh|dvw|svw|lvw|vw|vmin|vmax)\b/gi;
      const resolveViewportUnits = (value) => value.replace(replaceViewportUnits, (_, raw, unit) => {
        const number = Number(raw);
        const width = window.innerWidth;
        const height = window.innerHeight;
        const ratios = {
          vh: height, dvh: height, svh: height, lvh: height,
          vw: width, dvw: width, svw: width, lvw: width,
          vmin: Math.min(width, height), vmax: Math.max(width, height),
        };
        return `${number * ratios[unit.toLowerCase()] / 100}px`;
      });
      const snapshots = [];
      const capture = (element, property, declaredValue) => {
        const computed = getComputedStyle(element).getPropertyValue(property).trim();
        const value = property.startsWith("--") ? resolveViewportUnits(declaredValue) : computed;
        if (value) snapshots.push([element, property, value]);
      };
      const visitRules = (rules) => {
        for (const rule of Array.from(rules || [])) {
          if (rule.type === CSSRule.STYLE_RULE) {
            const declarations = Array.from(rule.style).filter((property) => hasViewportUnit.test(rule.style.getPropertyValue(property)));
            if (!declarations.length) continue;
            let elements;
            try { elements = document.querySelectorAll(rule.selectorText); } catch { continue; }
            for (const element of elements) {
              for (const property of declarations) capture(element, property, rule.style.getPropertyValue(property));
            }
          } else if (rule.cssRules) {
            if (rule.type === CSSRule.MEDIA_RULE && !matchMedia(rule.conditionText).matches) continue;
            visitRules(rule.cssRules);
          }
        }
      };
      for (const sheet of Array.from(document.styleSheets)) {
        try { visitRules(sheet.cssRules); } catch {}
      }
      for (const element of document.querySelectorAll("[style]")) {
        for (const property of Array.from(element.style)) {
          const declared = element.style.getPropertyValue(property);
          if (hasViewportUnit.test(declared)) capture(element, property, declared);
        }
      }
      for (const [element, property, value] of snapshots) element.style.setProperty(property, value, "important");
      return snapshots.length;
    });

    await page.addStyleTag({ content: `
      html { scroll-behavior: auto !important; }
      *, *::before, *::after {
        animation-play-state: paused !important;
        caret-color: transparent !important;
      }
    ` });
    await page.evaluate(() => new Promise((resolveFrame) => requestAnimationFrame(() => requestAnimationFrame(resolveFrame))));

    const dimensions = await page.evaluate(() => ({
      width: Math.max(document.documentElement.scrollWidth, document.body?.scrollWidth || 0),
      height: Math.max(document.documentElement.scrollHeight, document.body?.scrollHeight || 0),
      failedImages: Array.from(document.images).filter((image) => !image.complete || image.naturalWidth === 0).map((image) => image.currentSrc || image.src),
    }));
    if (dimensions.width > options.width + 2) {
      console.warn(`Warning: document scroll width is ${dimensions.width}px, wider than the requested ${options.width}px PDF.`);
    }
    if (dimensions.height > 18500) {
      throw new Error(`Rendered height ${dimensions.height}px exceeds the safe continuous-page limit (18500px). Split the document or use a screenshot-backed PDF.`);
    }

    await page.pdf({
      path: output,
      width: `${options.width}px`,
      height: `${dimensions.height}px`,
      printBackground: true,
      preferCSSPageSize: false,
      displayHeaderFooter: false,
      margin: { top: 0, right: 0, bottom: 0, left: 0 },
    });

    console.log(JSON.stringify({
      output,
      width: options.width,
      height: dimensions.height,
      frozenViewportDeclarations,
      images: {
        discovered: imageStats.discovered,
        embedded: imageStats.embedded,
        embedFailures: imageStats.failed,
        renderFailures: dimensions.failedImages,
      },
      temporaryHtml: options.keepTemp ? tempHtml : undefined,
    }, null, 2));
  } finally {
    if (browser) await browser.close();
    if (!options.keepTemp) await rm(workDir, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exitCode = 1;
});
