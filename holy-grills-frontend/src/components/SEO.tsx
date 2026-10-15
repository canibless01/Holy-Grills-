/**
 * Holy Grill — <SEO /> declarative component
 * Wraps useSEO so pages can drop a single tag at the top:
 *
 *   <SEO title="Menu" description="Browse the flame-grilled menu" />
 *
 * Renders nothing — purely a head manager. See BUILDER_RULES.md.
 */
import useSEO from '@/hooks/useSEO';

export default function SEO(props) {
  useSEO(props);
  return null;
}