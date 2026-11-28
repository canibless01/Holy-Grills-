import { useId } from 'react';
import { msg } from '@/lib/messages';

export function eventAnswersComplete(fields: any[], answers: Record<string, any>) {
  return fields.every(field => !field.required || (field.type === 'checkbox' ? answers[field.name] === true : Array.isArray(answers[field.name]) ? answers[field.name].length > 0 : String(answers[field.name] ?? '').trim() !== ''));
}

/** Each attendee owns a separate answer map and radio group namespace. */
export default function EventAnswers({ fields, value, onChange }: { fields: any[]; value: Record<string, any>; onChange: (answers: Record<string, any>) => void }) {
  const prefix = useId();
  const change = (name: string, next: any) => onChange({ ...value, [name]: next });
  const base = 'mt-1 w-full rounded-xl border border-border bg-background p-3 text-sm';
  return <div className="space-y-3">{fields.map(field => {
    const current = value[field.name] ?? '';
    const label = `${field.label}${field.required ? ' *' : ''}`;
    if (field.type === 'radio' || field.type === 'multiselect') return <fieldset key={field.name} className="rounded-xl border border-border p-3 space-y-2"><legend className="px-1 text-sm font-semibold">{label}</legend>{(field.options || []).map(option => <label key={option} className="flex min-h-10 items-center gap-2 text-sm"><input type={field.type === 'radio' ? 'radio' : 'checkbox'} name={`${prefix}-${field.name}`} checked={field.type === 'radio' ? current === option : Array.isArray(current) && current.includes(option)} onChange={event => change(field.name, field.type === 'radio' ? option : event.target.checked ? [...(Array.isArray(current) ? current : []), option] : (Array.isArray(current) ? current : []).filter(item => item !== option))} />{option}</label>)}</fieldset>;
    if (field.type === 'checkbox') return <label key={field.name} className="flex min-h-11 items-center gap-2 rounded-xl border border-border p-3 text-sm"><input type="checkbox" checked={current === true} onChange={event => change(field.name, event.target.checked)} /><span>{label}</span></label>;
    return <label key={field.name} className="block text-sm font-semibold">{label}{field.type === 'select' ? <select aria-label={field.label} required={field.required} className={base} value={current} onChange={event => change(field.name, event.target.value)}><option value="">{msg('FE_EVENT_ANSWER_CHOOSE', 'Choose an option')}</option>{(field.options || []).map(option => <option key={option} value={option}>{option}</option>)}</select> : field.type === 'textarea' ? <textarea required={field.required} maxLength={5000} rows={3} placeholder={label} className={base} value={current} onChange={event => change(field.name, event.target.value)} /> : <input type={['number', 'email', 'date'].includes(field.type) ? field.type : 'text'} step={field.type === 'number' ? 'any' : undefined} required={field.required} maxLength={5000} placeholder={label} className={base} value={current} onChange={event => change(field.name, event.target.value)} />}</label>;
  })}</div>;
}
