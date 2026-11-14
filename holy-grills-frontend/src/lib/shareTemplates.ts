export function resolveShareTemplate(sections, key) {
  const available = (Array.isArray(sections) ? sections : [])
    .filter((section) => section.section_type === 'share_template' && section.is_active !== false);
  return available.find((section) => (section.key || section.content?.key) === key)
    || available.find((section) => (section.key || section.content?.key) === 'share_template') || null;
}

export function resolveShareCaption(template, payload, defaults = { hp: 0, name: '' }) {
  const caption = template?.content?.caption_template;
  if (typeof caption !== 'string' || !caption.trim()) return payload.caption || '';
  const values = {
    hp: payload.hp ?? defaults.hp,
    name: payload.name ?? defaults.name,
    headline: payload.headline || '', value: payload.value ?? '',
    caption: payload.caption || '', link: payload.link || '', code: payload.code || '',
  };
  return caption.replace(/\{(hp|name|headline|value|caption|link|code)\}/g, (_, key) => String(values[key]));
}
