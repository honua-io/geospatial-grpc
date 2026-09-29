-- sf-parks certification service for the geospatial-grpc conformance fixtures.
--
-- Apply after the candidate server has started (and run its migrations) and
-- after its own tests/seed/base-schema.sql, fetched at the exact server source
-- SHA. The running server picks up the new Metadata v2 snapshot. It uses the same
-- seed path as honua-server CI: rows in the honua.services / honua.layers /
-- honua.layer_fields catalog, features in the shared `features` table, and
-- honua.seed_metadata_v2_compat_snapshot() to compile the Metadata v2 graph
-- the server serves from.
--
-- The fixtures address `serviceId: sf-parks`, `layerId: 0`. Honua layer ids
-- are global, and base-schema.sql binds layer 0 to its own `test_service`.
-- This seed rebinds layer 0 to sf-parks; no fixture uses test_service.
--
-- Feature rows are restored separately by sf-parks-reset.sql so each client
-- lane starts from identical state.
\set ON_ERROR_STOP on

DELETE FROM honua.service_layers WHERE service_name = 'sf-parks' OR layer_id = 0;
DELETE FROM honua.layer_fields WHERE layer_id = 0;
DELETE FROM features WHERE layer_id = 0;
DELETE FROM honua.layers WHERE layer_id = 0;
DELETE FROM honua.services WHERE service_name = 'sf-parks';

INSERT INTO honua.services (
    service_name, description, srid, supported_formats, capabilities, service_extent, metadata)
VALUES (
    'sf-parks',
    'San Francisco parks service for geospatial-grpc conformance certification',
    4326,
    ARRAY['JSON', 'GeoJSON'],
    ARRAY['Query', 'Create', 'Update', 'Delete', 'Editing'],
    ST_MakeEnvelope(-122.52, 37.70, -122.35, 37.83, 4326),
    jsonb_build_object('accessPolicy', jsonb_build_object('allowAnonymous', true)));

INSERT INTO honua.layers (
    layer_id, layer_name, description, table_schema, table_name, primary_key_column,
    geometry_column, storage_srid, geometry_type, srid, extent, default_visibility,
    enabled, metadata)
VALUES (
    0, 'Parks', 'Managed parks', current_schema(), 'features', 'objectid',
    'geometry', 4326, 'Point', 4326,
    ST_MakeEnvelope(-122.52, 37.70, -122.35, 37.83, 4326), true,
    true, jsonb_build_object('accessPolicy', jsonb_build_object('allowAnonymous', true), 'displayField', 'NAME'));

INSERT INTO honua.service_layers (service_name, layer_id, layer_order)
VALUES ('sf-parks', 0, 0);

-- Field names, types, lengths and descriptions mirror
-- conformance/fixtures/feature_query_response.json.
INSERT INTO honua.layer_fields (
    layer_id, field_name, field_type, field_order, max_length, nullable, description)
VALUES
    (0, 'OBJECTID', 'bigint', 0, NULL, false, 'Object ID'),
    (0, 'NAME', 'String', 1, 128, true, 'Park Name'),
    (0, 'AREA', 'Double', 2, NULL, true, 'Area (sq ft)'),
    (0, 'shape', 'Geometry', 3, NULL, true, 'Geometry');

-- Elevation layer 4701 for the ElevationService fixtures: a synthetic 17 x 13
-- grid of 0.01 degree cells from (-122.52, 37.83) whose elevation is
-- 10 * column + row metres (1-based), so every sampled value is predictable.
-- Needs postgis_raster; honua.raster_data is created by the server's migrations.
DELETE FROM honua.raster_data WHERE layer_id = 4701;
DELETE FROM honua.service_layers WHERE layer_id = 4701;
DELETE FROM honua.layers WHERE layer_id = 4701;

INSERT INTO honua.layers (
    layer_id, layer_name, description, table_schema, table_name, primary_key_column,
    geometry_column, storage_srid, geometry_type, srid, extent, default_visibility,
    enabled, metadata)
VALUES (
    4701, 'Elevation', 'Synthetic San Francisco elevation model', current_schema(), 'features', 'objectid',
    'geometry', 4326, 'Polygon', 4326,
    ST_MakeEnvelope(-122.52, 37.70, -122.35, 37.83, 4326), true,
    true, jsonb_build_object('accessPolicy', jsonb_build_object('allowAnonymous', true)));

INSERT INTO honua.service_layers (service_name, layer_id, layer_order)
VALUES ('sf-parks', 4701, 1);

INSERT INTO honua.raster_data (layer_id, name, description, raster)
SELECT 4701, 'sf-dem', 'Synthetic elevation: 10 * column + row metres',
    ST_SetValues(
        ST_AddBand(ST_MakeEmptyRaster(17, 13, -122.52, 37.83, 0.01, -0.01, 0, 0, 4326), '32BF'::text, 0, -9999),
        1, 1, 1,
        (SELECT array_agg(cells ORDER BY row_number)
         FROM (
             SELECT row_number, array_agg((10 * column_number + row_number)::double precision ORDER BY column_number) AS cells
             FROM generate_series(1, 13) AS row_number, generate_series(1, 17) AS column_number
             GROUP BY row_number
         ) AS grid)::double precision[][]);

SELECT honua.seed_metadata_v2_compat_snapshot();

-- Field aliases. The fixture's display names ("Object ID", "Park Name",
-- "Area (sq ft)") live in the Metadata v2 field `alias`, the same field the
-- admin field-configuration API writes. The compat compiler above does not
-- project aliases, so set them on the compiled sf-parks feature resource
-- (res-layer-0) from layer_fields.description, then re-derive the etag the
-- same way honua.seed_metadata_v2_compat_snapshot() does.
WITH aliased AS (
    SELECT
        snapshot.environment,
        snapshot.revision,
        jsonb_set(
            snapshot.document,
            '{resources}',
            (
                SELECT jsonb_agg(
                    CASE
                        WHEN resource #>> '{metadata,id}' = 'res-layer-0' THEN jsonb_set(
                            resource,
                            '{schemaFields}',
                            (
                                SELECT jsonb_agg(
                                    CASE
                                        WHEN lf.description IS NULL THEN field
                                        ELSE field || jsonb_build_object('alias', lf.description)
                                    END
                                    ORDER BY ordinality
                                )
                                FROM jsonb_array_elements(resource -> 'schemaFields') WITH ORDINALITY AS f(field, ordinality)
                                LEFT JOIN honua.layer_fields lf
                                    ON lf.layer_id = 0 AND lf.field_name = field ->> 'name'
                            )
                        )
                        ELSE resource
                    END
                    ORDER BY resource_ordinality
                )
                FROM jsonb_array_elements(snapshot.document -> 'resources')
                    WITH ORDINALITY AS r(resource, resource_ordinality)
            )
        ) AS document
    FROM honua.metadata_v2_snapshots snapshot
    JOIN honua.metadata_v2_current current_revision
        ON current_revision.environment = snapshot.environment
       AND current_revision.revision = snapshot.revision
),
updated AS (
    UPDATE honua.metadata_v2_snapshots snapshot
    SET document = aliased.document,
        etag = '"' || md5(aliased.document::text) || '"'
    FROM aliased
    WHERE snapshot.environment = aliased.environment
      AND snapshot.revision = aliased.revision
    RETURNING snapshot.environment, snapshot.revision, snapshot.etag
)
UPDATE honua.metadata_v2_current current_revision
SET etag = updated.etag,
    activated_at = NOW()
FROM updated
WHERE current_revision.environment = updated.environment
  AND current_revision.revision = updated.revision;
