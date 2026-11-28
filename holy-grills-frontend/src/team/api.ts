import { apiClient } from '@/lib/apiClient';
import type { TeamData } from './types';
export const teamApi = {
 snapshot: (week?:string):Promise<TeamData> => apiClient.get('/team',week ? {week}:undefined),
 save: (action:string, data:Record<string,unknown>, requestId:string) => apiClient.post('/team/'+action,{...data,request_id:requestId}),
};
export const watDate = (raw = new Date()) => new Intl.DateTimeFormat('en-CA',{timeZone:'Africa/Lagos',year:'numeric',month:'2-digit',day:'2-digit'}).format(raw);
export function monday(raw = watDate()) { const d=new Date(raw+'T12:00:00Z');d.setUTCDate(d.getUTCDate()-((d.getUTCDay()+6)%7));return d.toISOString().slice(0,10); }
export function shiftWeek(raw:string,days:number) {const d=new Date(raw+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+days);return d.toISOString().slice(0,10);}
export const prettyDate = (raw:string) => new Intl.DateTimeFormat('en-NG',{timeZone:'Africa/Lagos',weekday:'short',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}).format(new Date(raw));
export const clock = (n:number) => `${String(Math.floor(n/60)).padStart(2,'0')}:${String(n%60).padStart(2,'0')}`;
export const minute = (s:string) => Number(s.split(':')[0])*60+Number(s.split(':')[1]);
export const localDateTime = (raw:string) => new Date(new Date(raw).getTime()+3600000).toISOString().slice(0,16);
export const utcDateTime = (raw:string) => raw ? new Date(raw+':00+01:00').toISOString() : null;
