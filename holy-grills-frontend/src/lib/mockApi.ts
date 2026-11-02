// HolyGrills student API — wired to the live backend.
// `mockApi` is now a thin alias over `liveApi` (the real backend client at
// https://holygrills-production.up.railway.app/api), so every page that imports
// { mockApi } fetches live data. The in-memory simulation has been retired.
export { liveApi as mockApi } from './liveApi';