SELECT pg_advisory_xact_lock(684512093);
CREATE TABLE IF NOT EXISTS pricing_control (id int PRIMARY KEY CHECK(id=1), version bigint NOT NULL DEFAULT 0);
INSERT INTO pricing_control(id) VALUES (1) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS pricing_permissions (
 username text PRIMARY KEY REFERENCES usuarios(usuario) ON UPDATE CASCADE ON DELETE CASCADE,
 permissions jsonb NOT NULL DEFAULT '[]', updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS pricing_materials (
 id bigserial PRIMARY KEY, code text UNIQUE NOT NULL CHECK(btrim(code)<>''), description text NOT NULL,
 unit text NOT NULL CHECK(unit IN ('KG','G','M','MM','M2','UN','BAR','H')),
 price numeric(28,12) NOT NULL CHECK(price>=0 AND price<='1000000000000' AND price<>'NaN'),
 factor numeric(14,12) NOT NULL DEFAULT 1 CHECK(factor>=0 AND factor<=1),
 kg_m2 numeric(24,12), length_mm numeric(24,12), per_person boolean NOT NULL DEFAULT true,
 reviewed_on date NOT NULL, active boolean NOT NULL DEFAULT true, version bigint NOT NULL DEFAULT 1,
 note text NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS pricing_components (LIKE pricing_materials INCLUDING ALL);
CREATE TABLE IF NOT EXISTS pricing_processes (LIKE pricing_materials INCLUDING ALL);
CREATE TABLE IF NOT EXISTS pricing_services (LIKE pricing_materials INCLUDING ALL);
CREATE TABLE IF NOT EXISTS pricing_profiles (
 id bigserial PRIMARY KEY, code text UNIQUE NOT NULL, data jsonb NOT NULL,
 reviewed_on date NOT NULL, version bigint NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS pricing_sheets (
 id bigserial PRIMARY KEY, material_code text UNIQUE NOT NULL REFERENCES materiais(codigo_material) ON DELETE RESTRICT,
 created_by text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS pricing_revisions (
 id bigserial PRIMARY KEY, sheet_id bigint NOT NULL REFERENCES pricing_sheets(id),
 number int NOT NULL, data jsonb NOT NULL, profile_id bigint REFERENCES pricing_profiles(id),
 status text NOT NULL CHECK(status IN ('DRAFT','ACTIVE','ARCHIVED')), author text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(sheet_id,number)
);
CREATE UNIQUE INDEX IF NOT EXISTS pricing_one_active ON pricing_revisions(sheet_id) WHERE status='ACTIVE';
CREATE TABLE IF NOT EXISTS pricing_dependencies (
 revision_id bigint NOT NULL REFERENCES pricing_revisions(id) ON DELETE CASCADE,
 material_id bigint REFERENCES pricing_materials(id), component_id bigint REFERENCES pricing_components(id),
 process_id bigint REFERENCES pricing_processes(id), service_id bigint REFERENCES pricing_services(id),
 CHECK(num_nonnulls(material_id,component_id,process_id,service_id)=1)
);
CREATE INDEX IF NOT EXISTS pricing_dep_material ON pricing_dependencies(material_id);
CREATE INDEX IF NOT EXISTS pricing_dep_component ON pricing_dependencies(component_id);
CREATE INDEX IF NOT EXISTS pricing_dep_process ON pricing_dependencies(process_id);
CREATE INDEX IF NOT EXISTS pricing_dep_service ON pricing_dependencies(service_id);
CREATE TABLE IF NOT EXISTS pricing_publications (
 id text PRIMARY KEY, operation_key text UNIQUE NOT NULL, fingerprint text NOT NULL,
 version bigint UNIQUE NOT NULL, actor text NOT NULL, action text NOT NULL,
 result jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS pricing_prices (
 id bigserial PRIMARY KEY, revision_id bigint NOT NULL REFERENCES pricing_revisions(id),
 publication_id text NOT NULL REFERENCES pricing_publications(id) DEFERRABLE INITIALLY DEFERRED,
 net_price numeric(28,2) NOT NULL CHECK(net_price>0), gross_price numeric(28,2) NOT NULL CHECK(gross_price>0),
 reviewed_on date NOT NULL, snapshot jsonb NOT NULL, fiscal_context jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS pricing_latest_snapshot ON pricing_prices(revision_id,id DESC);
CREATE TABLE IF NOT EXISTS pricing_events (
 id bigserial PRIMARY KEY, actor text NOT NULL, action text NOT NULL, target text NOT NULL,
 data jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS pricing_legacy_prices (
 material_code text PRIMARY KEY, data jsonb NOT NULL, archived_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO pricing_legacy_prices(material_code,data)
 SELECT codigo_material,jsonb_build_object('price',preco_revisado,'reviewed_on',data_ultima_revisao,
 'reviewed_by',usuario_ultima_revisao_preco) FROM materiais ON CONFLICT DO NOTHING;
ALTER TABLE IF EXISTS auditorias ADD COLUMN IF NOT EXISTS pricing_snapshot_id bigint REFERENCES pricing_prices(id);
ALTER TABLE IF EXISTS auditorias ADD COLUMN IF NOT EXISTS pricing_version bigint;
ALTER TABLE IF EXISTS auditorias ADD COLUMN IF NOT EXISTS pricing_context jsonb;
