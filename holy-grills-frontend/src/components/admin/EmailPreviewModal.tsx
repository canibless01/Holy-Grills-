import { X } from 'lucide-react';
import type { CTABlock } from './CTABlockEditor';
import type { ImageBlock } from './ImageStackEditor';

interface EmailPreviewModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  bodyHtml: string;
  images: ImageBlock[];
  ctaBlocks: CTABlock[];
}

/**
 * EmailPreviewModal — live preview of the email that will be sent.
 * Renders the email with brand styling, images, and CTA buttons.
 */
export default function EmailPreviewModal({ open, onClose, title, bodyHtml, images, ctaBlocks }: EmailPreviewModalProps) {
  if (!open) return null;

  const brandRed = '#E01616';
  const brandRedHover = '#B81212';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="relative w-full max-w-2xl max-h-[90vh] overflow-hidden bg-card rounded-2xl border border-border shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h2 className="font-bold text-lg text-foreground">Email Preview</h2>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-secondary transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Email Preview */}
        <div className="overflow-y-auto max-h-[calc(90vh-80px)] p-6" style={{ backgroundColor: '#FFF5F0' }}>
          <div style={{
            maxWidth: '600px',
            margin: '0 auto',
            backgroundColor: '#FFFFFF',
            borderRadius: '16px',
            border: '1px solid rgba(0,0,0,0.08)',
            overflow: 'hidden',
            boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
          }}>
            {/* Header with wordmark */}
            <div style={{ padding: '32px 40px 24px', textAlign: 'center' }}>
              <img
                src="https://holygrills.online/brand/wordmark.png"
                alt="Holy Grills"
                style={{ maxWidth: '180px', height: 'auto' }}
              />
            </div>

            {/* Divider */}
            <div style={{ padding: '0 40px' }}>
              <div style={{
                height: '1px',
                background: 'linear-gradient(to right, transparent, rgba(0,0,0,0.1), transparent)',
              }} />
            </div>

            {/* Images */}
            {images.length > 0 && (
              <div style={{ padding: '24px 40px 0' }}>
                {images.map((image) => (
                  <div key={image.id} style={{ marginBottom: '16px' }}>
                    {image.link ? (
                      <a href={image.link} target="_blank" rel="noopener noreferrer">
                        <img
                          src={image.url}
                          alt={image.alt}
                          style={{
                            width: '100%',
                            height: 'auto',
                            borderRadius: '12px',
                            display: 'block',
                          }}
                        />
                      </a>
                    ) : (
                      <img
                        src={image.url}
                        alt={image.alt}
                        style={{
                          width: '100%',
                          height: 'auto',
                          borderRadius: '12px',
                          display: 'block',
                        }}
                      />
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Content */}
            <div style={{ padding: '32px 40px' }}>
              {/* Greeting */}
              <p style={{
                margin: '0 0 16px 0',
                fontSize: '18px',
                color: '#1A1A1A',
              }}>
                Hello there 👋
              </p>

              {/* Title */}
              <h1 style={{
                margin: '0 0 20px 0',
                fontSize: '28px',
                fontWeight: 700,
                color: '#1A1A1A',
                lineHeight: 1.3,
              }}>
                {title}
              </h1>

              {/* Body HTML */}
              <div
                style={{
                  margin: '0 0 24px 0',
                  fontSize: '16px',
                  lineHeight: 1.6,
                  color: '#1A1A1A',
                }}
                dangerouslySetInnerHTML={{ __html: bodyHtml }}
              />

              {/* CTA Buttons */}
              {ctaBlocks.length > 0 && (
                <table style={{ margin: '0 0 24px 0' }}>
                  <tbody>
                    <tr>
                      {ctaBlocks.map((cta) => {
                        const isPrimary = cta.style === 'primary';
                        const bgColor = isPrimary ? brandRed : 'transparent';
                        const textColor = isPrimary ? '#FFFFFF' : brandRed;
                        const border = isPrimary ? 'none' : `2px solid ${brandRed}`;

                        return (
                          <td key={cta.id} style={{ padding: '0 8px 8px 0' }}>
                            <table>
                              <tbody>
                                <tr>
                                  <td style={{
                                    borderRadius: '12px',
                                    backgroundColor: bgColor,
                                    border,
                                  }}>
                                    <a
                                      href={cta.url}
                                      style={{
                                        display: 'inline-block',
                                        padding: '14px 28px',
                                        fontSize: '16px',
                                        fontWeight: 600,
                                        color: textColor,
                                        textDecoration: 'none',
                                        borderRadius: '12px',
                                      }}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                    >
                                      {cta.label || 'Click here'}
                                    </a>
                                  </td>
                                </tr>
                              </tbody>
                            </table>
                          </td>
                        );
                      })}
                    </tr>
                  </tbody>
                </table>
              )}

              {/* Sign-off — fixed brand line shared with the backend email builders */}
              <p style={{
                margin: '32px 0 0 0',
                fontSize: '16px',
                fontWeight: 600,
                color: '#1A1A1A',
              }}>
                Made with more than flame ❤️‍🔥, Holy Grills Team.
              </p>
            </div>

            {/* Footer */}
            <div style={{
              backgroundColor: '#F5F5F5',
              borderTop: '1px solid rgba(0,0,0,0.08)',
              padding: '32px 40px',
              textAlign: 'center',
            }}>
              <p style={{
                margin: '0 0 12px 0',
                fontSize: '14px',
                color: '#666666',
              }}>
                Thank you for being part of our community!
              </p>
              <p style={{
                margin: '0 0 12px 0',
                fontSize: '14px',
                color: '#666666',
              }}>
                <a
                  href="mailto:support@holygrills.online"
                  style={{ color: brandRed, textDecoration: 'none' }}
                >
                  support@holygrills.online
                </a>
              </p>
              <p style={{
                margin: 0,
                fontSize: '12px',
                color: '#666666',
              }}>
                Copyright © 2026 Holy Grills. All rights reserved.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
