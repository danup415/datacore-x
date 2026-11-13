%DCX_BRIDGE_RUN Co-simulation loop: Simulink facility model -> DATACORE-X.
%
% Runs the Simulink model in fixed chunks (operating-point continuation),
% maps logged signals to registry data points through config/tag_map.csv,
% publishes each chunk's final sample, then polls and applies approved
% operator commands, acknowledging each one.
%
% Requirements: Simulink; signals logged (Signal Logging, Dataset format)
% with names equal to the "simulink_signal" column of tag_map.csv, e.g.
% DCX_P_01_flow_ls.  Commands map to tunable block parameters in CMDMAP.
%
% NOTE: written against documented R2024a APIs; not executed where this
% project was generated (no MATLAB available). Treat as an integration
% template to verify against your model.

model    = "DCX_Facility";          % your Simulink facility model
baseUrl  = "http://localhost:8000";
chunk_s  = 1.0;                      % simulation seconds per publish
pace     = true;                     % true: wall-clock paced (1x)
root     = fileparts(fileparts(fileparts(mfilename("fullpath"))));

map = readtable(fullfile(root, "config", "tag_map.csv"), "TextType", "string");

% command -> {block path, parameter, value function}
CMDMAP = containers.Map();
CMDMAP("set_setpoint:chws_c")       = {model + "/Controls/CHWS_SP", "Value", @(v) num2str(v)};
CMDMAP("set_setpoint:supply_air_c") = {model + "/Controls/SAT_SP",  "Value", @(v) num2str(v)};
CMDMAP("pump_start:P-03")           = {model + "/Plant/Pumps/P03_Enable", "Value", @(v) "1"};
CMDMAP("pump_stop:P-01")            = {model + "/Plant/Pumps/P01_Enable", "Value", @(v) "0"};

load_system(model);
set_param(model, "SignalLogging", "on", "SignalLoggingName", "logsout");
opts = weboptions("MediaType", "application/json", "Timeout", 5, ...
    "HeaderFields", {'X-DCX-Role','engineer'; 'X-DCX-User','matlab-bridge'});

t = 0; op = [];
while true
    tic;
    in = Simulink.SimulationInput(model);
    in = in.setModelParameter("StopTime", num2str(t + chunk_s), ...
        "SaveFinalState", "on", "SaveOperatingPoint", "on", "FinalStateName", "xFinal");
    if ~isempty(op)
        in = in.setInitialState(op);
    end
    out = sim(in);
    op  = out.xFinal;
    t   = t + chunk_s;

    vals = containers.Map('KeyType','char','ValueType','any');
    states = containers.Map('KeyType','char','ValueType','any');
    logs = out.logsout;
    for k = 1:height(map)
        name = map.simulink_signal(k);
        el = logs.getElement(char(name));
        if isempty(el), continue; end
        ts = el.Values;
        aid = char(map.asset_id(k));
        if ~isKey(vals, aid), vals(aid) = containers.Map('KeyType','char','ValueType','double'); end
        m = vals(aid); m(char(map.key(k))) = double(ts.Data(end)); vals(aid) = m;
        if ~isKey(states, aid), states(aid) = 'RUNNING'; end   % replace with logged state enums
    end
    try
        dcx_bridge_publish(baseUrl, t, vals, states);
    catch ME
        warning("DCX publish failed: %s", ME.message);
    end

    % ---- approved commands (role checks & interlocks already applied server-side)
    try
        cmds = webread(baseUrl + "/api/external/commands", opts);
        for i = 1:numel(cmds)
            c = cmds(i); if iscell(cmds), c = cmds{i}; end
            key = string(c.command) + ":" + string(c.name);
            if ~isKey(CMDMAP, key), key = string(c.command) + ":" + string(c.asset); end
            ok = isKey(CMDMAP, key); reason = "no mapping in CMDMAP";
            if ok
                m = CMDMAP(key);
                set_param(m{1}, m{2}, m{3}(c.value));
                reason = "applied to " + m{1};
            end
            webwrite(baseUrl + "/api/external/commands/ack", ...
                jsonencode(struct('id', c.id, 'accepted', ok, 'reason', reason)), opts);
        end
    catch ME
        warning("DCX command poll failed: %s", ME.message);
    end
    if pace, pause(max(0, chunk_s - toc)); end
end
