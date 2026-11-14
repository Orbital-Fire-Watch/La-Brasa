-- Drawn areas registered with POST /api/areas (spec 6.3).
-- The id is a hash of the cleaned geometry, so the same area always gets the same id.
-- Not touched by pipeline/load_to_db.py: areas survive data reloads.
--
-- Runs automatically on a new, empty database volume. For an existing database run it once:
--   docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /docker-entrypoint-initdb.d/002_areas.sql'
CREATE TABLE IF NOT EXISTS areas (
  area_id    TEXT PRIMARY KEY,                 -- 'a_' + 12 hex characters
  geometry   JSONB NOT NULL,                   -- GeoJSON MultiPolygon, exactly as returned to the frontend
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
