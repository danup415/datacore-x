function B = dcx_bridge_config()
%DCX_BRIDGE_CONFIG Bridge settings (edit here or set base variable DCX_BRIDGE_URL).
B.url = "http://localhost:8000";
try
    if evalin('base', 'exist(''DCX_BRIDGE_URL'',''var'')'), B.url = string(evalin('base', 'DCX_BRIDGE_URL')); end
catch
end
B.publish_every_s = 1;
B.source_id = "matlab-dcx-facility";
B.model_version = string(version('-release')) + " / DCX_Facility";
B.opts = weboptions('MediaType', 'application/json', 'Timeout', 3, ...
    'HeaderFields', {'X-DCX-Role', 'engineer'; 'X-DCX-User', 'matlab-bridge'});
end
