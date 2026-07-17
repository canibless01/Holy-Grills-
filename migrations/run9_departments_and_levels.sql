-- =============================================================
--  RUN 9: Department / Faculty + Academic Levels Feature
--  Combines run9_departments.sql and run9b_academic_levels.sql
--  Apply once in Supabase SQL Editor (Dashboard → SQL Editor)
-- =============================================================

-- ── PART 1: Departments table ─────────────────────────────────

CREATE TABLE IF NOT EXISTS public.departments (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT        NOT NULL,
  slug        TEXT        NOT NULL UNIQUE,
  faculty     TEXT        NOT NULL,
  is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
  sort_order  INTEGER     NOT NULL DEFAULT 0,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_departments_is_active  ON public.departments (is_active);
CREATE INDEX IF NOT EXISTS idx_departments_faculty    ON public.departments (faculty);
CREATE INDEX IF NOT EXISTS idx_departments_slug       ON public.departments (slug);
CREATE INDEX IF NOT EXISTS idx_departments_sort_order ON public.departments (sort_order);

-- Row-Level Security
ALTER TABLE public.departments ENABLE ROW LEVEL SECURITY;

-- Anyone can read active departments (used at registration/profile — no auth required)
DROP POLICY IF EXISTS "departments_public_read" ON public.departments;
CREATE POLICY "departments_public_read"
  ON public.departments FOR SELECT
  USING (is_active = TRUE);

-- Admins manage via service-role key (bypasses RLS) — no extra policy needed

-- ── PART 2: Add department_id FK to profiles ──────────────────

ALTER TABLE public.profiles
  ADD COLUMN IF NOT EXISTS department_id UUID REFERENCES public.departments(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_profiles_department_id ON public.profiles (department_id);

-- ── PART 3: Department seed data ─────────────────────────────
-- Note: seeds are FUTA departments — admin can add/edit/remove via admin panel after migration.
-- Faculty is admin-defined per department; update the faculty values below before running
-- if your campus uses different faculty groupings.

INSERT INTO public.departments (name, slug, faculty, sort_order) VALUES
  -- Faculty of Agriculture
  ('Agricultural Economics and Farm Management',  'agric-economics',        'Agriculture',                  10),
  ('Agricultural Extension and Rural Development','agric-extension',        'Agriculture',                  20),
  ('Crop, Soil and Pest Management',              'crop-soil-pest',         'Agriculture',                  30),
  ('Fisheries and Aquaculture',                   'fisheries',              'Agriculture',                  40),
  ('Forestry and Wood Technology',                'forestry',               'Agriculture',                  50),

  -- Faculty of Engineering
  ('Agricultural Engineering',                   'agric-engineering',      'Engineering',                  60),
  ('Civil Engineering',                           'civil-engineering',      'Engineering',                  70),
  ('Computer Engineering',                        'computer-engineering',   'Engineering',                  80),
  ('Electrical and Electronics Engineering',      'electrical-engineering', 'Engineering',                  90),
  ('Food Engineering',                            'food-engineering',       'Engineering',                 100),
  ('Mechanical Engineering',                      'mechanical-engineering', 'Engineering',                 110),

  -- Faculty of Environmental Technology
  ('Architecture',                                'architecture',           'Environmental Technology',    120),
  ('Estate Management',                           'estate-management',      'Environmental Technology',    130),
  ('Quantity Surveying',                          'quantity-surveying',     'Environmental Technology',    140),
  ('Urban and Regional Planning',                 'urban-planning',         'Environmental Technology',    150),

  -- Faculty of Management Sciences
  ('Accounting',                                  'accounting',             'Management Sciences',         160),
  ('Business Administration',                     'business-admin',         'Management Sciences',         170),
  ('Entrepreneurship',                            'entrepreneurship',       'Management Sciences',         180),
  ('Public Administration',                       'public-admin',           'Management Sciences',         190),

  -- Faculty of Sciences
  ('Biology',                                     'biology',                'Sciences',                    200),
  ('Chemistry',                                   'chemistry',              'Sciences',                    210),
  ('Computer Science',                            'computer-science',       'Sciences',                    220),
  ('Industrial Chemistry',                        'industrial-chemistry',   'Sciences',                    230),
  ('Mathematics',                                 'mathematics',            'Sciences',                    240),
  ('Microbiology',                                'microbiology',           'Sciences',                    250),
  ('Physics',                                     'physics',                'Sciences',                    260),
  ('Statistics',                                  'statistics',             'Sciences',                    270),

  -- Faculty of Social and Management Sciences
  ('Economics',                                   'economics',              'Social Sciences',             280),
  ('Geography and Environmental Management',      'geography',              'Social Sciences',             290),
  ('Political Science',                           'political-science',      'Social Sciences',             300),
  ('Sociology',                                   'sociology',              'Social Sciences',             310),

  -- School of Education
  ('Education and Biology',                       'education-biology',      'Education',                   320),
  ('Education and Chemistry',                     'education-chemistry',    'Education',                   330),
  ('Education and Mathematics',                   'education-mathematics',  'Education',                   340)
ON CONFLICT (slug) DO NOTHING;


-- ── PART 4: Academic Levels table ────────────────────────────

CREATE TABLE IF NOT EXISTS public.academic_levels (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT        NOT NULL,        -- Display label shown in dropdown (e.g. "200 Level")
    value       TEXT        NOT NULL UNIQUE, -- Stored value on profiles.academic_level (e.g. "200L")
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    sort_order  INTEGER     NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_academic_levels_is_active  ON public.academic_levels (is_active);
CREATE INDEX IF NOT EXISTS idx_academic_levels_sort_order ON public.academic_levels (sort_order);

-- Row-Level Security
ALTER TABLE public.academic_levels ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "academic_levels_public_read" ON public.academic_levels;
CREATE POLICY "academic_levels_public_read"
    ON public.academic_levels FOR SELECT
    USING (is_active = TRUE);

-- Note: academic_levels has NO seed data — admin adds levels via the admin panel.
-- Typical entries: "100 Level" (100L), "200 Level" (200L), "300 Level" (300L),
-- "400 Level" (400L), "500 Level" (500L), "Postgraduate" (PG), "Alumni" (ALUM)


-- ── Verify ────────────────────────────────────────────────────
SELECT 'departments' AS tbl, count(*) FROM public.departments
UNION ALL
SELECT 'academic_levels', count(*) FROM public.academic_levels
UNION ALL
SELECT 'profiles with department_id', count(*) FROM public.profiles WHERE department_id IS NOT NULL;
