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

SELECT honua.seed_metadata_v2_compat_snapshot();
