-- Restore the sf-parks feature rows the conformance fixtures expect. Run once
-- before every client lane: ApplyEdits mutates the layer, so without a reset a
-- later lane would observe the previous lane's edits.
--
--   42  Golden Gate Park  - returned by QueryFeatures (AREA > 1000, inside the
--                           request polygon); updated by ApplyEdits.
--    7  Alamo Square ...   - excluded by QueryFeatures (AREA <= 1000); deleted
--                           by ApplyEdits.
--    8                     - intentionally absent; ApplyEdits deletes it.
--
-- The next assigned objectid is 101, the id feature_apply_edits_response.json
-- expects for its single add. The features sequence is shared by every layer,
-- so the reset refuses to run if another layer already holds an id >= 100.
\set ON_ERROR_STOP on

BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM features WHERE layer_id <> 0 AND objectid >= 100) THEN
        RAISE EXCEPTION 'features outside sf-parks already use objectid >= 100; cannot pin the next id to 101';
    END IF;
    IF EXISTS (SELECT 1 FROM features WHERE layer_id <> 0 AND objectid IN (7, 8, 42)) THEN
        RAISE EXCEPTION 'objectid 7, 8 or 42 belongs to another layer';
    END IF;
END
$$;

DELETE FROM features WHERE layer_id = 0;

INSERT INTO features (objectid, layer_id, geometry, attributes)
VALUES
    (7, 0, ST_SetSRID(ST_MakePoint(-122.4346, 37.7764), 4326),
        jsonb_build_object('NAME', 'Alamo Square Playground', 'AREA', 500.0)),
    (42, 0, ST_SetSRID(ST_MakePoint(-122.486, 37.769), 4326),
        jsonb_build_object('NAME', 'Golden Gate Park', 'AREA', 44340000.0));

SELECT setval(pg_get_serial_sequence('features', 'objectid'), 100, true);

COMMIT;
