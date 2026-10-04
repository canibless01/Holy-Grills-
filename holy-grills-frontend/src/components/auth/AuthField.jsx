import React from 'react';

// Domain 1 — shared labeled input with optional leading icon + trailing slot.
// One input implementation across every auth screen: same height, radius,
// focus ring, placeholder tone. Keeps the auth flow visually uniform.
export default function AuthField({
  icon: Icon,
  label,
  type = 'text',
  value,
  onChange,
  placeholder,
  required,
  trailing,
  inputRef,
  autoComplete,
  name,
  min,
  max,
}) {
  return (
    <div>
      {label && (
        <label className="block text-[11px] font-bold uppercase tracking-wide text-muted-foreground mb-1.5">
          {label}
        </label>
      )}
      <div className="relative">
        {Icon && (
          <Icon className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
        )}
        <input
          ref={inputRef}
          name={name}
          type={type}
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          required={required}
          autoComplete={autoComplete}
          min={min}
          max={max}
          className={`w-full ${Icon ? 'pl-10' : 'pl-4'} ${trailing ? 'pr-11' : 'pr-4'} py-3 rounded-xl bg-card border border-border text-sm text-foreground placeholder:text-muted-foreground/70 focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/40 transition`}
        />
        {trailing && (
          <div className="absolute right-2.5 top-1/2 -translate-y-1/2">{trailing}</div>
        )}
      </div>
    </div>
  );
}