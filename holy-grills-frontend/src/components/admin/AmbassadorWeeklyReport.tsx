import { useRef, useState } from 'react';
import { liveApi } from '@/lib/liveApi';
import { msg } from '@/lib/messages';
import { watCalendarDay } from '@/lib/watCalendar';
import { buildWhatsAppShareUrl } from '@/lib/whatsappShare';
import { toast } from '@/components/ui/use-toast';

export default function AmbassadorWeeklyReport() {
  const [week, setWeek] = useState(watCalendarDay());
  const [report, setReport] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const load = async () => {
    if (lock.current) return;
    lock.current = true; setBusy(true); setReport(null);
    try { setReport(await liveApi.ambassadors.weeklyReport(week)); }
    catch (error) { toast({ title: error.message, variant: 'destructive' }); }
    finally { lock.current = false; setBusy(false); }
  };
  const copy = async () => {
    try { await navigator.clipboard.writeText(report.share_text); }
    catch { toast({ title: msg('FE_AMBASSADOR_CLIPBOARD_FAILED', 'Copy failed. Select and copy the link or caption instead.'), variant: 'destructive' }); }
  };
  return <section className="rounded-2xl border border-border bg-card p-4 space-y-3">
    <h2 className="font-bold">{msg('FE_AMBASSADOR_WEEKLY_REPORT', 'Weekly ambassador report')}</h2>
    <p className="text-xs text-muted-foreground">{msg('FE_AMBASSADOR_REPORT_HELP', 'Delivered, paid orders after completed refunds. Sharing is confirmed manually; opening WhatsApp is not proof of a share.')}</p>
    <div className="flex flex-wrap items-end gap-3">
      <label className="text-xs font-bold">{msg('FE_AMBASSADOR_REPORT_WEEK', 'Week containing')}<input type="date" value={week} onChange={e => { setWeek(e.target.value); setReport(null); }} className="mt-1 block rounded-xl border p-2" /></label>
      <button type="button" disabled={busy || !week} onClick={load} className="rounded-full bg-primary px-4 py-2 text-sm font-bold text-white disabled:opacity-50">{msg('FE_AMBASSADOR_REPORT_LOAD', 'Prepare report')}</button>
    </div>
    {report && <><textarea readOnly aria-label={msg('FE_AMBASSADOR_WEEKLY_REPORT', 'Weekly ambassador report')} value={report.share_text} rows={8} className="w-full rounded-xl border p-3 text-sm" />
      <div className="flex flex-wrap gap-4 text-xs font-bold"><button type="button" onClick={copy} className="underline">{msg('FE_AMBASSADOR_REPORT_COPY', 'Copy report')}</button><a href={buildWhatsAppShareUrl(report.share_text)} target="_blank" rel="noopener noreferrer" className="underline">{msg('FE_AMBASSADOR_REPORT_SHARE', 'Share report on WhatsApp')}</a></div>
    </>}
  </section>;
}
