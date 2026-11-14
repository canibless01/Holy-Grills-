import { msg } from '@/lib/messages';

export type EventQuestion = {name:string;label:string;type:string;required:boolean;options?:string[]};
export function normalizedEventQuestions(rows:EventQuestion[]) {
  return rows.map(row => ({...row, label:row.label.trim(), ...(['select','radio','multiselect'].includes(row.type)?{options:(row.options||[]).map(o=>o.trim()).filter(Boolean)}:{})}));
}
const types = ['text','textarea','select','radio','multiselect','checkbox','date','email','number'];
const control = 'mt-1 w-full rounded-xl border border-border bg-background p-3 text-sm';

/** Shared draft editor: stable field keys survive edits and answer exports. */
export default function EventQuestionsEditor({value,onChange}:{value:EventQuestion[];onChange:(rows:EventQuestion[])=>void}) {
  const update = (index:number, patch:Partial<EventQuestion>) => onChange(value.map((row,i)=>i===index?{...row,...patch}:row));
  return <section className="space-y-3 rounded-2xl border border-border bg-secondary/30 p-4" aria-label={msg('FE_EVENT_QUESTIONS','Registration questions')}>
    <div><h3 className="font-bold">{msg('FE_EVENT_QUESTIONS','Registration questions')}</h3><p className="mt-1 text-xs text-muted-foreground">{msg('FE_EVENT_QUESTIONS_HELP','Ask only what you need for this event. Name, email and phone are already collected.')}</p></div>
    {value.map((field,index)=><div key={field.name} className="space-y-3 rounded-xl border border-border bg-card p-3">
      <label className="block text-sm font-semibold">{msg('FE_EVENT_QUESTION_LABEL','Question')}<input required maxLength={200} className={control} value={field.label} onChange={e=>update(index,{label:e.target.value})}/></label>
      <label className="block text-sm font-semibold">{msg('FE_EVENT_QUESTION_TYPE','Answer type')}<select aria-label={msg('FE_EVENT_QUESTION_TYPE','Answer type')} className={control} value={field.type} onChange={e=>update(index,{type:e.target.value,...(['select','radio','multiselect'].includes(e.target.value)?{options:field.options||[]}: {})})}>{types.map(type=><option key={type} value={type}>{msg(`FE_EVENT_FIELD_${type.toUpperCase()}`,type)}</option>)}</select></label>
      {['select','radio','multiselect'].includes(field.type) && <label className="block text-sm font-semibold">{msg('FE_EVENT_QUESTION_OPTIONS','Options, one per line')}<textarea required rows={3} className={control} value={(field.options||[]).join('\n')} onChange={e=>update(index,{options:e.target.value.split('\n')})}/></label>}
      <div className="flex flex-wrap items-center justify-between gap-3"><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={field.required} onChange={e=>update(index,{required:e.target.checked})}/>{msg('FE_EVENT_QUESTION_REQUIRED','Required')}</label><button type="button" onClick={()=>onChange(value.filter((_,i)=>i!==index))} className="min-h-10 rounded-full border border-border px-4 text-xs font-bold text-destructive">{msg('FE_EVENT_QUESTION_REMOVE','Remove question')}</button></div>
    </div>)}
    <button type="button" disabled={value.length>=20} onClick={()=>onChange([...value,{name:`q_${crypto.randomUUID().replaceAll('-','').slice(0,12)}`,label:'',type:'text',required:false}])} className="min-h-11 rounded-full bg-primary px-5 py-2 text-sm font-bold text-white disabled:opacity-50">{msg('FE_EVENT_QUESTION_ADD','Add question')}</button>
  </section>;
}
