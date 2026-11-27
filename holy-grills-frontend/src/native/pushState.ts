/** Small shared state; web pages never need to load the native OneSignal SDK. */
export const nativePushState: { registered: boolean; permission: NotificationPermission } = {
  registered: false, permission: 'default',
};
