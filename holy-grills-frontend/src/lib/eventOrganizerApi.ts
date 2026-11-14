import { apiClient } from './apiClient';
const root = '/event-organizer/events';
export const eventOrganizerApi = {
  list: (params = {}) => apiClient.get(root, params),
  create: (body) => apiClient.post(root, body),
  edit: (id, body) => apiClient.patch(`${root}/${id}`, body),
  account: (id) => apiClient.get(`${root}/${id}`),
  submit: (id) => apiClient.post(`${root}/${id}/submit`, {}),
  change: (id, body) => apiClient.post(`${root}/${id}/change`, body, { timeoutMs: 45000 }),
  review: (id, body) => apiClient.post(`${root}/${id}/review`, body),
  attendees: (id, params = {}) => apiClient.get(`${root}/${id}/attendees`, params),
  export: (id) => apiClient.get(`${root}/${id}/attendees/export`),
  doorQr: (id) => apiClient.post(`${root}/${id}/door-qr`, {}),
  checkin: (id, qr_token) => apiClient.post(`${root}/${id}/checkin`, { qr_token }),
  requestPayout: (id, body) => apiClient.post(`${root}/${id}/payouts`, body),
  payout: (id, requestId, body) => apiClient.post(`${root}/${id}/payouts/${requestId}`, body),
};
