-- READ ONLY: reference candidates, never function bodies or customer data.
WITH f AS MATERIALIZED (
 SELECT p.oid,p.proname,p.prosrc,p.oid::regprocedure::text AS signature
 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname IN('public','hg_internal') AND p.prokind='f'
)
SELECT f.signature,
 coalesce((SELECT jsonb_agg(c.signature ORDER BY c.signature) FROM f c WHERE c.oid<>f.oid AND (strpos(c.prosrc,f.proname||'(')>0 OR strpos(c.prosrc,f.proname||' (')>0)),'[]') AS sql_reference_candidates,
 coalesce((SELECT jsonb_agg(n.nspname||'.'||c.relname||':'||t.tgname ORDER BY t.tgname) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE t.tgfoid=f.oid AND NOT t.tgisinternal),'[]') AS trigger_bindings,
 coalesce((SELECT jsonb_agg(p.schemaname||'.'||p.tablename||':'||p.policyname ORDER BY p.tablename,p.policyname) FROM pg_policies p WHERE p.schemaname IN('public','hg_internal') AND (strpos(coalesce(p.qual,''),f.proname||'(')>0 OR strpos(coalesce(p.with_check,''),f.proname||'(')>0)),'[]') AS policy_reference_candidates,
 (SELECT count(*) FROM pg_depend d WHERE d.refclassid='pg_proc'::regclass AND d.refobjid=f.oid) AS catalog_dependents
FROM f ORDER BY f.signature;
