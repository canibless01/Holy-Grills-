# Sound Moments Map — Holy Grills

One page listing every moment that makes a sound, the sound it makes, and
where it's wired. All sounds are synthesized in `src/lib/soundManager.ts`
(no audio files), respect the device's hardware silent switch, and obey the
master toggle (Profile → Sound, persisted in `localStorage`).

Rule of thumb (from the original spec): **if the moment matters to the
student, amplify it. If it is functional and routine, keep it quiet.**

| Moment | Sound | Wired in |
|---|---|---|
| Item added to cart | `cart_add` | Menu/ItemDetail/Home quick-add |
| Item removed from cart | `cart_remove` | Cart |
| Order placed (student) | `order_placed` | Checkout → confirmation |
| Confirmation screen loads (paid) | `order_placed` + `hp_earned` + mascot | OrderConfirmation |
| Holy Points earned from order | `hp_earned` | OrderConfirmation |
| Order status changed | `order_status` | OrderDetail / messages |
| New order lands in kitchen queue | `order_placed` + card flash | Kitchen (`useKitchenData` poll) |
| New batch / order added for rider | `push_received` | Rider (`useRiderData` poll) |
| Push notification arrives | `push_received` | messages |
| Spin opened (idle, can spin) | `spin_idle` | SpinWheel |
| Spin in motion | `spin_spinning` | SpinWheel |
| Spin won | `spin_win` + confetti | SpinWheel |
| Spin lost | `spin_no_win` | SpinWheel |
| Badge/challenge unlocked | `badge_unlock` | Challenges / Rewards |
| Tier upgraded | `tier_upgrade` | HP context |
| Streak milestone hit | `streak_milestone` | Streak |
| Leaderboard rank improved | `leaderboard_up` + hips mascot | Leaderboard |
| HP transfer sent / received | `hp_transfer_sent` / `hp_transfer_received` | Transfer modal |
| First order completed | `first_order` | OrderConfirmation |
| Review submitted | `review_submitted` | OrderDetail review |

## Adding a new moment

1. Reuse an existing sound name from `SOUND_DEFS` unless the moment genuinely
   has no match (then add a `tone()` schedule — keep gains ≤ 0.2, keep it
   short).
2. Play it through `useSound().play(name)` (components) or
   `playSound(name)` (helpers/hooks) — never raw Web Audio.
3. Add the row to this table.
