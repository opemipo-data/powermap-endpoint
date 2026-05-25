-- Run once in Supabase SQL editor.

CREATE OR REPLACE FUNCTION get_state_supply_avg(
    p_state text, p_start date, p_end date
)
RETURNS float AS $$
    SELECT AVG(feeder_avg)
    FROM (
        SELECT AVG(ds.hours_of_supply) AS feeder_avg
        FROM daily_supply ds
        JOIN feeders f ON f.feeder_id = ds.feeder_id
        WHERE LOWER(f.state) = LOWER(p_state)
          AND ds.date BETWEEN p_start AND p_end
        GROUP BY ds.feeder_id
    ) sub;
$$ LANGUAGE sql;


-- Allow anon role to call this function
GRANT EXECUTE ON FUNCTION get_state_supply_avg(text, date, date) TO anon;
