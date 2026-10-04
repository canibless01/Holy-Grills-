/**
 * Holy Grill — Central Icon Registry
 * ============================================================================
 * Single source for every icon used in the app. Import icons from here, NOT
 * directly from lucide-react:
 *
 *   import { ICONS, ICON_SIZES } from '@/config/icons';
 *   const { Flame, ShoppingCart } = ICONS;
 *
 * When you need a new lucide icon, add it to the ICONS map below first. This
 * keeps the full icon set auditable and prevents duplicate/inconsistent usage.
 *
 * Icon size is ALWAYS one of ICON_SIZES — never pass arbitrary pixel values.
 *
 * NOTE: this file is plain JS (no JSX) so it stays valid as a `.js` module —
 * the two brand icons below are built with React.createElement for that reason.
 * ============================================================================
 */
import React from 'react';
import {
  Flame, ShoppingCart, Bell, User, ChevronDown, ChevronRight, ChevronLeft,
  Wallet, MapPin, Settings, Gift, LogOut, Home, Menu, X, Plus, Minus, Trash2,
  LayoutDashboard, ClipboardList, Award, Star, Heart, Search, Filter, Clock,
  Truck, Bike, Check, CheckCircle2, AlertCircle, Info, ArrowRight, ArrowLeft,
  ArrowUp, ArrowDown, RefreshCw, Loader2, Eye, EyeOff, Lock, Unlock, Crown,
  Trophy, Sparkles, Zap, Calendar, MapPinned, Phone, Mail, Share2, Copy,
  Download, Image, Package, Tag, Percent, Coins, TrendingUp, TrendingDown,
  CircleDot, MoreVertical, MoreHorizontal, Pencil, Edit, Save, Upload,
  MessageSquare, ThumbsUp, Shield, ShieldCheck, Ban, Pause, Play, RotateCw,
  Send, ExternalLink, ChevronUp, ShoppingBag, Utensils, Egg, Drumstick,
  Cookie, IceCream, Leaf, Wheat, Coffee,
} from 'lucide-react';

export const ICONS = {
  Flame, ShoppingCart, Bell, User, ChevronDown, ChevronRight, ChevronLeft,
  Wallet, MapPin, Settings, Gift, LogOut, Home, Menu, X, Plus, Minus, Trash2,
  LayoutDashboard, ClipboardList, Award, Star, Heart, Search, Filter, Clock,
  Truck, Bike, Check, CheckCircle2, AlertCircle, Info, ArrowRight, ArrowLeft,
  ArrowUp, ArrowDown, RefreshCw, Loader2, Eye, EyeOff, Lock, Unlock, Crown,
  Trophy, Sparkles, Zap, Calendar, MapPinned, Phone, Mail, Share2, Copy,
  Download, Image, Package, Tag, Percent, Coins, TrendingUp, TrendingDown,
  CircleDot, MoreVertical, MoreHorizontal, Pencil, Edit, Save, Upload,
  MessageSquare, ThumbsUp, Shield, ShieldCheck, Ban, Pause, Play, RotateCw,
  Send, ExternalLink, ChevronUp, ShoppingBag, Utensils, Egg, Drumstick,
  Cookie, IceCream, Leaf, Wheat, Coffee,
};

// Canonical icon sizes — use these everywhere for visual consistency.
export const ICON_SIZES = {
  xs: 14,
  sm: 16,
  md: 18,
  lg: 20,
  xl: 24,
  '2xl': 32,
  '3xl': 48,
};

export const ICON_STROKE = {
  light: 1.5,
  normal: 2,
  bold: 2.5,
};

/**
 * Custom Holy Grill brand icons not available in lucide.
 * Built with React.createElement so this module stays valid without JSX.
 */

// HP (Holy Points) flame-coin icon.
export const HpIcon = ({ size = 20, className = '', ...props }) =>
  React.createElement(
    'svg',
    { viewBox: '0 0 24 24', width: size, height: size, className, fill: 'none', ...props },
    React.createElement('circle', { key: 'bg', cx: 12, cy: 12, r: 10, fill: '#FF6B1A' }),
    React.createElement('circle', { key: 'ring', cx: 12, cy: 12, r: 10, stroke: '#FF4E2D', strokeWidth: 1.5, fill: 'none' }),
    React.createElement('path', {
      key: 'flame',
      d: 'M12 6c-1.5 2-2.2 3.3-1.8 5 .25 1.1.9 1.7 1.8 2.4.9-.7 1.55-1.3 1.8-2.4.4-1.7-.3-3-1.8-5z',
      fill: '#fff',
    }),
    React.createElement(
      'text',
      { key: 'label', x: 12, y: 16.5, textAnchor: 'middle', fontSize: 6, fontWeight: 800, fill: '#fff', fontFamily: 'Sora, sans-serif' },
      'HP'
    )
  );

// Tier badge icon — pass tier name to pick the ring color.
export const TierBadge = ({ tier = 'Ember', size = 24, className = '', ...props }) => {
  const colors = { Ember: '#FF9500', Flame: '#FF6B1A', Blaze: '#FFD700', Holy: '#D63D20' };
  const color = colors[tier] || colors.Ember;
  return React.createElement(
    'svg',
    { viewBox: '0 0 24 24', width: size, height: size, className, fill: 'none', ...props },
    React.createElement('path', {
      d: 'M12 2l2.4 4.9 5.4.8-3.9 3.8.9 5.4L12 14.8 7.2 16.9l.9-5.4L4.2 7.7l5.4-.8L12 2z',
      fill: color,
      stroke: '#fff',
      strokeWidth: 1,
      strokeLinejoin: 'round',
    })
  );
};

export default ICONS;