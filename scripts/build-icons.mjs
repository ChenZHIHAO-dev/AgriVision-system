// Generate only the icons AgriVision uses. PNG assets also work in packaged mini-programs.
import { readFile, writeFile, mkdir, copyFile } from 'node:fs/promises'
import { Resvg } from '@resvg/resvg-js'
const icons = {
  home: 'house', camera: 'camera', chat: 'message-square', history: 'history',
  book: 'book-open', user: 'user-round', settings: 'settings-2', info: 'info',
  close: 'x', back: 'arrow-left', chevron: 'chevron-down', right: 'chevron-right',
  plus: 'plus', check: 'check', search: 'search', upload: 'images', image: 'image',
  file: 'file-text', trash: 'trash-2', leaf: 'sprout', location: 'map-pin',
  arrow: 'arrow-up', zoom: 'scan-search', menu: 'menu', collapse: 'panel-left-close',
  sun: 'sun', moon: 'moon', system: 'contrast', logout: 'log-out',
  new: 'square-pen', grid: 'layout-grid', list: 'list', external: 'arrow-up-right',
  thinking: 'brain', shield: 'shield-check', copy: 'copy',
}
const colors = { light: '#4a5561', dark: '#d3d7de', white: '#ffffff', inverse: '#202126' }
const target = new URL('../apps/client/src/static/icons/ui/', import.meta.url)
await mkdir(target, { recursive: true })
for (const [name, source] of Object.entries(icons)) {
  const svg = await readFile(new URL('../node_modules/lucide-static/icons/' + source + '.svg', import.meta.url), 'utf8')
  for (const [tone, color] of Object.entries(colors)) {
    const painted = svg.replaceAll('currentColor', color).replace(/stroke-width="[^"]+"/, 'stroke-width="2.2"')
    const buffer = new Resvg(painted, { fitTo: { mode: 'width', value: 96 } }).render().asPng()
    await writeFile(new URL(name + '-' + tone + '.png', target), buffer)
  }
}
await mkdir(new URL('../licenses/', import.meta.url), { recursive: true })
await copyFile(new URL('../node_modules/lucide-static/LICENSE', import.meta.url), new URL('../licenses/lucide-LICENSE', import.meta.url))
console.log('Generated ' + Object.keys(icons).length + ' icons in four explicit color variants.')
