# Holy Grills — Sound & Micro-Interaction Spec

Authoritative mapping of **user action → sound name**. Every sound name is
defined in `src/lib/soundManager.js` (`SOUND_DEFS`). Wire each action to exactly
one sound; never double-fire (if a toast already passes `sound:`, do not also
call `play()` for the same moment).

## Rules
- One sound per moment. If a toast carries `sound: 'x'`, the calling code must
  NOT also `play('x')`.
- Sounds respect the global on/off toggle (`soundManager` / `SoundProvider`).
- Toasts use the `sound` prop on `toast({ ..., sound: 'cart_add' })` so the tone
  is owned by the toast and never clashes with a simultaneously fired sound.
- If a moment has no matching sound yet, add the definition to `soundManager.js`
  rather than reusing an unrelated one.

## Action → Sound

### Cart & ordering
| Action | Sound |
|---|---|
| Add item to cart | `cart_add` |
| Remove item from cart | `cart_remove` |
| Order placed / confirmed | `order_placed` |
| Order status changes | `order_status` |
| First-order gift unlocked | `first_order` |

### Holy Points
| Action | Sound |
|---|---|
| HP earned (any source) | `hp_earned` |
| Tier upgrade | `tier_upgrade` |
| HP transfer sent | `hp_transfer_sent` |
| HP transfer received | `hp_transfer_received` |
| Badge unlocked | `badge_unlock` |
| Set/badge collection completed | `set_completed` |

### Streaks & check-ins
| Action | Sound |
|---|---|
| Daily check-in | `streak_milestone` |
| Login streak milestone | `streak_milestone` |

### Spin & Win
| Action | Sound |
|---|---|
| Spin starts / spinning | `spin_spinning` |
| Spin win | `spin_win` |
| Spin no-win | `spin_no_win` |

### Leaderboard & events
| Action | Sound |
|---|---|
| Leaderboard rank up | `leaderboard_up` |
| Review submitted | `review_submitted` |

### Notifications
| Action | Sound |
|---|---|
| Push notification received (in-app) | `push_received` |

## Notes for wiring
- All add-to-cart buttons → `cart_add` (currently via the toast `sound` prop on
  Home; other pages should match).
- All remove-from-cart actions → `cart_remove`.
- Spin wheel: play `spin_spinning` while spinning, then `spin_win` or
  `spin_no_win` on result.
- Keep toasts as the single sound owner when a toast accompanies the action.