import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useCampus } from '@/lib/campusContext';
import { liveApi } from '@/lib/liveApi';
import { sessionStore } from '@/lib/storage';
import { closureDay, sundayDismissKey } from '@/lib/sundayClosure';
import KitchenClosedPopup from './KitchenClosedPopup';

// Home already has its own status observer; checkout owns its payment popup.
// Other customer pages share this Sunday notice, once per campus/day/session.
export default function SundayClosureNotice() {
  const { campusId } = useCampus();
  const { pathname } = useLocation();
  const [now, setNow] = useState(Date.now());
  const [status, setStatus] = useState(null);
  const day = closureDay(now);
  const eligible = day.sunday && pathname !== '/' &&
    !/^\/(checkout|admin|kitchen|rider)(\/|$)/.test(pathname);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 60000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    setStatus(null);
    if (!eligible || !campusId || sessionStore.getItem(sundayDismissKey(campusId, day.date)) === '1') return;
    let active = true;
    liveApi.orders.getDeliveryWindowStatus(campusId).then(value => { if (active) setStatus(value); }).catch(() => {});
    return () => { active = false; };
  }, [campusId, eligible, day.date]);
  return eligible && status?.is_open === false ? <KitchenClosedPopup status={status} /> : null;
}
