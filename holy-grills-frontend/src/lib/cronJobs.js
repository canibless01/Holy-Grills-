// Known Celery beat jobs — mirrors the backend's app/tasks/celery_app.py
// beat_schedule + the @with_cron_logging job names in app/tasks/scheduled.py.
//
// The backend's GET /admin/cron/status may return a partial/hardcoded list
// that lags behind the real beat schedule. This registry is merged with the
// backend response in liveApi.admin.getCronStatus so the admin panel always
// shows every triggerable job — even ones the backend's status endpoint
// doesn't know about yet. Triggering still hits POST /admin/cron/:job, so the
// job name here MUST match the celery task's @with_cron_logging name exactly.
export const KNOWN_CRON_JOBS = [
  { job: 'reset-monthly-leaderboard', cadence: '1st of month · 00:01 WAT', desc: 'Archive top 10 to Hall of Fame, reset monthly HP, snapshot' },
  { job: 'recalculate-120day-hp', cadence: 'Daily · 02:00 WAT', desc: 'Recompute hp_earned_120day + tier recalc for all users' },
  { job: 'tier-grace-period-check', cadence: 'Daily · 03:00 WAT', desc: 'Start/drop grace periods for users below tier maintenance' },
  { job: 'hp-decay-check', cadence: 'Daily · 05:00 WAT', desc: '10%/month HP decay after 120 days inactivity' },
  { job: 'membership-anniversary-awards', cadence: 'Daily · 06:00 WAT', desc: 'Award HP on 3/6/12/24/36/48/60-month milestones' },
  { job: 'birthday-hp', cadence: 'Daily · 08:00 WAT', desc: 'Award birthday HP + faculty peer blast' },
  { job: 'check-order-locks', cadence: 'Daily · 09:00 WAT', desc: 'Send lock reminders (10/7/3/1 days) + expire stale locks' },
  { job: 'win-back-notifications', cadence: 'Daily · 10:00 WAT', desc: 'Dormancy win-back at day 70/95/118' },
  { job: 'reset-monthly-hp-tracker', cadence: '1st of month · 00:05 WAT', desc: 'Clear monthly_hp_tracker for the new month' },
  { job: 'grant-monthly-tier-perks', cadence: '1st of month · 00:05 WAT', desc: 'Grant monthly tier free-side credits + exclusive spins' },
  { job: 'monthly-birthday-report', cadence: '1st of month · 07:00 WAT', desc: 'Send admins the month\'s birthday list (in-app + email)' },
  { job: 'process-scheduled-orders', cadence: 'Every 5 min', desc: 'Notify kitchen when scheduled order delivery window arrives' },
  { job: 'send-scheduled-notifications', cadence: 'Every 15 min', desc: 'Deliver due scheduled notification campaigns' },
  { job: 'scan-abandoned-carts', cadence: 'Every 30 min', desc: 'Flag carts idle 60+ min as abandoned + notify' },
  { job: 'check-post-delivery-nudges', cadence: 'Every 30 min', desc: 'Satisfaction check (2h) + re-engagement nudge (24h)' },
];

export const KNOWN_CRON_MAP = Object.fromEntries(KNOWN_CRON_JOBS.map((j) => [j.job, j]));