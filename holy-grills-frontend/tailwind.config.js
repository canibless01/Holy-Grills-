/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx,js,jsx}"],
  theme: {
    extend: {
      /* ── CORNER-RADIUS — from central --radius-* tokens ──
         rounded-lg / sm / md  = inputs, badges (8px scale)
         rounded-menu          = menu / item / reward cards (16px)
         rounded-detail        = detail-page cards (12px)
         rounded-button        = buttons, other pages (30px)
         rounded-button-home   = buttons, homepage only (12px)
         rounded-pill          = pills, tabs (9999px) */
      borderRadius: {
        sm: 'calc(var(--radius-sm) - 4px)',
        md: 'calc(var(--radius-sm) - 2px)',
        lg: 'var(--radius-sm)',
        xl: 'var(--radius-detail-card)',   /* 12px */
        '2xl': 'var(--radius-menu-card)',  /* 16px */
        '3xl': 'var(--radius-lg)',          /* 24px */
        menu: 'var(--radius-menu-card)',    /* 16px */
        detail: 'var(--radius-detail-card)',/* 12px */
        button: 'var(--radius-button)',     /* 30px */
        'button-home': 'var(--radius-button-home)', /* 12px */
        pill: 'var(--radius-pill)',
      },
      /* ── SPACING — named tokens pulled from --space-* vars ── */
      spacing: {
        xs:  'var(--space-xs)',
        sm:  'var(--space-sm)',
        md:  'var(--space-md)',
        lg:  'var(--space-lg)',
        xl:  'var(--space-xl)',
        '2xl': 'var(--space-2xl)',
      },
      /* ── SHADOWS — per design spec (tokens in index.css) ── */
      boxShadow: {
        glow: 'var(--shadow-glow)',
        card: 'var(--shadow-card)',
        tab: 'var(--shadow-tab)',
      },
      /* ── FONT WEIGHTS — full Nunito range (300–900) per design spec ── */
      fontWeight: {
        thin:     '300',
        light:    '300',
        normal:   '400',
        medium:   '500',
        semibold: '600',
        bold:     '700',
        extrabold:'800',
        black:    '900',
      },
      colors: {
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))'
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))'
        },
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))'
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))'
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))'
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))'
        },
        'brand-brown': 'hsl(var(--brand-brown))',
        beige: 'hsl(var(--beige))',
        'beige-soft': 'hsl(var(--beige-soft))',
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))'
        },
        success: {
          DEFAULT: 'hsl(var(--success))',
          foreground: 'hsl(var(--success-foreground))'
        },
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',

        chart: {
          '1': 'hsl(var(--chart-1))',
          '2': 'hsl(var(--chart-2))',
          '3': 'hsl(var(--chart-3))',
          '4': 'hsl(var(--chart-4))',
          '5': 'hsl(var(--chart-5))'
        },
        sidebar: {
          DEFAULT: 'hsl(var(--sidebar-background))',
          foreground: 'hsl(var(--sidebar-foreground))',
          primary: 'hsl(var(--sidebar-primary))',
          'primary-foreground': 'hsl(var(--sidebar-primary-foreground))',
          accent: 'hsl(var(--sidebar-accent))',
          'accent-foreground': 'hsl(var(--sidebar-accent-foreground))',
          border: 'hsl(var(--sidebar-border))',
          ring: 'hsl(var(--sidebar-ring))'
        }
      },
      fontFamily: {
        heading: ['var(--font-heading)'],
        body: ['var(--font-body)'],
        display: ['var(--font-display)'],
        mono: ['var(--font-mono)']
      },
      keyframes: {
        'accordion-down': {
          from: { height: '0' },
          to: { height: 'var(--radix-accordion-content-height)' }
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to: { height: '0' }
        },
        'flame-flicker': {
          '0%, 100%': { transform: 'scale(1) rotate(-1deg)', opacity: '1' },
          '50%': { transform: 'scale(1.05) rotate(1deg)', opacity: '0.9' }
        },
        'flame-rise': {
          '0%': { transform: 'translateY(0) scale(1)', opacity: '0' },
          '20%': { opacity: '1' },
          '100%': { transform: 'translateY(-40px) scale(0.5)', opacity: '0' }
        },
        'slide-up': {
          from: { transform: 'translateY(20px)', opacity: '0' },
          to: { transform: 'translateY(0)', opacity: '1' }
        },
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' }
        },
        'count-up': {
          from: { transform: 'scale(0.8)', opacity: '0' },
          to: { transform: 'scale(1)', opacity: '1' }
        },
        'pulse-ring': {
          '0%': { transform: 'scale(1)', opacity: '1' },
          '100%': { transform: 'scale(2)', opacity: '0' }
        },
        'shimmer': {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' }
        },
        'ken-burns': {
          '0%': { transform: 'scale(1) translate(0, 0)' },
          '50%': { transform: 'scale(1.12) translate(-1%, -1%)' },
          '100%': { transform: 'scale(1) translate(0, 0)' }
        },
        'hp-pop': {
          '0%': { transform: 'scale(1)' },
          '40%': { transform: 'scale(1.3) rotate(8deg)' },
          '100%': { transform: 'scale(1)' }
        },
        'bar-rise': {
          '0%': { transform: 'scaleY(0)' },
          '100%': { transform: 'scaleY(1)' }
        },
        'wiggle': {
          '0%, 100%': { transform: 'rotate(0deg)' },
          '25%': { transform: 'rotate(-3deg)' },
          '75%': { transform: 'rotate(3deg)' }
        }
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
        'flame-flicker': 'flame-flicker 2s ease-in-out infinite',
        'flame-rise': 'flame-rise 1.5s ease-out infinite',
        'slide-up': 'slide-up 0.4s ease-out',
        'fade-in': 'fade-in 0.3s ease-out',
        'count-up': 'count-up 0.5s ease-out',
        'pulse-ring': 'pulse-ring 1.5s ease-out infinite',
        'shimmer': 'shimmer 2s linear infinite',
        'ken-burns': 'ken-burns 12s ease-in-out infinite',
        'hp-pop': 'hp-pop 0.4s ease-out',
        'bar-rise': 'bar-rise 0.6s cubic-bezier(0.34, 1.56, 0.64, 1)',
        'wiggle': 'wiggle 0.5s ease-in-out'
      }
    }
  },
  plugins: [require("tailwindcss-animate")],
}
