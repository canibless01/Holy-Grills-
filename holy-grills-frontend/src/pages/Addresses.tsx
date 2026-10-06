import { useState, useEffect } from 'react';
import { Plus, MapPin, X, Trash2, Edit2, Check } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { findNearestGate } from '@/lib/deliveryUtils';
import OffCampusMap from '@/components/OffCampusMap';
import AddressesSkeleton from '@/components/skeletons/AddressesSkeleton';
import MascotStandee from '@/components/mascot/MascotStandee';

const EMPTY_FORM = { label: '', type: 'on_campus', line1: '', hostel: '', city: 'Akure', state: 'Ondo', is_default: false, gate_id: '', location_id: '', lat: null, lng: null };

export default function Addresses() {
  const [addresses, setAddresses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [gates, setGates] = useState([]);
  const [hostels, setHostels] = useState([]);
  const [pin, setPin] = useState(null);
  const [saveError, setSaveError] = useState(null);

  useEffect(() => { load(); }, []);

  const load = async () => {
    try {
      const [result, g, h] = await Promise.all([
        liveApi.addresses.list(),
        liveApi.delivery.getGates().catch(() => []),
        liveApi.delivery.getHostels().catch(() => []),
      ]);
      setAddresses(result || []);
      setGates(g || []);
      setHostels(h || []);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  const handleSave = async () => {
    setSaveError(null);
    if (!form.label.trim()) { setSaveError('Please give this address a label (e.g. Hostel).'); return; }
    if (form.type === 'on_campus') {
      if (!form.gate_id) { setSaveError('Please select your gate.'); return; }
      if (!form.location_id) { setSaveError('Please select your location.'); return; }
    }
    if (form.type === 'off_campus' && (form.lat == null || form.lng == null)) {
      setSaveError('Drop your delivery pin on the map so we can calculate your delivery fee.');
      return;
    }
    if (form.type === 'off_campus' && !form.line1.trim()) { setSaveError('Please enter your street address / description.'); return; }
    if (!form.city.trim()) { setSaveError('Please enter your city.'); return; }
    try {
      // `user_addresses` stores exactly two columns for this: `delivery_type`
      // ('on_campus' | 'off_campus') and `delivery_location_id` — a hostel id for
      // on_campus, a gate id for off_campus, the same meaning
      // `orders.delivery_location_id` has. create_order re-reads both from the
      // saved address, so sending anything else (or nothing) is what left every
      // saved address unreplayable at checkout.
      //
      // `gate_id` here is a FORM field, not a column: on-campus it is the gate the
      // hostel sits behind (used only to filter the hostel list), and off-campus
      // it is the nearest gate the pin resolved to — which IS the value persisted.
      const data = {
        ...form,
        delivery_type: form.type,
        delivery_location_id: form.type === 'on_campus' ? (form.location_id || null) : (form.gate_id || null),
        latitude: form.lat,
        longitude: form.lng,
      };
      if (form.type === 'on_campus') {
        const loc = hostels.find(l => l.id === form.location_id);
        const gate = gates.find(g => g.id === form.gate_id);
        data.line1 = `${loc?.name || ''}, ${gate?.name || ''}`.replace(/^,\s*|,\s*$/g, '').trim();
        // The hostel name is the only free-text record of which hostel this was;
        // checkout falls back to matching it when an old row has no id.
        data.hostel = loc?.name || '';
      }
      if (editing) {
        await liveApi.addresses.update(editing, data);
      } else {
        await liveApi.addresses.create(data);
      }
      setShowForm(false);
      setEditing(null);
      setForm(EMPTY_FORM);
      setPin(null);
      load();
    } catch (e) { setSaveError(e.message); }
  };

  const handleDelete = async (id) => {
    if (!confirm('Delete this address?')) return;
    await liveApi.addresses.delete(id);
    load();
  };

  if (loading) return <AddressesSkeleton />;

  return (
    <div className="space-y-4 animate-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="font-heading font-extrabold text-2xl text-foreground">Addresses</h1>
        <button onClick={() => { setShowForm(true); setEditing(null); setForm(EMPTY_FORM); setPin(null); }} className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-gradient-cta text-white text-xs font-bold shadow-glow active:scale-[0.98] transition-transform">
          <Plus className="w-4 h-4" /> Add
        </button>
      </div>

      {/* Address List */}
      <div className="space-y-2.5">
        {addresses.map(addr => (
          <div key={addr.id} className="rounded-2xl bg-card border border-border p-4 hover:shadow-md transition-all">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
                <MapPin className="w-5 h-5 text-primary" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-bold text-sm text-foreground">{addr.label}</span>
                  {addr.is_default && <span className="text-[10px] font-bold text-success px-2 py-0.5 rounded-full bg-success/10 border border-success/20 inline-flex items-center gap-1"><Check className="w-2.5 h-2.5" /> DEFAULT</span>}
                  <span className="text-[10px] font-bold text-muted-foreground px-2 py-0.5 rounded-full bg-muted capitalize">{addr.type?.replace('_', '-')}</span>
                </div>
                <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{addr.line1}, {addr.city}, {addr.state}</p>
              </div>
              <div className="flex gap-1 shrink-0">
                <button onClick={() => {
                  // Read back what was actually persisted. `delivery_location_id`
                  // is a hostel id for on_campus and a gate id for off_campus, so
                  // it restores `location_id` or `gate_id` respectively. Rows saved
                  // before these were written have neither, and the hostel is then
                  // recovered by name from `hostel`/`line1`.
                  const type = addr.delivery_type || 'on_campus';
                  const ref = addr.delivery_location_id || '';
                  const hostelName = addr.hostel || (addr.line1 || '').split(',')[0] || '';
                  const matched = type === 'on_campus'
                    ? (hostels.find(l => l.id === ref)?.id || hostels.find(l => l.name === hostelName.trim())?.id || '')
                    : ref;
                  const gate = type === 'off_campus' ? ref : (hostels.find(l => l.id === ref)?.gate_id || '');
                  setEditing(addr.id);
                  setForm({ ...addr, type, gate_id: gate, location_id: matched, lat: (addr.latitude ?? addr.lat) ?? null, lng: (addr.longitude ?? addr.lng) ?? null });
                  const la = addr.latitude ?? addr.lat; const ln = addr.longitude ?? addr.lng;
                  setPin(la != null && ln != null ? { lat: la, lng: ln } : null);
                  setShowForm(true);
                }} className="p-2 rounded-xl hover:bg-muted transition">
                  <Edit2 className="w-4 h-4 text-muted-foreground" />
                </button>
                <button onClick={() => handleDelete(addr.id)} className="p-2 rounded-xl hover:bg-destructive/10 transition">
                  <Trash2 className="w-4 h-4 text-destructive/70" />
                </button>
              </div>
            </div>
          </div>
        ))}
        {addresses.length === 0 && (
          <div className="text-center py-10 rounded-2xl border border-border">
            <MascotStandee mascot="worried" className="w-28 h-28 mx-auto mb-1" alt="No saved addresses" />
            <p className="text-sm text-muted-foreground">No saved addresses yet</p>
            <p className="text-xs text-muted-foreground mt-1">Add one to make checkout faster.</p>
          </div>
        )}
      </div>

      {/* Form Modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-end sm:items-center justify-center p-0 sm:p-4" onClick={() => !editing && setShowForm(false)}>
          <div className="bg-card rounded-t-3xl sm:rounded-3xl p-6 w-full max-w-sm max-h-[92vh] overflow-y-auto animate-slide-up" onClick={e => e.stopPropagation()}>
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-heading font-bold text-lg text-foreground">{editing ? 'Edit Address' : 'Add Address'}</h3>
              <button onClick={() => setShowForm(false)} className="p-1 rounded-lg hover:bg-muted transition"><X className="w-5 h-5 text-muted-foreground" /></button>
            </div>
            <div className="space-y-3">
              {/* Type toggle */}
              <div className="grid grid-cols-2 gap-2">
                <button onClick={() => setForm({ ...form, type: 'on_campus' })} className={`p-3 rounded-xl border-2 transition ${form.type === 'on_campus' ? 'border-primary bg-primary/5' : 'border-border hover:border-border/80'}`}>
                  <span className="text-xs font-bold">🏫 On Campus</span>
                </button>
                <button onClick={() => setForm({ ...form, type: 'off_campus' })} className={`p-3 rounded-xl border-2 transition ${form.type === 'off_campus' ? 'border-primary bg-primary/5' : 'border-border hover:border-border/80'}`}>
                  <span className="text-xs font-bold">🏠 Off Campus</span>
                </button>
              </div>

              <input className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/40 transition" placeholder="Label (e.g., Hostel)" value={form.label} onChange={e => setForm({ ...form, label: e.target.value })} />

              {form.type === 'on_campus' ? (
                <>
                  <div>
                    <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wide">Gate</label>
                    <select className="w-full mt-1.5 p-3 rounded-xl border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/40 transition" value={form.gate_id} onChange={e => setForm({ ...form, gate_id: e.target.value, location_id: '' })}>
                      <option value="">Select gate</option>
                      {gates.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
                    </select>
                  </div>
                  {form.gate_id && (
                    <div>
                      <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wide">Location</label>
                      <select className="w-full mt-1.5 p-3 rounded-xl border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/40 transition" value={form.location_id} onChange={e => setForm({ ...form, location_id: e.target.value })}>
                        <option value="">Select location</option>
                        {hostels.filter(l => l.gate_id === form.gate_id).map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
                      </select>
                    </div>
                  )}
                </>
              ) : (
                <>
                  <div>
                    <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wide">Drop your delivery pin</label>
                    <div className="mt-1.5">
                      <OffCampusMap
                        gates={gates}
                        pin={pin}
                        onPinChange={(ll) => {
                          setPin(ll);
                          const nearest = findNearestGate(gates, ll.lat, ll.lng);
                          setForm((f) => ({ ...f, lat: ll.lat, lng: ll.lng, gate_id: nearest?.gate?.id || f.gate_id }));
                        }}
                        selectedGateId={form.gate_id}
                        onGateSelect={(g) => setForm((f) => ({ ...f, gate_id: g.id }))}
                      />
                    </div>
                    {form.lat == null && (
                      <p className="text-[11px] text-primary font-semibold mt-1.5">Tap the map or "Use my location" so we can calculate your delivery fee.</p>
                    )}
                  </div>
                  <input className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/40 transition" placeholder="Street address / description" value={form.line1} onChange={e => setForm({ ...form, line1: e.target.value })} />
                  <div className="grid grid-cols-2 gap-2">
                    <input className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/40 transition" placeholder="City" value={form.city} onChange={e => setForm({ ...form, city: e.target.value })} />
                    <input className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/40 transition" placeholder="State" value={form.state} onChange={e => setForm({ ...form, state: e.target.value })} />
                  </div>
                </>
              )}

              <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                <input type="checkbox" checked={form.is_default} onChange={e => setForm({ ...form, is_default: e.target.checked })} className="w-4 h-4 accent-primary" />
                Set as default
              </label>

              {saveError && (
                <div className="flex items-center gap-2 p-2.5 rounded-xl bg-destructive/10 border border-destructive/20">
                  <span className="text-xs text-destructive font-semibold">{saveError}</span>
                </div>
              )}
              <button onClick={handleSave} className="w-full py-3 rounded-xl bg-gradient-cta text-white font-bold shadow-glow active:scale-[0.98] transition-transform">
                {editing ? 'Update' : 'Save'} Address
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}