import MarkdownIt from 'markdown-it'
const markdown = new MarkdownIt({ html: false, breaks: true, linkify: false, typographer: false })
markdown.validateLink = (url) => /^https?:\/\//i.test(url)
const styles: Record<string, string> = {
  p: 'margin:0 0 13px;line-height:1.95;',
  h1: 'font-size:17px;font-weight:650;margin:20px 0 10px;',
  h2: 'font-size:16px;font-weight:650;margin:20px 0 10px;',
  h3: 'font-size:15px;font-weight:650;margin:18px 0 9px;',
  ul: 'padding-left:23px;margin:8px 0 15px;',
  ol: 'padding-left:23px;margin:8px 0 15px;',
  li: 'margin:5px 0;',
  blockquote: 'margin:14px 0;padding:9px 14px;border-left:3px solid var(--line);',
}
for (const rule of [
  'paragraph_open',
  'heading_open',
  'bullet_list_open',
  'ordered_list_open',
  'list_item_open',
  'blockquote_open',
  'strong_open',
  'th_open',
  'td_open',
]) {
  markdown.renderer.rules[rule] = (tokens, index, options, _env, renderer) => {
    const token = tokens[index]
    token.attrJoin('class', 'md-' + token.tag)
    if (styles[token.tag]) token.attrJoin('style', styles[token.tag])
    return renderer.renderToken(tokens, index, options)
  }
}
markdown.renderer.rules.link_open = (tokens, index, options, _env, renderer) => {
  tokens[index].attrSet('target', '_blank')
  tokens[index].attrSet('rel', 'noopener noreferrer')
  tokens[index].attrJoin('class', 'md-a')
  return renderer.renderToken(tokens, index, options)
}
markdown.renderer.rules.image = (tokens, index) =>
  '<span class="md-image-note">[图片：' +
  markdown.utils.escapeHtml(tokens[index].content) +
  ']</span>'
markdown.renderer.rules.table_open = () => '<div class="md-table-wrap"><table class="md-table">'
markdown.renderer.rules.table_close = () => '</table></div>'
markdown.renderer.rules.code_inline = (tokens, index) =>
  '<code class="md-code">' + markdown.utils.escapeHtml(tokens[index].content) + '</code>'
const fence = markdown.renderer.rules.fence!
markdown.renderer.rules.fence = (tokens, index, options, env, renderer) =>
  fence(tokens, index, options, env, renderer)
    .replace(
      '<pre>',
      '<pre class="md-pre" style="white-space:pre;overflow-x:auto;padding:13px;border-radius:10px;background:var(--subtle);">',
    )
    .replace(
      /<code(?: class="([^"]*)")?>/,
      (_tag, classes) => '<code class="md-code ' + (classes || '') + '">',
    )
export function renderMarkdown(text: string) {
  return markdown.render(text)
}
