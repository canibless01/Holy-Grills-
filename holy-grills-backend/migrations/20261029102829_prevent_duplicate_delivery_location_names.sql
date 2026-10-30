CREATE UNIQUE INDEX gates_campus_normalized_name_key ON public.gates (campus_id, lower(btrim(name))) NULLS NOT DISTINCT;
CREATE UNIQUE INDEX hostels_campus_normalized_name_key ON public.hostels (campus_id, lower(btrim(name))) NULLS NOT DISTINCT;
