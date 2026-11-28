import { msg } from '@/lib/messages';

/** Popup artwork is displayed on exactly one of these five pages. */
export default function CmsPlacementSelect({ value, onChange }) {
  return <select aria-label={msg('FE_SF_PLACEMENT', 'Show on page')} value={value || 'home'} onChange={(event) => onChange(event.target.value)} className="w-full p-2 rounded-lg border border-border text-sm bg-card">
    <option value="home">{msg('FE_SF_PAGE_HOME', 'Home')}</option>
    <option value="menu">{msg('FE_SF_PAGE_MENU', 'Menu')}</option>
    <option value="dashboard">{msg('FE_SF_PAGE_DASHBOARD', 'Dashboard')}</option>
    <option value="orders">{msg('FE_SF_PAGE_ORDERS', 'Orders')}</option>
    <option value="rewards">{msg('FE_SF_PAGE_REWARDS', 'Rewards')}</option>
  </select>;
}
