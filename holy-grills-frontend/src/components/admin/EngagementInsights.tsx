import { msg } from '@/lib/messages';
export default function EngagementInsights({ data }: { data: any }) {
  const value = data?.engagement;
  return <section className="rounded-2xl border border-border bg-card p-4 space-y-3">
    <h2 className="font-bold">{msg('FE_ENGAGEMENT_INSIGHTS', 'Student activity and visits')}</h2>
    <p className="text-xs text-muted-foreground">{msg('FE_ENGAGEMENT_BASIS', 'Page visits are measured only after analytics consent. Active users are observed student accounts, independent of purchases. Historical traffic before tracking began is unavailable.')}</p>
    {!value ? <p>{msg('FE_ENGAGEMENT_EMPTY', 'No activity observations are available for this period yet.')}</p> : <>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
        {[['FE_ENGAGEMENT_ACTIVE','Active students',value.active_users],['FE_ENGAGEMENT_VISITORS','Opt-in visitors',value.visitors],['FE_ENGAGEMENT_VIEWS','Page visits',value.page_views]].map(([key,label,n]) => <div key={String(key)}><span>{msg(String(key),String(label))}</span><strong className="block">{Number(n || 0).toLocaleString()}</strong></div>)}
      </div>
      <p className="text-xs text-muted-foreground">{msg('FE_ENGAGEMENT_FUNNEL_HELP', 'Observed visitor funnel: menu → checkout → paid linked account, in order. Guest payments without a linked account are not included in the final step.')}</p>
      <div className="grid grid-cols-3 gap-2 text-xs">{[['FE_ENGAGEMENT_MENU','Menu visitors',value.funnel?.menu_visitors],['FE_ENGAGEMENT_CHECKOUT','Checkout after menu',value.funnel?.checkout_after_menu],['FE_ENGAGEMENT_PAID','Paid linked accounts',value.funnel?.paid_linked_accounts]].map(([key,label,n]) => <div key={String(key)}><span>{msg(String(key),String(label))}</span><strong className="block text-lg">{Number(n || 0).toLocaleString()}</strong></div>)}</div>
      <div className="overflow-x-auto"><table className="w-full text-xs"><thead><tr>{[['FE_ENGAGEMENT_DATE','Date'],['FE_ENGAGEMENT_ACTIVE','Active students'],['FE_ENGAGEMENT_VISITORS','Opt-in visitors'],['FE_ENGAGEMENT_VIEWS','Page visits'],['FE_ENGAGEMENT_CHECKINS','Daily check-ins']].map(([key,label]) => <th className="p-2 text-left" key={key}>{msg(key,label)}</th>)}</tr></thead><tbody>{(value.daily || []).map(day => <tr key={day.day} className="border-t"><td className="p-2">{day.day}</td><td>{day.active_users}</td><td>{day.visitors}</td><td>{day.page_views}</td><td>{day.checkins}</td></tr>)}</tbody></table></div>
      <h3 className="text-sm font-bold">{msg('FE_ENGAGEMENT_STREAKS','Recorded weekly streak outcomes')}</h3>
      <p className="text-xs">{msg('FE_ENGAGEMENT_QUALIFIED','Qualified weeks')}: {value.streaks?.qualified_weeks ?? 0} · {msg('FE_ENGAGEMENT_FAILED','Weeks below the requirement')}: {value.streaks?.failed_weeks ?? 0}</p>
    </>}
  </section>;
}
