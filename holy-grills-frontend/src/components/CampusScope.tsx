import { useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { useCampus } from '@/lib/campusContext';
import Skeleton from '@/components/Skeleton';
import CampusPickerLanding, { type CampusPickerCopy } from '@/components/CampusPickerLanding';

// Domain 0 — route guard for campus-scoped pages. Guests without a selected
// campus get the non-cancelable CampusGate (rendered globally by CampusProvider)
// and the page content is withheld until a campus is chosen. Authenticated
// users pass straight through (scoped by their own campus_id). Static pages
// (Home, FAQ, Terms, Our Story) are intentionally NOT wrapped here.
const ACTION_BY_PATH = {
  '/menu': 'browse the menu',
  '/cart': 'review your cart',
  '/checkout': 'place your order',
  '/events': 'see campus events',
  '/marketplace': 'open the marketplace',
  '/leaderboard': 'view the leaderboard',
};

// Track B, section 6 item 1: what a guest sees on a campus-scoped route before
// choosing a campus. This is also what the build-time pre-render writes into the
// HTML for /menu, /events and /marketplace, so those URLs carry real indexable
// content instead of an empty shell. Routes without copy here (cart, checkout)
// keep the old behaviour: a transactional page has nothing useful for a crawler.
const LANDING_BY_PATH: Record<string, CampusPickerCopy> = {
  '/menu': {
    title: "Today's menu at FUTA",
    intro:
      'Flame-grilled chicken, wings, kebabs and crispy sides, cooked to order and delivered across campus.',
    bullets: [
      'Live menu with prices and what is available right now',
      'Delivery to hostels and gates, or pickup from the grill',
      'Holy Points on every order, spendable on rewards',
    ],
  },
  '/events': {
    title: 'Campus events at FUTA',
    intro: 'Tickets, tiers and check-in for the events happening around campus.',
    bullets: [
      'Ticket tiers with live availability',
      'QR check-in on the day',
      'Holy Points for turning up',
    ],
  },
  '/marketplace': {
    title: 'The campus marketplace',
    intro: 'Vouchers, tickets, goodies and services listed by students and campus businesses.',
    bullets: [
      'Browse what is listed on your campus',
      'Buy and collect alongside your order',
      'Reporting built in for anything that looks wrong',
    ],
  },
  '/leaderboard': {
    title: 'The Holy Grills leaderboard',
    intro: 'Who is showing up, earning and climbing this term.',
    bullets: ['Weekly and all-time rankings', 'Top ten earners win free sides', 'Your rank and streak'],
  },
};

export default function CampusScope() {
  const { campusId, campuses, campusesLoading, requireCampus } = useCampus();
  const { pathname } = useLocation();
  const base = '/' + (pathname.split('/')[1] || '');
  const landing = LANDING_BY_PATH[base];

  useEffect(() => {
    requireCampus(ACTION_BY_PATH[base] || 'continue');
  }, [base, requireCampus]);

  if (campusId) return <Outlet />;

  // No campuses to choose (single-campus / no public list endpoint) — let the
  // backend fall back to global/unscoped data rather than trapping the guest.
  if (!campusesLoading && campuses.length === 0) return <Outlet />;

  // Either the campus list is still loading or the gate is open (it renders
  // globally, on top of this). A guest sees what the page is for either way.
  if (landing) return <CampusPickerLanding {...landing} />;
  if (campusesLoading) return (
    <div className="space-y-3 py-6">
      <Skeleton className="h-5 w-32" />
      <Skeleton className="h-10 w-full rounded-xl" />
      <Skeleton className="h-10 w-full rounded-xl" />
      <Skeleton className="h-10 w-full rounded-xl" />
    </div>
  );
  return null;
}