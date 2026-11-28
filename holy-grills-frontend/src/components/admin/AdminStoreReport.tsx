import { csvCell } from '@/lib/csvCell';
import { useEffect, useState } from 'react';
import { BarChart3 } from 'lucide-react';
import { apiClient } from '@/lib/apiClient';
import { formatNaira } from '@/lib/hgUtils';
import { msg } from '@/lib/messages';
import { Card } from './ui/AdminKit';

const today = () => new Date(Date.now() + 3600000).toISOString().slice(0, 10);
const ago = () => new Date(Date.now() + 3600000 - 29 * 86400000).toISOString().slice(0, 10);
export default function AdminStoreReport({ campusId, stores, universities = [] }) {
  const [first,setFirst]=useState(ago);
  const [last,setLast]=useState(today);
  const [store,setStore]=useState('');
  const [university,setUniversity]=useState('');
  const [revision,setRevision]=useState(0);
  const [result,setResult]=useState<any>(null);
  const key=JSON.stringify([campusId,store,first,last,revision]);
  useEffect(()=>{
    let active=true;
    if(!first || !last){setResult({key,error:msg('STORE_REPORT_RANGE','Choose a reporting period of up to one year, with the end after the start.')});return;}
    const end=new Date(`${last}T00:00:00+01:00`);end.setTime(end.getTime()+86400000);
    if(!Number.isFinite(end.getTime()))return;
    apiClient.get('/admin/store-analytics',{...(campusId?{campus_id:campusId}:{}),...(store?{store_id:store}:{}),start:`${first}T00:00:00+01:00`,end:end.toISOString()}).then(data=>{if(active)setResult({key,data});}).catch(error=>{if(active)setResult({key,error:error.message});});
    return ()=>{active=false;};
  },[key]);
  const current=result?.key===key?result:null;
  const rows=(current?.data?.rows || []).filter(row=>!!campusId || !university || row.university_id===university);
  const total=(field:string)=>rows.reduce((sum,row)=>sum+Number(row[field]||0),0);
  const exportReport=()=>{
    const cell=(value:unknown)=>`"${csvCell(value)}"`;
    const headers=['campus','store','orders','paid_orders','paid_volume','completed_refunds','retained_revenue','retained_food_revenue','retained_delivery_revenue','completed_orders','cancelled_orders'];
    const csv=[headers.map(cell).join(','),...rows.map(row=>[row.campus_name,row.store_name || msg('FE_STORE_REPORT_UNASSIGNED','Legacy / unassigned'),row.orders,row.paid_orders,row.paid_volume,row.refunds,row.retained_revenue,row.retained_food_revenue,row.retained_delivery_revenue,row.completed_orders,row.cancelled_orders].map(cell).join(','))].join('\r\n');
    const url=URL.createObjectURL(new Blob(['\uFEFF'+csv],{type:'text/csv;charset=utf-8;'}));const link=document.createElement('a');link.href=url;link.download=`store-performance-${first}-${last}.csv`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  return <Card className="p-5 space-y-4"><h3 className="flex gap-2 items-center font-heading text-lg font-bold"><BarChart3 className="h-5 w-5 text-primary"/>{msg('FE_STORE_REPORT','Store performance')}</h3><p className="text-xs text-muted-foreground">{msg('FE_STORE_REPORT_BASIS','Orders created in the selected period. Revenue reflects completed refunds recorded so far; test orders and unpaid amounts are excluded from revenue.')}</p>{!campusId && universities.length>0 && <label className="block text-sm">{msg('FE_UNIVERSITY_TITLE','Universities')}<select value={university} onChange={event=>setUniversity(event.target.value)} className="mt-1 min-h-11 rounded-xl border border-border bg-background p-2"><option value="">{msg('FE_STORE_REPORT_ALL_UNIVERSITIES','All universities')}</option>{universities.map(row=><option value={row.id} key={row.id}>{row.name}</option>)}</select></label>}<div className="grid sm:grid-cols-3 gap-3">{[['start',first,setFirst,'FE_STORE_REPORT_FROM','From'],['end',last,setLast,'FE_STORE_REPORT_TO','Through']].map(([id,value,setValue,label,fallback])=><label className="text-sm" key={id as string}>{msg(label as string,fallback as string)}<input type="date" required value={value as string} onChange={event=>(setValue as (value:string)=>void)(event.target.value)} className="mt-1 block w-full min-h-11 rounded-xl border border-border bg-background p-2"/></label>)}<label className="text-sm">{msg('FE_STORE_REPORT_STORE','Store')}<select value={store} onChange={event=>setStore(event.target.value)} className="mt-1 w-full min-h-11 rounded-xl border border-border bg-background p-2"><option value="">{msg('FE_STORE_REPORT_ALL','All stores')}</option>{stores.map(row=><option value={row.id} key={row.id}>{row.name}</option>)}</select></label></div>
    {!current?<p role="status">{msg('FE_STORE_REPORT_LOADING','Loading store performance…')}</p>:current.error?<div role="alert" className="space-y-2"><p>{current.error}</p><button type="button" className="min-h-11 rounded-full bg-primary px-5 font-bold text-white" onClick={()=>setRevision(value=>value+1)}>{msg('FE_PLATFORM_RETRY','Retry')}</button></div>:<><div className="grid grid-cols-2 lg:grid-cols-4 gap-3">{[['paid_volume','FE_STORE_REPORT_GROSS','Paid volume'],['refunds','FE_STORE_REPORT_REFUNDS','Completed refunds'],['retained_revenue','FE_STORE_REPORT_NET','Retained revenue'],['retained_food_revenue','FE_STORE_REPORT_FOOD','Net food revenue']].map(([field,label,fallback])=><div className="min-w-0 rounded-xl bg-secondary p-3" key={field}><p className="text-xs text-muted-foreground">{msg(label,fallback)}</p><p className="mt-2 break-words font-bold">{formatNaira(total(field))}</p></div>)}</div><button className="min-h-11 rounded-full border border-border px-5 text-sm font-bold disabled:opacity-50" type="button" disabled={!rows.length} onClick={exportReport}>{msg('FE_STORE_REPORT_EXPORT','Download report CSV')}</button><div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="border-b border-border text-left"><th className="p-2">{msg('FE_STORE_REPORT_STORE','Store')}</th><th className="p-2">{msg('FE_STORE_REPORT_ORDERS','Orders')}</th><th className="p-2">{msg('FE_STORE_REPORT_PAID','Paid orders')}</th><th className="p-2">{msg('FE_STORE_REPORT_DONE','Completed')}</th><th className="p-2">{msg('FE_STORE_REPORT_NET','Retained revenue')}</th></tr></thead><tbody>{rows.map(row=><tr key={`${row.campus_id}:${row.store_id}`} className="border-b border-border/60"><td className="p-2"><strong>{row.store_name || msg('FE_STORE_REPORT_UNASSIGNED','Legacy / unassigned')}</strong><span className="block text-xs text-muted-foreground">{row.campus_name}</span></td><td className="p-2">{row.orders}</td><td className="p-2">{row.paid_orders}</td><td className="p-2">{row.completed_orders}</td><td className="p-2 whitespace-nowrap">{formatNaira(Number(row.retained_revenue))}</td></tr>)}</tbody></table></div>{!rows.length && <p className="text-sm text-muted-foreground">{msg('FE_STORE_REPORT_EMPTY','No orders in this reporting period.')}</p>}<p className="text-xs text-muted-foreground">{msg('FE_STORE_REPORT_LEGACY','Historical orders without a recorded store stay unassigned. They are not attributed to a store by guesswork.')}</p></>}
  </Card>;
}
