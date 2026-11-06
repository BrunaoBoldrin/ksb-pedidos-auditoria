-- Preserve missing non-fiscal parameters before retiring profile controls.
-- Published price snapshots remain untouched.
UPDATE pricing_revisions r
SET data=jsonb_build_object(
    'efficiency',coalesce(r.data->'efficiency',p.data->'efficiency','"1"'::jsonb),
    'rounding',coalesce(r.data->'rounding',p.data->'rounding','"CENT"'::jsonb)
) || r.data
FROM pricing_profiles p
WHERE r.profile_id=p.id AND (NOT r.data ? 'efficiency' OR NOT r.data ? 'rounding');

CREATE INDEX IF NOT EXISTS pricing_fiscal_ncm_active
ON regras_fiscais ((regexp_replace(ncm,'[^0-9]','','g')),id DESC) WHERE ativo=1;
