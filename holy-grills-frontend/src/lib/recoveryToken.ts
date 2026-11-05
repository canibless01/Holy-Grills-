/** Supabase implicit recovery redirects and legacy application reset links. */
export function recoveryToken(search: string, hash: string): string | null {
  const fragment = new URLSearchParams(hash.replace(/^#/, ''));
  if (fragment.has('error') || fragment.has('error_code')) return null;
  if (fragment.has('access_token')) {
    return fragment.get('type') === 'recovery' ? fragment.get('access_token') || null : null;
  }
  return new URLSearchParams(search).get('token') || null;
}
