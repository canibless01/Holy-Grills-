// Storefront section helpers — backend-only, no mock fallback.
// The admin creates real sections in the storefront admin panel; these helpers
// fetch them from the live API. If the backend returns nothing for a type, the
// corresponding slider/card simply renders nothing (honest empty state).
import { liveApi } from './liveApi';

// Fetch live storefront sections for a type — backend-only, no mock fallback.
export async function getStorefrontSections(sectionType) {
  const list = await liveApi.storefront.getSections({ section_type: sectionType });
  // Always filter client-side too — some backend deployments ignore the
  // section_type query param and return every section, which would mix types.
  return (Array.isArray(list) ? list : []).filter((s) => s.section_type === sectionType);
}

// Early supporters — backend-only, no mock fallback.
export async function getEarlySupporters() {
  const list = await liveApi.storefront.getEarlySupporters();
  return Array.isArray(list) ? list : [];
}