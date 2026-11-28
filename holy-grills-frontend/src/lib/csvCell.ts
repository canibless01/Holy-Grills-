/** Escape a quoted CSV field and keep user input from becoming a spreadsheet formula. */
export function csvCell(value: unknown): string {
  let text = String(value ?? '');
  if (/^[\s\uFEFF]*[=+@-]/u.test(text)) text = `'${text}`;
  return text.replace(/"/g, '""');
}
