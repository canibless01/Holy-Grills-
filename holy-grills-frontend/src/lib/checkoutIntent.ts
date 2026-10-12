/** The persisted cart-row IDs distinguish a new basket from a retry in any tab. */
export async function checkoutIntent(fingerprint: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(JSON.stringify(fingerprint));
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return 'checkout-' + Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('');
}
