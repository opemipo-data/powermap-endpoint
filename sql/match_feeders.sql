-- Run once in Supabase SQL editor.
-- Requires pg_trgm: CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE OR REPLACE FUNCTION match_feeders_for_address(
    p_route        text,
    p_neighborhood text,
    p_sublocality  text,
    p_adm2_pcode   text
)
RETURNS TABLE (
    feeder_id   int,
    feeder_name varchar,
    location    text,
    street      text,
    match_score float
)
LANGUAGE sql
AS $$
    WITH geocoded AS (
        SELECT
            LOWER(p_route)        AS route,
            LOWER(p_neighborhood) AS neighborhood,
            LOWER(p_sublocality)  AS sublocality,
            p_adm2_pcode          AS adm2_pcode,
            p_address          AS address
    )
    SELECT
        f.feeder_id,
        f.feeder_name,
        f.location,
        f.street,
        similarity(LOWER(COALESCE(f.feeder_name, '')), COALESCE(g.address, '')) +
        similarity(LOWER(COALESCE(f.feeder_name, '')), COALESCE(g.route, ''))
        + similarity(LOWER(COALESCE(f.street, '')), COALESCE(g.route, g.neighborhood, g.sublocality, '')) * 0.4
        AS match_score
    FROM feeders f, geocoded g
    WHERE LOWER(f.adm2_pcode) = LOWER(g.adm2_pcode)
    ORDER BY match_score DESC
    LIMIT 1;
$$;

-- Allow anon role to call this function
GRANT EXECUTE ON FUNCTION match_feeders_for_address(text, text, text, text) TO anon;
