-- Run once in Supabase SQL editor.

CREATE OR REPLACE FUNCTION get_lga_supply_avg(
    p_adm2_pcode text, p_start date, p_end date
)
RETURNS float AS $$
    SELECT AVG(feeder_avg)
    FROM (
        SELECT AVG(ds.hours_of_supply) AS feeder_avg
        FROM daily_supply ds
        JOIN feeders f ON f.feeder_id = ds.feeder_id
        WHERE f.adm2_pcode = p_adm2_pcode
          AND ds.date BETWEEN p_start AND p_end
        GROUP BY ds.feeder_id
    ) sub;
$$ LANGUAGE sql;


-- Allow anon role to call this function
GRANT EXECUTE ON FUNCTION get_lga_supply_avg(text, date, date) TO anon;
