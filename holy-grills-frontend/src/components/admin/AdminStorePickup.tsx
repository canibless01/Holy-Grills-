import { useEffect,useRef,useState } from 'react';
import { apiClient } from '@/lib/apiClient';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { useCampus } from '@/lib/campusContext';
import { msg } from '@/lib/messages';
import { toast } from '@/components/ui/use-toast';
import { Field,TextInput } from './AdminShared';

export default function AdminStorePickup(){
 const {user}=useHolyGrill();const {adminCampusId}=useCampus();
 const campus=user?.role==='super_admin'?adminCampusId:user?.campus_id;
 const [form,setForm]=useState({name:'',address:'',instructions:''});const [stamp,setStamp]=useState(null);const [loading,setLoading]=useState(true);const [error,setError]=useState('');const [saving,setSaving]=useState(false);const [retry,setRetry]=useState(0);const lock=useRef(false);const version=useRef(0);
 useEffect(()=>{const current=++version.current;if(!campus){setLoading(false);return;}setLoading(true);setError('');apiClient.get('/delivery/admin/store-pickup').then(r=>{if(current===version.current){setForm(r.location);setStamp(r.updated_at);}}).catch(e=>{if(current===version.current)setError(e.message);}).finally(()=>{if(current===version.current)setLoading(false);});return()=>{version.current++;};},[campus,retry]);
 const save=async event=>{event.preventDefault();if(lock.current)return;lock.current=true;setSaving(true);setError('');const current=version.current;try{const r=await apiClient.patch('/delivery/admin/store-pickup',{location:form,expected_updated_at:stamp});if(current===version.current){setStamp(r.updated_at);toast({title:msg('FE_STORE_PICKUP_SAVED','Pickup point saved')});}}catch(e){if(current===version.current)setError(e.message);}finally{lock.current=false;setSaving(false);}};
 if(!campus)return <p>{msg('STORE_PICKUP_CAMPUS_REQUIRED','Select a campus to configure its physical pickup point.')}</p>;
 return <form onSubmit={save} className="rounded-2xl border border-border bg-card p-5 space-y-4 max-w-xl"><h3 className="font-heading text-lg font-bold">{msg('FE_STORE_PICKUP_CONFIG','Store pickup point')}</h3><p className="text-sm text-muted-foreground">{msg('FE_STORE_PICKUP_DISABLED_HELP','Configure this campus first. Store pickup stays hidden until its feature flag is enabled. Preparing and ready remain part of fulfillment.')}</p>{error&&<div role="alert" className="space-y-2 text-sm"><p>{error}</p><button type="button" onClick={()=>setRetry(r=>r+1)} className="font-bold underline">{msg('FE_PLATFORM_RETRY','Retry')}</button></div>}{loading?<p role="status">{msg('FE_STORE_PICKUP_LOADING','Loading pickup point…')}</p>:<fieldset disabled={saving} className="space-y-4"><Field label={msg('FE_STORE_PICKUP_NAME','Pickup-point name')}><TextInput required maxLength={120} value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></Field><Field label={msg('FE_STORE_PICKUP_ADDRESS','Street address')}><TextInput required maxLength={500} value={form.address} onChange={e=>setForm({...form,address:e.target.value})}/></Field><Field label={msg('FE_STORE_PICKUP_INSTRUCTIONS','Collection instructions')}><TextInput maxLength={500} value={form.instructions} onChange={e=>setForm({...form,instructions:e.target.value})}/></Field><button disabled={loading} className="rounded-full bg-gradient-cta px-5 py-3 font-bold text-white">{msg('FE_STORE_PICKUP_SAVE','Save pickup point')}</button></fieldset>}</form>;
}
