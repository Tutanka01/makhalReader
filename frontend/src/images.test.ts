import { describe, expect, it } from 'vitest'
import { isChromeImage, pickHeroImage } from './images'

describe('isChromeImage', () => {
  it('flags theme assets, svg logos, icons and avatars', () => {
    expect(
      isChromeImage(
        'https://developer-blogs.nvidia.com/wp-content/themes/nvidia/dist/images/nvidia-logo_28b633c7.svg',
      ),
    ).toBe(true)
    expect(isChromeImage('https://site.com/assets/favicon.ico')).toBe(true)
    expect(isChromeImage('https://site.com/img/rss-icon.png')).toBe(true)
    expect(isChromeImage('https://secure.gravatar.com/avatar/abc.png')).toBe(true)
  })

  it('passes real illustrations even when the name contains a substring', () => {
    expect(isChromeImage('https://site.com/uploads/silicon-photonics.jpg')).toBe(false)
    expect(
      isChromeImage('https://developer-blogs.nvidia.com/wp-content/uploads/2026/06/AI-Inference-1024x576.jpg'),
    ).toBe(false)
  })
})

describe('pickHeroImage', () => {
  it('skips the logo and returns the first real image', () => {
    const images = [
      'https://developer-blogs.nvidia.com/wp-content/themes/nvidia/dist/images/nvidia-logo_28b633c7.svg',
      'https://developer-blogs.nvidia.com/wp-content/uploads/2026/06/AI-Inference-1024x576.jpg',
    ]
    expect(pickHeroImage(images)).toBe(images[1])
  })

  it('skips an image already present in the article body', () => {
    const hero = 'https://site.com/uploads/figure-1.webp'
    const html = `<p>x</p><img src="${hero}">`
    expect(pickHeroImage([hero], html)).toBeNull()
  })

  it('returns null when there are no content images', () => {
    expect(pickHeroImage([])).toBeNull()
    expect(pickHeroImage(null)).toBeNull()
    expect(pickHeroImage(['https://site.com/favicon.ico'])).toBeNull()
  })
})
