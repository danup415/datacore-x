function dcx_live(opts)
%DCX_LIVE Run DCX_Facility as the live source of the DATACORE-X twin.
%   dcx_live()                       % start backend (if needed) + paced simulation
%   dcx_live('Speed',10,'Hours',8)   % 10x real time
%   dcx_live('Stop',true)            % stop the simulation
%   Then open http://localhost:8000 — the 3D twin shows source "external".
arguments
    opts.Speed (1,1) double = 1
    opts.Hours (1,1) double = 24
    opts.FT (32,9) double = zeros(32,9)
    opts.Stop (1,1) logical = false
    opts.StartBackend (1,1) logical = true
end
mdl = 'DCX_Facility';
if opts.Stop
    if bdIsLoaded(mdl), set_param(mdl, 'SimulationCommand', 'stop'); end
    return
end
if opts.StartBackend, dcx_start_backend(); end
load_system(mdl);
P = evalin('base', 'P');
P2 = dcx_params('Seed', P.seed, 'Horizon', opts.Hours*3600 + 10);
assignin('base', 'P', P2); assignin('base', 'FT', opts.FT); assignin('base', 'BRIDGE', 1);
dcx_model_data(P2);
clear dcx_bridge_tick
set_param(mdl, 'StopTime', num2str(opts.Hours*3600), 'EnablePacing', 'on', 'PacingRate', num2str(opts.Speed));
set_param(mdl, 'SimulationCommand', 'start');
fprintf('DCX_Facility running at %gx real time, publishing to the integration service.\n', opts.Speed);
end
