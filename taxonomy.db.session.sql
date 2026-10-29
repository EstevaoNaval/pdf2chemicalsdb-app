SELECT *
FROM taxon
    INNER JOIN taxon_name ON taxon.taxon_id = taxon_name.taxon_id
WHERE taxon_name.name = 'Human coronavirus OC43'
LIMIT 50;