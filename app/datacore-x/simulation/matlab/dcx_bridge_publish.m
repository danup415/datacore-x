function resp = dcx_bridge_publish(baseUrl, simTime, assetValues, assetStates, facility, opts)
%DCX_BRIDGE_PUBLISH Publish one MATLAB/Simulink state snapshot to DATACORE-X.
%
%   resp = dcx_bridge_publish(baseUrl, simTime, assetValues, assetStates, facility)
%
%   baseUrl     e.g. "http://localhost:8000"
%   simTime     simulation time [s]
%   assetValues containers.Map: assetId (char, e.g. 'P-01') -> containers.Map(key -> double)
%               keys MUST be registry data points (config/tag_map.csv); the
%               service rejects unknown assets/keys with HTTP 422.
%   assetStates containers.Map: assetId -> state string ('RUNNING','STANDBY','TRIPPED',...)
%   facility    containers.Map: facility KPI key -> double (it_load_kw, pue, ...)
%
%   Once the first snapshot is accepted the service switches its
%   authoritative source to "external": the 3D twin, historian, tag API
%   and OPC UA server then show these values (source.type = "external").
%
%   Written against documented R2024a APIs (jsonencode, weboptions,
%   webwrite). NOTE: not executed in the environment where this project was
%   generated (no MATLAB available) — verify on your installation.

arguments
    baseUrl (1,1) string
    simTime (1,1) double
    assetValues containers.Map
    assetStates containers.Map
    facility containers.Map = containers.Map('KeyType','char','ValueType','any')
    opts.ModelVersion (1,1) string = "R2024a"
    opts.SourceId (1,1) string = "matlab-01"
    opts.Timeout (1,1) double = 5
end

assets = containers.Map('KeyType','char','ValueType','any');
ids = assetValues.keys;
for i = 1:numel(ids)
    id = ids{i};
    rec = struct();
    rec.values = assetValues(id);           % containers.Map -> JSON object
    if isKey(assetStates, id)
        rec.state = char(assetStates(id));
    else
        rec.state = 'UNKNOWN';
    end
    assets(id) = rec;
end

doc = struct( ...
    'sim_time_s', simTime, ...
    'source_id', char(opts.SourceId), ...
    'model', 'MATLAB/Simulink', ...
    'model_version', char(opts.ModelVersion), ...
    'assets', assets, ...
    'facility', facility);

wo = weboptions('MediaType','application/json', 'Timeout', opts.Timeout, ...
    'HeaderFields', {'X-DCX-Role','engineer'; 'X-DCX-User','matlab-bridge'});
resp = webwrite(baseUrl + "/api/external/snapshot", jsonencode(doc), wo);
end
