-- The existing role column is an enum, not unconstrained text.
ALTER TYPE public.user_role ADD VALUE IF NOT EXISTS 'community_manager';
