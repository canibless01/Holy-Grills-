// Recover old notification display numbers using only orders already visible
// to the signed-in account or guest capabilities in this tab. Never guess a
// global order ID or relax the server's ownership check.
export function ownedOrderId(reference: string, orders: Array<{ id?: string }>): string | null {
  if (!/^[a-f0-9]{8}$/i.test(reference)) return null;
  const matches = [...new Set(orders.map(row => row.id).filter((id): id is string =>
    Boolean(id && id.toLowerCase().startsWith(reference.toLowerCase()))))];
  return matches.length === 1 ? matches[0] : null;
}
