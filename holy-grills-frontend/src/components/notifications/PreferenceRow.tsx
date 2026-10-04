import { motion } from 'framer-motion';

// Accessible toggle switch. `disabled` locks it while a save is in flight.
export default function PreferenceRow({ icon: Icon, label, desc, enabled, onToggle, disabled }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-center gap-3 p-3.5 rounded-2xl bg-card border border-border"
    >
      <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
        enabled ? 'bg-primary/10' : 'bg-secondary'
      }`}>
        <Icon className={`w-5 h-5 ${enabled ? 'text-primary' : 'text-muted-foreground'}`} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="font-bold text-sm text-foreground">{label}</div>
        <div className="text-[11px] text-muted-foreground leading-snug">{desc}</div>
      </div>
      <button
        role="switch"
        aria-checked={enabled}
        aria-label={label}
        disabled={disabled}
        onClick={() => onToggle(!enabled)}
        className={`relative w-12 h-7 rounded-full p-1 transition-colors flex-shrink-0 ${
          enabled ? 'bg-gradient-cta' : 'bg-border'
        } ${disabled ? 'opacity-50 cursor-not-allowed' : 'active:scale-95'}`}
      >
        <motion.span
          layout
          transition={{ type: 'spring', stiffness: 500, damping: 30 }}
          className={`block w-5 h-5 rounded-full bg-white shadow-sm ${enabled ? 'translate-x-5' : ''}`}
        />
      </button>
    </motion.div>
  );
}