ALTER TABLE pricing_profiles ADD COLUMN IF NOT EXISTS active boolean NOT NULL DEFAULT true;
