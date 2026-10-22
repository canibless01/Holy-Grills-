import { useLocation } from 'react-router-dom';
import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { liveApi, isAuthenticated, clearTokens } from './liveApi';
import { apiClient } from './apiClient';
import { localStore, sessionStore } from './storage';
import { isHydratingPrerender } from './hydrationMode';
import { loadSystemSettings, loadFeatureFlags, useFeatureFlags, getSetting, getStringSetting, getBoolSetting } from './featureConfig';
import { loadTiers } from './hgUtils';
import { msg, useMessages } from '@/lib/messages';
import { toast } from '@/components/ui/use-toast';
import { initOneSignal } from './onesignal';

// Holy Grills app context — real JWT auth against the live backend.
// No demo auto-login. Authenticated users hit the server-side cart; guests
// get a local cart (localStorage) so they can browse + order without an account.
// TODO(ts): the context value is an untyped bag today; giving it a real
// interface is follow-up work (no runtime change: createContext() and
// createContext(undefined) are identical).
const HolyGrillContext = createContext<any>(undefined);
// Identity first; wallet and tier have their own background refresh paths.
const loadSessionProfile = async () => {
  try { return await apiClient.get('/auth/me', { session: '1' }); }
  catch (error) {
    if (error.status !== 0 && !(error.status >= 500)) throw error;
    return apiClient.get('/auth/me', { session: '1' });
  }
};
const GUEST_CART_KEY = 'hg_guest_cart';

const readAllGuestItems = () => {
  try { const items = JSON.parse(localStore.getItem(GUEST_CART_KEY) || '[]'); return Array.isArray(items) ? items : []; } catch { return []; }
};
const guestCartScope = item => item.guest_campus_id || item.menu_items?.campus_id || localStore.getItem('hg_campus_id');
const readGuestCart = () => readAllGuestItems().filter(item => guestCartScope(item) === localStore.getItem('hg_campus_id'));
const writeGuestCart = (items) => {
  const campus = localStore.getItem('hg_campus_id');
  const otherCampuses = readAllGuestItems().filter(item => guestCartScope(item) !== campus);
  localStore.setItem(GUEST_CART_KEY, JSON.stringify([...otherCampuses, ...items.map(item => ({ ...item, guest_campus_id: campus }))]));
};

const computeCart = (items) => ({
  items,
  subtotal: items.reduce((s, ci) => s + (ci.menu_items?.price || 0) * ci.quantity, 0),
  item_count: items.length,
  hp_earn_preview: items.reduce((s, ci) => s + (ci.menu_items?.hp_earn_value || 0) * (ci.menu_items?.hp_multiplier || 1) * ci.quantity, 0),
  has_unavailable_items: items.some((ci) => ci.menu_items?.is_available === false),
});

const EMPTY_CART = { items: [], subtotal: 0, item_count: 0, hp_earn_preview: 0, has_unavailable_items: false };

// Persist the signed-in user's campus so apiClient can scope storefront /
// kitchen-status requests (X-Campus-ID) — the backend does not scope all of
// those endpoints from the JWT alone, which made the storefront read
// "closed" for signed-in users on an open campus.
// apiClient needs the role as well as the campus to build X-Campus-ID: a
// super_admin with a campus on their profile must NOT be scoped to it by
// default (their default view is every campus), while every other role is.
// Persisted here because apiClient runs outside React and cannot read context.
// `campus_id` is read from BOTH shapes /auth/me has returned: the top-level
// alias and the nested `profile.campus_id`. Reading only the top level is what
// left `hg_user_campus_id` unset, so apiClient sent no X-Campus-ID at all and
// every campus-scoped endpoint (menu availability, gates, hostels,
// delivery-window status, operating hours) answered with global data.
const persistUserCampus = (me) => {
  const campusId = me?.campus_id ?? me?.profile?.campus_id ?? null;
  if (campusId) localStore.setItem('hg_user_campus_id', campusId);
  else localStore.removeItem('hg_user_campus_id');
  if (me?.role) localStore.setItem('hg_user_role', me.role);
  else localStore.removeItem('hg_user_role');
};

// /api/auth/me nests HP under `profile` (hp_earned_120day, hp_balance) and
// exposes `tier` at the top level. /api/hp/balance returns hp_earned_120day at
// the TOP level. Normalise the /auth/me response into a balance-shaped object
// so the tier ring + progress bar read the real value immediately — refreshHp()
// later overwrites this with the authoritative /hp/balance object. The previous
// code read profile.hp_balance (top level, which doesn't exist) and stored null,
// freezing the ring at 0.
const normalizeHpBalance = (me) => {
  if (!me) return null;
  // Already a full /hp/balance-shaped object (top-level hp_earned_120day/active).
  if (me.hp_earned_120day != null || me.active != null || me.total_visible != null) {
    return {
      active: me.active ?? 0,
      pending: me.pending ?? 0,
      total_visible: me.total_visible ?? 0,
      monthly_hp_earned: me.monthly_hp_earned ?? 0,
      hp_earned_120day: me.hp_earned_120day ?? 0,
      tier_bonus_multiplier: me.tier_bonus_multiplier ?? 1,
      tier: me.tier ?? null,
      is_in_grace_period: me.is_in_grace_period ?? me.tier?.is_in_grace_period ?? false,
      grace_period_ends_at: me.grace_period_ends_at ?? me.tier?.grace_period_ends_at ?? null,
    };
  }
  const p = me.profile || {};
  return {
    active: p.hp_balance ?? 0,
    pending: 0,
    total_visible: p.hp_balance ?? 0,
    monthly_hp_earned: 0,
    hp_earned_120day: p.hp_earned_120day ?? 0,
    tier_bonus_multiplier: 1,
    tier: me.tier ?? null,
    is_in_grace_period: me.tier?.is_in_grace_period ?? false,
    grace_period_ends_at: me.tier?.grace_period_ends_at ?? null,
  };
};

// Route chunks are lazy (App.tsx), so the first navigation to a page pays for
// its JS. Right after sign-in the app is already busy with /auth/me plus a burst
// of background refreshes, and that first chunk request can lose the race: the
// page sits on the Suspense fallback until something else re-renders, which is
// what "I had to refresh before it came up" was. Warming the destination chunk
// while those refreshes run removes the wait.
// The specifier must match App.tsx's lazy(() => import(...)) exactly, so the
// browser reuses the same chunk instead of fetching a second copy.
const warmRouteChunk = (loader) => {
  try { void loader(); } catch { /* a failed warm-up must never break sign-in */ }
};

const warmPostLoginChunks = (role) => {
  // The role's landing page first, then the menu — it is the one page every role
  // browses, it is its own lazy chunk, and it was the "had to refresh before it
  // came up" report. Warming both while the post-login refreshes run means
  // neither navigation waits on a chunk fetch.
  if (role === 'kitchen') warmRouteChunk(() => import('@/pages/Kitchen'));
  else if (role === 'rider') warmRouteChunk(() => import('@/pages/Rider'));
  else if (role === 'admin' || role === 'super_admin') warmRouteChunk(() => import('@/pages/Admin'));
  else warmRouteChunk(() => import('@/pages/Dashboard'));
  warmRouteChunk(() => import('@/pages/Menu'));
};

export const HolyGrillProvider = ({ children }) => {
  const featureVersion = useFeatureFlags();
  const { pathname } = useLocation();
  const publicPage = ['/', '/menu', '/faq', '/contact', '/our-story', '/terms'].includes(pathname) || pathname.startsWith('/menu/');
  useMessages();
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [sessionAttempt, setSessionAttempt] = useState(0);
  const welcomeRecoveryUser = useRef(null);
  const restoreVersion = useRef(0);
  const recoverWelcome = (profile) => {
    if (!profile?.id || welcomeRecoveryUser.current === profile.id) return;
    welcomeRecoveryUser.current = profile.id;
    // Token delivery and verified identity must not wait for loyalty work.
    void apiClient.post('/auth/session-activity', {}).then(() => liveApi.auth.getStreak()).then(setStreak).catch(() => {});
    if (profile.role === 'student') void apiClient.post('/auth/welcome-credit', {}).catch(() => {});
  };
  const [cart, setCart] = useState(EMPTY_CART);
  const cartRequestVersion = useRef(0);
  const [cartCount, setCartCount] = useState(0);
  const [hpBalance, setHpBalance] = useState(null);
  const [wallet, setWallet] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [streak, setStreak] = useState(null);
  const [systemSettings, setSystemSettings] = useState({});
  // Track B: a pre-rendered page is built with empty storage, so its HTML shows
  // the signed-out state. Start there while hydrating (otherwise React sees a
  // different tree than the server sent); the session effect below adopts the
  // real token immediately after mount.
  const [authed, setAuthed] = useState(() => !isHydratingPrerender() && isAuthenticated());
  const [savedItems, setSavedItems] = useState([]);

  const loadGuestCart = useCallback(() => {
    cartRequestVersion.current += 1;
    const items = readGuestCart();
    setCart(computeCart(items));
    setCartCount(items.length);
  }, []);

  const refreshCart = useCallback(async () => {
    const version = ++cartRequestVersion.current;
    if (!isAuthenticated()) { loadGuestCart(); return; }
    try {
      const c = await liveApi.cart.get();
      if (version !== cartRequestVersion.current || !isAuthenticated()) return;
      const rawItems = c.items || c.cart_items || [];
      const items = rawItems.map((ci) => {
        const mi = ci.menu_items || ci.menu_item || { name: ci.name, price: ci.price, hp_earn_value: ci.hp_earn_value, is_available: ci.is_available !== false };
        return {
          id: ci.id,
          menu_item_id: ci.menu_item_id,
          quantity: ci.quantity,
          notes: ci.options?.notes || ci.notes || '',
          selected_variations: ci.selected_variations || [],
          selected_addons: ci.selected_addons || [],
          modifier_summary: ci.modifier_summary || [],
          selection_error: ci.selection_error,
          menu_items: mi,
          is_unavailable: ci.is_unavailable || mi.is_available === false,
        };
      });
      setCart({
        items,
        subtotal: c.subtotal ?? items.reduce((s, ci) => s + (ci.menu_items?.price || 0) * ci.quantity, 0),
        item_count: c.item_count ?? items.length,
        hp_earn_preview: c.hp_earn_preview ?? items.reduce((s, ci) => s + (ci.menu_items?.hp_earn_value || 0) * (ci.menu_items?.hp_multiplier || 1) * ci.quantity, 0),
        has_unavailable_items: c.has_unavailable_items ?? items.some((ci) => ci.menu_items?.is_available === false),
      });
      setCartCount(c.item_count ?? items.length);
    } catch (e) { console.error('Cart refresh failed:', e); }
  }, [loadGuestCart]);

  const refreshNotifications = useCallback(async () => {
    if (!isAuthenticated()) return;
    try {
      const n = await liveApi.notifications.list({ limit: 30 });
      setNotifications(n.notifications || n.items || []);
      setUnreadCount(n.unread_count ?? 0);
    } catch (e) { console.error('Notif refresh failed:', e); }
  }, []);

  const refreshHp = useCallback(async () => {
    if (!isAuthenticated()) return;
    try { setHpBalance(await liveApi.hp.getBalance()); } catch (e) { /* ignore */ }
  }, []);

  const refreshWallet = useCallback(async () => {
    if (!isAuthenticated()) return;
    try { setWallet(await liveApi.wallet.get()); } catch (e) { /* ignore */ }
  }, []);

  // Saved-for-later items — server-backed (/saved) for authenticated users.
  // Guests have no server list; savedItems stays empty and the heart prompts login.
  const refreshSavedItems = useCallback(async () => {
    if (!isAuthenticated()) { setSavedItems([]); return; }
    try { setSavedItems(await liveApi.saved.list()); } catch (e) { /* ignore */ }
  }, []);

  const toggleSavedItem = useCallback(async (item) => {
    if (!isAuthenticated()) return false;
    const existing = savedItems.find((s) => s.menu_item_id === item.id);
    try {
      if (existing) { await liveApi.saved.remove(existing.id); setSavedItems((prev) => prev.filter((s) => s.id !== existing.id)); return false; }
      await liveApi.saved.add({ menu_item_id: item.id, name: item.name, price: item.price, hp_earn_value: item.hp_earn_value, image_url: item.image_url });
      await refreshSavedItems();
      return true;
    } catch (e) { return existing ? true : false; }
  }, [savedItems, refreshSavedItems]);

  const removeSavedItem = useCallback(async (savedId) => {
    if (!isAuthenticated()) return;
    try { await liveApi.saved.remove(savedId); setSavedItems((prev) => prev.filter((s) => s.id !== savedId)); } catch (e) { /* ignore */ }
  }, []);

  const moveSavedToCart = useCallback(async (saved) => {
    // Use the dedicated atomic endpoint (POST /saved/<id>/move-to-cart) which
    // merges into an existing cart row and removes the saved row in one call,
    // instead of a cart.add + saved.remove pair that could half-fail.
    try {
      await liveApi.saved.moveToCart(saved.id);
      setSavedItems((prev) => prev.filter((s) => s.id !== saved.id));
      await refreshCart();
    } catch (e) { /* ignore */ }
  }, [refreshCart]);

  const isSavedItem = useCallback((menuItemId) => savedItems.some((s) => s.menu_item_id === menuItemId), [savedItems]);

  const refreshUser = useCallback(async () => {
    if (!isAuthenticated()) return;
    try {
      const profile = await liveApi.auth.me();
      setUser(profile); persistUserCampus(profile);
      setHpBalance(normalizeHpBalance(profile));
      setWallet(profile.wallet || null);
      // Push runs on OneSignal — identify the signed-in user so the device's
      // player id maps to their account (fire-and-forget, never blocks login).
      if (profile?.id) initOneSignal(profile.id).catch(() => {});
    } catch (e) { /* ignore */ }
  }, []);

  const refreshStreak = useCallback(async () => {
    if (!isAuthenticated()) return;
    try { setStreak(await liveApi.auth.getStreak()); } catch (e) { /* ignore */ }
  }, []);

  // Restore session on load — real token → fetch profile; no token → guest cart.
  useEffect(() => {
    const version = ++restoreVersion.current;
    const init = async () => {
      setSessionError(null);
      setAuthed(isAuthenticated());
      // Promo-flyer popup session marker — survives refresh (same sessionStore),
      // re-shows the flyer after a fresh login (login/register regenerate it).
      if (!sessionStore.getItem('hg_login_session')) sessionStore.setItem('hg_login_session', String(Date.now()));
      if (isAuthenticated()) {
        try {
          const profile = await loadSessionProfile();
          if (version !== restoreVersion.current || !isAuthenticated()) return;
          setUser(profile); persistUserCampus(profile);
          setHpBalance(normalizeHpBalance(profile));
          setWallet(profile.wallet || null);
          setAuthed(true);
          recoverWelcome(profile);
          // Unblock the UI immediately — fire background refreshes in
          // parallel so a slow/cold backend never traps the user behind a
          // full-screen spinner. Each one swallows its own errors.
          setIsLoading(false);
          // A hard refresh on /dashboard (or a staff page) renders that lazy
          // chunk the moment we unblock — warm it now, in parallel with the
          // refreshes, so the page is not waiting on its own JS.
          warmPostLoginChunks(profile?.role);
          Promise.allSettled([
            refreshCart(),
            refreshNotifications(),
            refreshHp(),
            refreshWallet(),
            refreshSavedItems(),
            liveApi.auth.getStreak().then(setStreak).catch(() => {}),
            loadSystemSettings().then(setSystemSettings).catch(() => {}),
            loadFeatureFlags().catch(() => {}),
            loadTiers().catch(() => {}),
          ]);
        } catch (e) {
          if (version !== restoreVersion.current) return;
          if (e.status === 401 || e.status === 403) {
            clearTokens();
            setAuthed(false);
            loadGuestCart();
          } else {
            setSessionError(e.message || msg('FE_SESSION_LOAD_FAILED', 'Your account could not be loaded. Please try again.'));
          }
          setIsLoading(false);
        }
      } else {
        loadGuestCart();
        setIsLoading(false);
        // Guests read public campus configuration for contact and feature UI.
        loadSystemSettings().then(setSystemSettings).catch(() => {});
        loadFeatureFlags().catch(() => {});
        loadTiers().catch(() => {});
      }
    };
    init();
    return () => { restoreVersion.current += 1; };
  }, [sessionAttempt]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const reloadScope = () => {
      if (!isAuthenticated()) loadGuestCart();
      loadSystemSettings().then(setSystemSettings).catch(() => {});
      loadFeatureFlags().catch(() => {});
    };
    window.addEventListener('hg:scope-changed', reloadScope);
    return () => window.removeEventListener('hg:scope-changed', reloadScope);
  }, [loadGuestCart]);

  const login = async (email, password) => {
    restoreVersion.current += 1;
    const data = await liveApi.auth.login({ email, password });
    const profile = await loadSessionProfile();
    setUser(profile); persistUserCampus(profile);
    setHpBalance(normalizeHpBalance(profile));
    setWallet(profile.wallet || null);
    setAuthed(true); setIsLoading(false); setSessionError(null);
    recoverWelcome(profile);
    // Fresh login → new session id so the promo-flyer popup re-shows.
    sessionStore.setItem('hg_login_session', String(Date.now()) + Math.random().toString(36).slice(2));
    // Migrate any guest cart items into the now-authenticated server cart.
    const guestItems = readGuestCart();
    if (guestItems.length) {
      const transfers = await Promise.allSettled(guestItems.map((ci) => liveApi.cart.add({ menu_item_id: ci.menu_item_id, quantity: ci.quantity, notes: ci.notes,
        selected_variations: ci.selected_variations || [], selected_addons: ci.selected_addons || [] })));
      const retained = guestItems.filter((_, index) => transfers[index].status === 'rejected');
      writeGuestCart(retained);
      if (retained.length) toast({ title: msg('FE_HOLY_GRILL_CONTEXT_SOME_GUEST_CART_ITEMS_COULD_NOT_BE_ADDED', 'Some guest cart items could not be added'),
        description: msg('FE_HOLY_GRILL_CONTEXT_YOUR_SAVED_GUEST_ITEMS_ARE_KEPT_ON_THIS', 'Your saved guest items are kept on this device. Check availability and your account campus before adding them again.'), variant: 'destructive' });
    }
    // Fire background refreshes in parallel — don't block the login redirect
    // on slow/cold backend calls. The user gets to their dashboard instantly.
    // Warm the destination chunk in the same breath, so the redirect lands on a
    // rendered page instead of the Suspense fallback.
    warmPostLoginChunks(profile?.role || data?.user?.role);
    Promise.allSettled([refreshCart(), refreshNotifications(), refreshHp(), refreshWallet(), refreshSavedItems(), liveApi.auth.getStreak().then(setStreak).catch(() => {}), loadSystemSettings().then(setSystemSettings).catch(() => {}), loadFeatureFlags().catch(() => {}), loadTiers().catch(() => {})]);
    return { ...data, role: profile.role || data?.user?.role || 'student' };
  };

  const register = async (body) => {
    const data = await liveApi.auth.register(body);
    // Backend returns { status: "check_email", message } when the account is
    // created but email verification is required before login. Don't call
    // /auth/me — there's no valid session yet. The Register page shows the
    // message as info (not an error) with login/reset links.
    if (data?.status === 'check_email') {
      return data;
    }
    const profile = await loadSessionProfile();
    setUser(profile); persistUserCampus(profile);
    setHpBalance(normalizeHpBalance(profile));
    setWallet(profile.wallet || null);
    setAuthed(true);
    sessionStore.setItem('hg_login_session', String(Date.now()) + Math.random().toString(36).slice(2));
    await refreshCart();
    return { ...data, role: profile.role || data?.user?.role || 'student' };
  };

  const logout = async () => {
    restoreVersion.current += 1; welcomeRecoveryUser.current = null;
    try { await liveApi.auth.logout(); } catch { /* ignore */ }
    clearTokens();
    localStore.removeItem('hg_admin_campus_id');
    localStore.removeItem('hg_admin_scope_all');
    localStore.removeItem('hg_user_campus_id');
    localStore.removeItem('hg_user_role');
    setUser(null); setHpBalance(null); setWallet(null);
    setNotifications([]); setUnreadCount(0); setStreak(null); setSavedItems([]);
    setAuthed(false);
    loadGuestCart();
  };

  const addToCart = async (body) => {
    if (isAuthenticated()) {
      await liveApi.cart.add(body);
      await refreshCart();
    } else {
      const items = readGuestCart();
      const it = await liveApi.menu.getItem(body.menu_item_id);
      const addons = await liveApi.menu.getAddons(body.menu_item_id);
      const variations = (body.selected_variations || []).map((v) => v.option_id || v.id || v);
      const selectedAddons = body.selected_addons || [];
      const variationPrice = (it.variation_groups || []).flatMap((g) => g.options || [])
        .filter((option) => variations.includes(option.id)).reduce((sum, option) => sum + Number(option.price_delta || 0), 0);
      const addonPrice = (addons.addon_groups || []).flatMap((g) => g.addons || g.options || [])
        .reduce((sum, addon) => sum + selectedAddons.filter((a) => (a.addon_id || a.id || a) === addon.id)
          .reduce((subtotal, a) => subtotal + Number(addon.price_delta || addon.price || 0) * Number(a.quantity || 1), 0), 0);
      const snap = { ...it, price: Number(it.price) + variationPrice + addonPrice, is_available: it.is_available !== false };
      const signature = (entry) => JSON.stringify({
        variations: (entry.selected_variations || []).map((v) => v.option_id || v.id || v).sort(),
        addons: (entry.selected_addons || []).map((a) => `${a.addon_id || a.id || a}:${a.quantity || 1}`).sort(), notes: entry.notes || '',
      });
      const existing = items.find((ci) => ci.menu_item_id === body.menu_item_id && signature(ci) === signature(body));
      if (existing) existing.quantity += body.quantity || 1;
      else items.push({ id: `gci_${crypto.randomUUID()}`, menu_item_id: body.menu_item_id, quantity: body.quantity || 1, notes: body.notes || '', selected_variations: body.selected_variations || [], selected_addons: body.selected_addons || [], menu_items: snap });
      writeGuestCart(items);
      loadGuestCart();
    }
  };

  const updateCartItem = async (itemId, body) => {
    if (isAuthenticated()) {
      await liveApi.cart.update(itemId, body);
      await refreshCart();
    } else {
      let items = readGuestCart();
      if (body.quantity === 0) items = items.filter((ci) => ci.id !== itemId);
      else { const it = items.find((ci) => ci.id === itemId); if (it) { if (body.quantity) it.quantity = body.quantity; if (body.notes !== undefined) it.notes = body.notes; } }
      writeGuestCart(items);
      loadGuestCart();
    }
  };

  const removeFromCart = async (itemId) => {
    if (isAuthenticated()) {
      await liveApi.cart.remove(itemId);
      await refreshCart();
    } else {
      writeGuestCart(readGuestCart().filter((ci) => ci.id !== itemId));
      loadGuestCart();
    }
  };

  const clearCart = async () => {
    cartRequestVersion.current += 1;
    if (isAuthenticated()) {
      await liveApi.cart.clear();
      setCart(EMPTY_CART); setCartCount(0);
      await refreshCart();
    } else {
      writeGuestCart([]);
      loadGuestCart();
    }
  };

  const markNotificationRead = async (id) => { await liveApi.notifications.markRead(id); await refreshNotifications(); };
  const markAllNotificationsRead = async () => { await liveApi.notifications.markAllRead(); await refreshNotifications(); };

  return (
    <HolyGrillContext.Provider value={{
      featureVersion, user, isLoading, cart, cartCount, hpBalance, wallet, notifications, unreadCount, streak, systemSettings, getSetting, getStringSetting, getBoolSetting,
      savedItems, isAuthenticated: authed,
      login, register, logout, refreshUser, refreshStreak, refreshCart, refreshHp, refreshWallet, refreshNotifications, refreshSavedItems,
      addToCart, updateCartItem, removeFromCart, clearCart,
      toggleSavedItem, removeSavedItem, moveSavedToCart, isSavedItem,
      markNotificationRead, markAllNotificationsRead,
    }}>
      {sessionError && publicPage && <div role="status" className="px-4 py-3 bg-secondary text-foreground text-sm flex flex-wrap items-center justify-center gap-3"><span>{msg('FE_HOLY_GRILL_CONTEXT_YOUR_SIGN_IN_IS_SAVED_TRY_LOADING_YOUR_ACCOUNT_A', "Your sign-in is saved. Try loading your account again.")}</span><button onClick={() => { setIsLoading(true); setSessionAttempt(attempt => attempt + 1); }} className="font-bold underline">{msg('FE_HOLY_GRILL_CONTEXT_RETRY_ACCOUNT', "Retry account")}</button></div>}
      {sessionError && !publicPage ? <div role="alert" className="min-h-screen flex flex-col items-center justify-center px-6 text-center gap-4 bg-background">
        <h1 className="font-heading font-bold text-xl">{msg('FE_HOLY_GRILL_CONTEXT_YOUR_ACCOUNT_IS_TEMPORARILY_UNAVAILABLE', "Your account is temporarily unavailable")}</h1>
        <p className="text-sm text-muted-foreground max-w-sm">{msg('FE_HOLY_GRILL_CONTEXT_YOUR_SIGN_IN_IS_SAVED_TRY_LOADING_YOUR_ACCOUNT_A', "Your sign-in is saved. Try loading your account again.")}</p>
        <button onClick={() => { setIsLoading(true); setSessionAttempt(attempt => attempt + 1); }} className="px-5 py-3 rounded-full bg-primary text-white font-bold">{msg('FE_HOLY_GRILL_CONTEXT_RETRY_ACCOUNT', "Retry account")}</button>
      </div> : children}
    </HolyGrillContext.Provider>
  );
};

export const useHolyGrill = () => {
  const ctx = useContext(HolyGrillContext);
  if (!ctx) throw new Error(msg('FE_HOLY_GRILL_CONTEXT_USE_HOLY_GRILL_MUST_BE_USED_WITHIN_HOLY', 'useHolyGrill must be used within HolyGrillProvider'));
  return ctx;
};
