/** Directions use the customer's saved pin, without assuming a campus/city. */
export function riderNavigationUrl(order) {
  const address = order?.delivery_address_snapshot || order?.delivery_address;
  const coordinate = (value, max) => {
    if (!['number', 'string'].includes(typeof value) || (typeof value === 'string' && !value.trim())) return null;
    const number = Number(value);
    return Number.isFinite(number) && Math.abs(number) <= max ? number : null;
  };
  const lat = coordinate(order?.delivery_location_lat ?? address?.lat ?? address?.latitude, 90);
  const lon = coordinate(order?.delivery_location_lon ?? address?.lng ?? address?.lon ?? address?.longitude, 180);
  const label = typeof address === 'string' ? address.trim() :
    [address?.line1, address?.address, address?.street, address?.landmark, address?.hostel_name,
      address?.hostel, address?.room, address?.gate_name]
      .filter(value => typeof value === 'string' && value.trim()).join(', ')
      || (typeof order?.delivery_address === 'string' ? order.delivery_address.trim() : '');
  const destination = lat !== null && lon !== null ? `${lat},${lon}` : label;
  return destination ? `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(destination)}` : null;
}
