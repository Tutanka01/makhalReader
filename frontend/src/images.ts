// Hero-image selection for the reader.
//
// Older articles were ingested before the extractor learned to skip site
// chrome, so `article.images[0]` can be a logo, favicon, or UI icon (e.g. the
// NVIDIA developer-blog SVG logo). This filters those out at render time and
// avoids showing a hero that already appears inside the article body.

const CHROME_IMAGE_RE =
  /(?:^|[/_\-.])(logos?|icons?|favicons?|avatars?|gravatar|sprites?|emojis?|badges?|spacer|pixel|placeholder)(?=[/_\-.@]|$)/i

function pathOf(url: string): string {
  try {
    return new URL(url, 'https://x.invalid').pathname.toLowerCase()
  } catch {
    return url.toLowerCase()
  }
}

/** True for images that are site chrome (logo/icon/theme asset) rather than content. */
export function isChromeImage(url: string): boolean {
  const path = pathOf(url)
  if (path.includes('/themes/')) return true
  if (path.endsWith('.svg')) return true
  return CHROME_IMAGE_RE.test(path)
}

/**
 * Pick a hero image worth showing, or null.
 * Skips chrome images and any image already embedded in the article HTML
 * (so we don't render the same figure twice).
 */
export function pickHeroImage(
  images: string[] | undefined | null,
  contentHtml?: string | null,
): string | null {
  if (!images) return null
  for (const url of images) {
    if (!url || isChromeImage(url)) continue
    if (contentHtml && contentHtml.includes(url)) continue
    return url
  }
  return null
}
