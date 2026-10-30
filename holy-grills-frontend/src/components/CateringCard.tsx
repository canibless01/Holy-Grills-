import { useStorefrontContent } from '@/hooks/useStorefrontContent';
import StorefrontReadState from '@/components/storefront/StorefrontReadState';
import { useNavigate } from 'react-router-dom';
import { openCmsDestination } from '@/lib/safeNavigation';
import { useState } from 'react';
import BannerCard from '@/components/storefront/BannerCard';
import { bannerSpec } from '@/lib/bannerSpec';
import CateringRequestModal from '@/components/events/CateringRequestModal';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { msg } from '@/lib/messages';

/**
 * CateringCard — storefront-driven Catering card on the Home page, visible to
 * guests too. The content (image, title, description, CTA) comes from an admin-
 * uploaded storefront section of section_type='service' (see Confirmed Business
 * Logic · Catering). Renders nothing if no such section is configured.
 *
 * The CTA opens an inline request form that POSTs /events/catering-requests
 * (public submissions allowed).
 */
export default function CateringCard() {
  const { isAuthenticated } = useHolyGrill();
  const contentRead = useStorefrontContent('sections');
  const navigate = useNavigate();
  const currentSection = contentRead.data?.find(row => row.section_type === 'catering' && row.is_active !== false);
  const [showForm, setShowForm] = useState(false);
  const [formSection, setFormSection] = useState(null);
  const section = showForm ? formSection : currentSection;
  if (contentRead.isError && !contentRead.data) return <StorefrontReadState label="Catering" retry={() => void contentRead.refetch({ cancelRefetch: false })} />;
  if (!section) return null;

  const content = section?.content || section?.data || {};
  const image = content.image_url || content.image || section?.image_url;
  const title = content.title || section?.title || 'Your crowd. Our fire.';
  // The CMS form writes subtitle + cta_text; storefront.py merges both into
  // `content`, so those are the keys that actually arrive.
  const description = content.description || content.body || content.subtitle || section?.subtitle || 'Tell us the date.';
  const cta = content.cta_label || content.cta_text || content.cta || section?.cta_text || 'Request catering';

  return (
    <>
      <div id="catering" className="rounded-2xl overflow-hidden hover:shadow-glow transition-shadow">
        <BannerCard
          spec={bannerSpec('feature')}
          mode="text"
          image={image || ''}
          eyebrow={msg('FE_CATERING_EYEBROW', 'Catering')}
          title={title}
          line={description}
          actionLabel={cta}
          label={cta}
          onAction={() => {
            const destination = content.cta_url || content.cta_link || section?.cta_url;
            if (destination) openCmsDestination(destination, navigate);
            else { setFormSection(section); setShowForm(true); }
          }}
          footer={!isAuthenticated ? msg('FE_CATERING_NO_ACCOUNT_NEEDED', 'No account needed.') : null}
        />
      </div>

      <CateringRequestModal open={showForm} onClose={() => setShowForm(false)} />
    </>
  );
}