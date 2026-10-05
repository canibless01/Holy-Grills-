import { useState, useEffect } from 'react';
import { MessageCircle, X } from 'lucide-react';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { liveApi } from '@/lib/liveApi';
import { normalizeWhatsAppNumber } from '@/lib/valueText';

/**
 * WhatsAppFloatingButton — fixed bottom-right "Chat with us" button on all
 * student-facing screens. Hidden when whatsapp_support_enabled is false.
 * Pre-fills a context-aware message (includes order number if user has an
 * active order).
 *
 * WHERE THE VALUE COMES FROM (the chain, end to end):
 *   system_settings row (key = whatsapp_support_number, is_public = TRUE)
 *     → GET /api/storefront/config/public        (only is_public rows!)
 *     → featureConfig.loadSystemSettings()       (settingsMap)
 *     → getStringSetting('whatsapp_support_number')
 *     → https://wa.me/<number>
 *
 * Two things used to break that chain silently, and both made the button look
 * like it "wasn't reading the table":
 *   1. A row with is_public = false is filtered out of the public config, so
 *      the button fell back to the hardcoded '2348000000000'. New keys created
 *      from the admin screen defaulted to private, so a number typed there was
 *      saved, visible in the admin list, and never used.
 *   2. getSetting() coerced numeric-looking strings to Number, so
 *      "+234 801 234 5678" became NaN and the link became https://wa.me/NaN.
 * Both are fixed here (string read + digit sanitising) and at the source (the
 * admin screen now shows and can set is_public).
 *
 * Server-side fallback, for reference: if the table has no value the backend
 * substitutes the WHATSAPP_SUPPORT_NUMBER environment variable
 * (app/routes/storefront.py → get_public_config).
 */

export default function WhatsAppFloatingButton() {
  const { getStringSetting, getBoolSetting } = useHolyGrill();
  const [activeOrder, setActiveOrder] = useState(null);
  const [dismissed, setDismissed] = useState(false);

  const enabled = getBoolSetting('whatsapp_support_enabled', true);
  const number = normalizeWhatsAppNumber(getStringSetting('whatsapp_support_number', '2348000000000'));
  const defaultMessage = getStringSetting('whatsapp_support_message', 'Hello, I need help with my order');

  useEffect(() => {
    let cancelled = false;
    const checkActive = async () => {
      try {
        const orders = await liveApi.orders.getActive();
        if (cancelled) return;
        const first = Array.isArray(orders) ? orders[0] : null;
        if (first) setActiveOrder(first);
      } catch { /* ignore — non-auth or no active orders */ }
    };
    checkActive();
    return () => { cancelled = true; };
  }, []);

  // No usable number means no button: a wa.me/NaN link is worse than nothing.
  if (!enabled || dismissed || !number) return null;

  const orderId = activeOrder?.id || activeOrder?.order_id;
  const message = orderId
    ? `Hello, I need help with my order #${orderId}`
    : defaultMessage;

  const href = `https://wa.me/${number}?text=${encodeURIComponent(message)}`;

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="fixed bottom-24 md:bottom-20 right-4 z-40 flex items-center gap-2 pl-3 pr-4 py-3 rounded-full bg-green-500 text-white shadow-lg hover:bg-green-600 active:scale-95 transition-all group"
    >
      <MessageCircle className="w-5 h-5 fill-white/20" />
      <span className="text-sm font-bold whitespace-nowrap">Chat with us</span>
      <button
        onClick={(e) => { e.preventDefault(); setDismissed(true); }}
        className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-foreground flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
        aria-label="Dismiss"
      >
        <X className="w-3 h-3 text-white" />
      </button>
    </a>
  );
}
