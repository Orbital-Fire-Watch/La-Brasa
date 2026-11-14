-- Monthly counts per region: original MODIS, original VIIRS and harmonized.
CREATE MATERIALIZED VIEW monthly_comparison AS
SELECT region_id,
       month,
       SUM(modis_raw)       AS modis_raw,
       SUM(viirs_raw)       AS viirs_raw,
       SUM(harmonized)      AS harmonized,
       BOOL_OR(provisional) AS provisional
FROM (
  SELECT region_id, date_trunc('month', acq_date)::date AS month,
         COUNT(*)::bigint AS modis_raw, 0::bigint AS viirs_raw,
         0::double precision AS harmonized, FALSE AS provisional
  FROM modis_hotspots WHERE region_id IS NOT NULL GROUP BY 1, 2

  UNION ALL

  SELECT region_id, date_trunc('month', acq_date)::date,
         0::bigint, COUNT(*)::bigint, 0::double precision, FALSE
  FROM viirs_hotspots WHERE region_id IS NOT NULL GROUP BY 1, 2

  UNION ALL

  SELECT region_id, date_trunc('month', acq_date)::date,
         0::bigint, 0::bigint, SUM(weight)::double precision, BOOL_OR(provisional)
  FROM harmonized_hotspots WHERE region_id IS NOT NULL GROUP BY 1, 2
) t
GROUP BY region_id, month;

CREATE UNIQUE INDEX ON monthly_comparison (region_id, month);