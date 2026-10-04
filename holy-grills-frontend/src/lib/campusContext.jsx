import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { liveApi } from './liveApi';
import { useHolyGrill } from './HolyGrillContext';
import CampusGate from '@/components/CampusGate';
import { useLocation } from 'react-router-dom';

// Domain 0 — Multi-Campus / Multi-Tenant frontend layer.
// Students never switch campus after registration; guests get a one-time,
// non-cancelable campus-selection gate before any campus-scoped action
// (menu, events, checkout, marketplace, leaderboard). The selection persists
// for the session and is sent as the X-Campus-ID header on guest requests
// (Mechanism 1). Authenticated users are scoped server-side by their own
// campus_id in the JWT, so no header is sent for them.

const CAMPUS_KEY = 'hg_campus_id';
const ADMIN_CAMPUS_KEY = 'hg_admin_campus_id';
const CampusContext = createContext();

export const getStoredCampusId = () => localStorage.getItem(CAMPUS_KEY);
export const getStoredAdminCampusId = () => localStorage.getItem(ADMIN_CAMPUS_KEY);

export const CampusProvider = ({ children }) => {
  const { user, isLoading } = useHolyGrill();
  const [campuses, setCampuses] = useState([]);
  const [campusesLoading, setCampusesLoading] = useState(true);
  const [guestCampusId, setGuestCampusId] = useState(getStoredCampusId());
  const [adminCampusId, setAdminCampusId] = useState(getStoredAdminCampusId());
  const [gateOpen, setGateOpen] = useState(false);
  const [gateAction, setGateAction] = useState('continue');
  // 'prompt' — dismissible (homepage only). 'blocking' — campus-scoped routes.
  const [gateMode, setGateMode] = useState('prompt');
  const [gateDismissed, setGateDismissed] = useState(false);
  const location = useLocation();

  // Authenticated users are scoped by their own campus_id (set at registration,
  // never changeable — auth_service.update_profile drops campus_id). Guests
  // use the localStorage selection from the gate. Super-admins can override
  // their own campus via the admin campus selector (hg_admin_campus_id).
  const campusId = user?.campus_id || guestCampusId || null;
  const campus = campuses.find((c) => c.id === campusId) || null;
  const adminCampus = campuses.find((c) => c.id === adminCampusId) || null;

  useEffect(() => {
    // Public campus list — campuses RLS allows everyone to select. If the
    // public endpoint is absent (single-campus launch) this resolves to an
    // empty list and the gate never activates (guests browse global data).
    liveApi.campuses
      .list()
      .then((c) => { setCampuses(c); setCampusesLoading(false); })
      .catch(() => { setCampuses([]); setCampusesLoading(false); });
  }, []);

  // Guests get a dismissible campus prompt once on the homepage — it must
  // never block browsing the storefront. Campus-scoped routes open the
  // non-cancelable gate via requireCampus. Once dismissed, the prompt stays
  // away until the user hits a campus-scoped page.
  // The gate keys off the real `user` object, not a raw token check. A token can
  // linger in storage after expiry or before the profile loads, so isAuthenticated()
  // is unreliable and would flash the gate at logged-in users. `user` is only set
  // after a successful /auth/me — it is null exactly when the header shows the
  // "Sign In" button, so this mirrors what the guest actually sees.
  useEffect(() => {
    // Skip the prompt on the guest order-tracking page — tracking by code is
    // campus-agnostic, so a guest shouldn't be forced to pick a campus to reach
    // the tracking box. Campus-scoped pages still open the blocking gate.
    if (isLoading || campusesLoading) return;
    if (!user && !guestCampusId && campuses.length > 0 && !gateOpen && !gateDismissed && !location.pathname.startsWith('/track-orders')) {
      setGateAction('continue');
      setGateMode('prompt');
      setGateOpen(true);
    }
  }, [isLoading, campusesLoading, user, guestCampusId, campuses, gateOpen, gateDismissed, location.pathname]);

  // The dismissible homepage prompt can follow a guest onto the tracking page
  // (the effect above only runs on mount). Close it whenever the guest reaches
  // /track-orders so the tracking box is never covered. The blocking gate only
  // fires on campus-scoped routes via requireCampus, which track-orders is not.
  useEffect(() => {
    if (location.pathname.startsWith('/track-orders') && gateOpen && gateMode === 'prompt') {
      setGateOpen(false);
    }
  }, [location.pathname, gateOpen, gateMode]);

  const selectCampus = useCallback((id) => {
    if (id) localStorage.setItem(CAMPUS_KEY, id); else localStorage.removeItem(CAMPUS_KEY);
    setGuestCampusId(id);
    setGateOpen(false);
  }, []);

  // Super-admin campus switch — persists across admin sessions and is sent
  // as X-Campus-ID by apiClient for all authenticated admin requests.
  const selectAdminCampus = useCallback((id) => {
    if (id) localStorage.setItem(ADMIN_CAMPUS_KEY, id); else localStorage.removeItem(ADMIN_CAMPUS_KEY);
    setAdminCampusId(id);
  }, []);

  const clearAdminCampus = useCallback(() => {
    localStorage.removeItem(ADMIN_CAMPUS_KEY);
    setAdminCampusId(null);
  }, []);

  // Called by campus-scoped routes before rendering campus data. Returns true
  // when a campus is resolved; opens the non-cancelable gate when it isn't.
  const requireCampus = useCallback((action = 'continue') => {
    // While auth is still resolving (profile fetch in flight) don't open the
    // gate — a logged-in user's `user` object is null for a brief window after
    // load. CampusScope re-runs this via its effect dep once `user` lands.
    if (isLoading) return true;
    // Logged-in users (a real `user` object) are scoped server-side by their own
    // campus_id — never gate them. Guests who already chose a campus pass through.
    if (user || user?.campus_id || guestCampusId) return true;
    setGateAction(action);
    setGateMode('blocking');
    setGateOpen(true);
    return false;
  }, [isLoading, user, guestCampusId]);

  // Homepage dismissal — closes the prompt without a selection; the next
  // campus-scoped page re-opens it in blocking mode.
  const dismissGate = useCallback(() => {
    setGateDismissed(true);
    setGateOpen(false);
  }, []);

  return (
    <CampusContext.Provider value={{
      campusId, campus, campuses, campusesLoading,
      gateOpen, gateAction, gateMode, selectCampus, requireCampus, setGateOpen,
      dismissGate,
      adminCampusId, adminCampus, selectAdminCampus, clearAdminCampus,
    }}>
      {children}
      <CampusGate />
    </CampusContext.Provider>
  );
};

export const useCampus = () => {
  const ctx = useContext(CampusContext);
  if (!ctx) throw new Error('useCampus must be used within CampusProvider');
  return ctx;
};