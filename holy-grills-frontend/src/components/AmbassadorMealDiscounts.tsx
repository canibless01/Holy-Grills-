import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Gift } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { formatNaira } from '@/lib/hgUtils';
import { msg } from '@/lib/messages';

/** Lightweight owned benefits, including rewards earned before an ambassador tag was removed. */
export default function AmbassadorMealDiscounts() {
  const { user, cartCount } = useHolyGrill();
  const [discounts, setDiscounts] = useState<any[]>([]);
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!user?.id) return;
    let current = true;
    setDiscounts([]); setFailed(false);
    liveApi.ambassadors.myMealDiscounts().then(rows => {
      if (current) setDiscounts((rows || []).filter(row => row.status === 'active' && row.uses_remaining > 0));
    }).catch(() => { if (current) setFailed(true); });
    return () => { current = false; };
  }, [user?.id, retry]);
  if (!failed && !discounts.length) return null;
  return (
    <section aria-label={msg('FE_AMBASSADOR_MEAL_DISCOUNTS', 'Your meal discounts')} className="rounded-2xl bg-card border border-border p-4 space-y-3">
      <h2 className="font-heading font-bold flex items-center gap-2"><Gift className="w-4 h-4 text-primary" />{msg('FE_AMBASSADOR_MEAL_DISCOUNTS', 'Your meal discounts')}</h2>
      {failed ? <p role="alert" className="text-sm text-destructive">{msg('FE_CHECKOUT_MEAL_FAILED', 'Your meal discounts could not be loaded.')}{' '}
        <button type="button" onClick={() => setRetry(value => value + 1)} className="underline">{msg('FE_LOOKUP_RETRY', 'Retry')}</button>
      </p> : <>
        <p className="text-xs text-muted-foreground">{msg('FE_MEAL_DISCOUNT_TOPUP_HELP', 'Choose any eligible meal. Pay the amount above your discount plus delivery at checkout.')}</p>
        {discounts.map(discount => <div key={discount.id} className="rounded-xl border border-border p-3 text-sm">
          <p className="font-bold">{discount.code} · {formatNaira(discount.max_meal_value)}</p>
          <p className="text-xs text-muted-foreground">{discount.uses_remaining}/{discount.uses_total} · {msg('FE_AMBASSADOR_DISCOUNT_EXPIRES', 'Expires')} {String(discount.expires_at).slice(0, 10)}</p>
        </div>)}
        <Link to={cartCount ? '/checkout#ambassador-meal-discounts' : '/menu'} className="inline-flex rounded-full bg-primary px-4 py-2 text-sm font-bold text-white">
          {cartCount ? msg('FE_MEAL_DISCOUNT_CHECKOUT', 'Apply at checkout') : msg('FE_MEAL_DISCOUNT_CHOOSE_MEAL', 'Choose a meal')}
        </Link>
      </>}
    </section>
  );
}
