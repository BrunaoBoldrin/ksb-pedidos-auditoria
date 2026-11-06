-- Freeze the parameters that were actually effective, exactly once.
-- The old calculator applied profile values over stored sheet values.
CREATE TABLE IF NOT EXISTS pricing_schema_migrations (
    version integer PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

DO $$
DECLARE affected integer;
BEGIN
    PERFORM 1 FROM pricing_control WHERE id=1 FOR UPDATE;
    IF NOT EXISTS (SELECT 1 FROM pricing_schema_migrations WHERE version=3) THEN
        UPDATE pricing_revisions r
        SET data=r.data || jsonb_build_object(
            'efficiency',coalesce(p.data->'efficiency',r.data->'efficiency','"1"'::jsonb),
            'rounding',coalesce(p.data->'rounding',r.data->'rounding','"CENT"'::jsonb)
        )
        FROM pricing_profiles p WHERE r.profile_id=p.id;
        GET DIAGNOSTICS affected = ROW_COUNT;
        IF affected>0 THEN UPDATE pricing_control SET version=version+1 WHERE id=1; END IF;
        INSERT INTO pricing_schema_migrations(version) VALUES(3);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS pricing_fiscal_ncm_active
ON regras_fiscais ((regexp_replace(ncm,'[^0-9]','','g')),id DESC) WHERE ativo=1;
