-- Historical inputs are preserved independently of published commercial prices.
CREATE TABLE IF NOT EXISTS pricing_excel_sources (
    id bigserial PRIMARY KEY,
    filename text NOT NULL,
    sha256 text NOT NULL UNIQUE CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    model jsonb NOT NULL CHECK (jsonb_typeof(model) = 'object'),
    edits jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(edits) = 'object'),
    linked_codes jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(linked_codes) = 'array'),
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    author text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
