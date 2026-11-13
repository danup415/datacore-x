function [cmd, sp] = dcx_bridge_tick(t, meas, q, st, fac, ack, CMD0, SP0)
%DCX_BRIDGE_TICK Simulink <-> DATACORE-X integration service, called once per
%   simulation step from the SCADA_Bridge block (coder.extrinsic).
%   1) publishes the 217 registry points + states + facility KPIs to
%      POST /api/external/snapshot  (source.type becomes "external")
%   2) polls approved operator commands (GET /api/external/commands),
%      converts them to the PLC command bus / setpoint bus, and
%   3) acknowledges each command with the PLC's interlock result.
%   Configure with dcx_bridge_config(); failures are counted, never fatal.
persistent B
if isempty(B) || t <= 0
    B = dcx_bridge_config();
    B.seq = 0; B.sp = SP0; B.queue = {}; B.pending = struct('id',{},'seq',{});
    B.tags = dcx_tag_list(); B.fail = 0; B.sent = 0; B.next_pub = -inf;
end
cmd = CMD0; cmd.seq = B.seq;
sp = B.sp;
if t < B.next_pub
    if isfield(B, 'lastcmd'), cmd = B.lastcmd; end
    return
end
B.next_pub = t + B.publish_every_s - 1e-9;

% ---------------- publish snapshot ----------------------------------------
T = B.tags;
assetsMap = containers.Map('KeyType','char','ValueType','any');
for j = 1:numel(T.state_assets)
    rec = struct('state', T.state_names{max(1, st(j))}, 'values', containers.Map('KeyType','char','ValueType','any'), ...
        'quality', containers.Map('KeyType','char','ValueType','any'));
    assetsMap(T.state_assets{j}) = rec;
end
for k = 1:numel(meas)
    rec = assetsMap(T.asset{k});
    if q(k) > 0 || isnan(meas(k))
        rec.values(T.key{k}) = NaN;  rec.quality(T.key{k}) = 'BAD';
    else
        rec.values(T.key{k}) = meas(k);
    end
end
facMap = containers.Map(T.facility_keys, num2cell(double(fac)));
doc = struct('sim_time_s', t, 'source_id', B.source_id, 'model', 'MATLAB/Simulink DCX_Facility', ...
    'model_version', B.model_version, 'assets', assetsMap, 'facility', facMap);
try
    webwrite(B.url + "/api/external/snapshot", jsonencode(doc, 'ConvertInfAndNaN', true), B.opts);
    B.sent = B.sent + 1;
catch ME
    B.fail = B.fail + 1;
    if B.fail < 5 || mod(B.fail, 60) == 0, warning('dcx:bridge', 'publish failed (%d): %s', B.fail, ME.message); end
end

% ---------------- acknowledge commands the PLC has processed ----------------
keep = true(1, numel(B.pending));
for i = 1:numel(B.pending)
    if ack(1) >= B.pending(i).seq
        reasons = {'accepted by PLC', 'INTERLOCK: equipment tripped — reset required', ...
            'INTERLOCK: cannot stop the last running CHW pump', 'INTERLOCK: CRAH tripped — reset required', ...
            'INTERLOCK: minimum two CRAH units must remain in service', 'INTERLOCK: trip cause still present', ...
            'invalid command/asset'};
        okc = ack(2) == 0 || ack(1) > B.pending(i).seq;
        r = reasons{min(numel(reasons), ack(2) + 1)}; if ack(1) > B.pending(i).seq, r = reasons{1}; end
        postAck(B, B.pending(i).id, okc, r);
        keep(i) = false;
    end
end
B.pending = B.pending(keep);

% ---------------- poll new commands ---------------------------------------
try
    c = webread(B.url + "/api/external/commands", B.opts);
    if ~isempty(c)
        if isstruct(c), c = num2cell(c); end
        B.queue = [B.queue(:); c(:)]';
    end
catch
end
if ~isempty(B.queue)
    c = B.queue{1}; B.queue(1) = [];
    [code, asset, val, isSp] = mapCommand(c);
    if isSp
        lim = struct('supply_air_c',[18 27],'chws_c',[12 22],'dp_kpa',[100 260],'tower_leaving_c',[16 29],'max_inlet_c',[20 27]);
        nm = char(c.name); v = double(val);
        if isfield(lim, nm) && v >= lim.(nm)(1) && v <= lim.(nm)(2)
            B.sp.(nm) = v; sp = B.sp; postAck(B, c.id, true, "setpoint applied in Simulink");
        else
            postAck(B, c.id, false, "setpoint name or value outside engineering limits");
        end
    elseif code > 0
        if code == 8, clearFaults(asset); end
        B.seq = B.seq + 1;
        cmd = struct('seq', B.seq, 'code', code, 'asset', asset, 'value', val);
        B.pending(end+1) = struct('id', c.id, 'seq', B.seq);
        B.lastcmd = cmd;
    else
        postAck(B, c.id, false, "command not supported by the Simulink PLC");
    end
end
if isfield(B, 'lastcmd'), cmd = B.lastcmd; end
end

% =========================================================================
function postAck(B, id, ok, reason)
try
    webwrite(B.url + "/api/external/commands/ack", jsonencode(struct('id', id, 'accepted', logical(ok), 'reason', char(reason))), B.opts);
catch
end
end

function [code, asset, val, isSp] = mapCommand(c)
code = 0; asset = 0; val = 0; isSp = false;
nm = char(c.command); a = ''; if isfield(c,'asset') && ~isempty(c.asset), a = char(c.asset); end
num = str2double(regexp(a, '\d+$', 'match', 'once'));
if startsWith(a, 'P-'), asset = 10 + num; elseif startsWith(a, 'CRAH-'), asset = 20 + num; elseif startsWith(a, 'CH-'), asset = 30 + num; end
switch nm
    case 'pump_start', code = 1;
    case 'pump_stop', code = 2;
    case 'pump_changeover', code = 3; val = str2double(regexp(char(c.value), '\d+$', 'match', 'once'));
    case 'crah_enable', code = 4;
    case 'crah_disable', code = 5;
    case 'chiller_lead', code = 6;
    case 'reset_trip', code = 7;
    case 'maintenance_complete', code = 8;
    case 'set_setpoint', isSp = true; val = c.value;
end
end

function clearFaults(asset)
% maintenance: deactivate fault-table rows for this asset and push to the running model
try
    FT = evalin('base', 'FT'); typ = floor(asset/10); i = mod(asset, 10);
    kinds = {[1 2 3 4], [5 6 7 8], [10 11]};
    if typ >= 1 && typ <= 3
        rows = ismember(FT(:,1), kinds{typ}) & FT(:,2) == i;
        FT(rows, :) = 0; assignin('base', 'FT', FT);
        set_param(bdroot, 'SimulationCommand', 'update');
    end
catch
end
end
