function mdl = dcx_build_model(opts)
%DCX_BUILD_MODEL Programmatically build DCX_Facility.slx — the DATACORE-X
%   facility digital twin in Simulink (fixed-step discrete, Ts = 1 s).
%
%   Architecture (one subsystem per engineering domain, discrete states in
%   Unit Delays so operating points / chunked co-simulation work):
%     Disturbances  -> ambient wet/dry bulb, diurnal IT load, OU noise
%     FaultInjection-> 21 fault kinds (table FT, tunable)
%     PLC           -> trips, generator/ATS, UPS modes, pump duty/standby,
%                      chiller lead/lag + anti-recycle, operator commands
%     Controllers   -> 7 Discrete PID Controller blocks (baseline control)
%     IT_Racks, Air_Side, CHW_Hydraulics, CHW_Plant, Electrical
%   Every inter-domain signal passes a one-step delay (explicit Euler,
%   no algebraic loops). Physics lives in dcx_*.m (shared with tests).
arguments
    opts.Save (1,1) logical = true
    opts.StopTime (1,1) double = 3600
end
mdl = 'DCX_Facility';
root = fileparts(fileparts(mfilename('fullpath')));
if bdIsLoaded(mdl), close_system(mdl, 0); end
f = fullfile(root, 'model', [mdl '.slx']);
if isfile(f), delete(f); end

% ------------------------------------------------------------------ data
dcx_model_data();                     % P, X0, Y0, FT, CMD, SP, dcx_ou + buses in base

new_system(mdl); load_system(mdl);
set_param(mdl, 'SolverType','Fixed-step', 'Solver','FixedStepDiscrete', 'FixedStep','1', ...
    'StopTime', num2str(opts.StopTime), 'SignalLogging','on', 'SignalLoggingName','logsout', ...
    'ReturnWorkspaceOutputs','on', 'SaveFormat','Dataset', 'UnconnectedInputMsg','error', ...
    'AlgebraicLoopMsg','error');
set_param(mdl, 'PreLoadFcn', 'dcx_model_data();');

% ------------------------------------------------------------ sources
add_block('simulink/Sources/Digital Clock', [mdl '/Clock'], 'SampleTime','1', 'Position',[20 40 60 70]);
add_block('simulink/Math Operations/Bias', [mdl '/t_next'], 'Bias','1', 'Position',[90 40 120 70]);
add_line(mdl, 'Clock/1', 't_next/1');
add_block('simulink/Sources/From Workspace', [mdl '/UtilNoise'], 'VariableName','dcx_ou', ...
    'SampleTime','1', 'Interpolate','off', 'OutputAfterFinalValue','Holding final value', 'Position',[20 100 120 130]);
mlf(mdl, 'Disturbances', 'function D = fcn(t, ou, P)\nD = dcx_disturbance(t, ou, P);\n', ...
    {'P'}, {'D','Bus: DistBus'}, [170 40 290 130]);
add_line(mdl, 't_next/1', 'Disturbances/1'); add_line(mdl, 'UtilNoise/1', 'Disturbances/2');
mlf(mdl, 'FaultInjection', 'function F = fcn(t, FT)\nF = dcx_faults(t, FT);\n', ...
    {}, {'F','Bus: FaultBus'}, [170 180 290 230]);
chF = find(sfroot, '-isa', 'Stateflow.EMChart', 'Path', [mdl '/FaultInjection']);
dF = chF.find('-isa','Stateflow.Data','Name','FT'); dF.Scope = 'Parameter'; dF.Tunable = true;
add_line(mdl, 't_next/1', 'FaultInjection/1');
% virtual instrumentation noise (seeded, reproducible)
add_block('simulink/Sources/Random Number', [mdl '/SensorNoise'], 'Mean','zeros(1,217)', 'Variance','1', ...
    'Seed','P.seed + 4 + (1:217)', 'SampleTime','1', 'Position',[170 270 290 300]);

% ------------------------------------------------------------ domains
% Stateflow: generator + ATS sequence (authoritative for bus / gen_state)
mlf(mdl, 'GridStatus', 'function g = fcn(F)\ng = double(F.utility <= 0);\n', {}, {}, [200 170 260 200]);
dcx_add_ats_chart(mdl, 'ATS_Sequence', [280 165 350 215]);
mlf(mdl, 'AtsPack', 'function a = fcn(bus, gen_state)\na = [1 bus gen_state];\n', {}, {}, [370 170 410 210]);
dom(mdl, 'PLC', 'dcx_plc', {'F','Ed','Cd','cmd','ats'}, 'PlcStateBus', 'PlcOutBus', 'X0.plc', '', [380 40 520 160], ...
    '[Xn, y] = dcx_plc(X, F, Ed.soc/100, Cd.plr, cmd, P, ats);');
dom(mdl, 'IT_Racks', 'dcx_racks', {'D','F','O','Ad'}, 'RackStateBus', 'RackBus', 'X0.rack', 'Y0.R', [640 40 780 160], '');
dom(mdl, 'Air_Side', 'dcx_air', {'D','F','O','Rd','Hd','Cd','ctrl'}, 'AirStateBus', 'AirBus', 'X0.air', 'Y0.A', [640 200 780 360], '');
dom(mdl, 'CHW_Hydraulics', 'dcx_hydraulics', {'F','O','Ad','ctrl'}, 'HydStateBus', 'HydBus', 'X0.hyd', 'Y0.H', [640 400 780 520], '');
dom(mdl, 'CHW_Plant', 'dcx_chwplant', {'D','F','O','Ad','Hd','ctrl','sp'}, 'ChwStateBus', 'ChwBus', 'X0.chw', 'Y0.C', [640 560 780 720], '');
dom(mdl, 'Electrical', 'dcx_electrical', {'F','O','Rd','Ad','Hd','Cd'}, 'ElecStateBus', 'ElecBus', 'X0.elec', 'Y0.E', [640 760 780 900], '');
controllers(mdl, [380 400 520 560]);
mlf(mdl, 'Sensors', ['function [meas, q, st, fac, truth] = fcn(R, A, H, C, E, O, F, D, nz)\n' ...
    '[meas, q, st, fac, truth] = dcx_sensors(R, A, H, C, E, O, F, D, nz);\n'], {}, {}, [900 300 1040 560]);
chS = find(sfroot, '-isa', 'Stateflow.EMChart', 'Path', [mdl '/Sensors']);
sz = {'meas','[1 217]'; 'q','[1 217]'; 'st','[1 34]'; 'fac','[1 11]'; 'truth','[1 217]'};
for i = 1:size(sz,1), d = chS.find('-isa','Stateflow.Data','Name',sz{i,1}); d.Props.Array.Size = sz{i,2}; end
mlf(mdl, 'SCADA_Bridge', ['function [cmd, sp] = fcn(t, meas, q, st, fac, O, BRIDGE, CMD, SP)\n' ...
    '%% Simulink <-> DATACORE-X integration service (enable with BRIDGE = 1)\n' ...
    'coder.extrinsic(''dcx_bridge_tick'');\n' ...
    'cmd = CMD; sp = SP;\n' ...
    'if BRIDGE > 0\n' ...
    '    [cmd, sp] = dcx_bridge_tick(t, meas, q, st, fac, [O.ack_seq O.ack_code], CMD, SP);\n' ...
    'end\n'], {'CMD','SP'}, {'cmd','Bus: CmdBus','sp','Bus: SpBus'}, [1100 300 1240 460]);
chB = find(sfroot, '-isa', 'Stateflow.EMChart', 'Path', [mdl '/SCADA_Bridge']);
dB = chB.find('-isa','Stateflow.Data','Name','BRIDGE'); dB.Scope = 'Parameter'; dB.Tunable = true;
add_block('simulink/Discrete/Unit Delay', [mdl '/cmd_z'], 'InitialCondition','CMD', 'SampleTime','1', 'Position',[1300 310 1340 340]);
add_block('simulink/Discrete/Unit Delay', [mdl '/sp_z'], 'InitialCondition','SP', 'SampleTime','1', 'Position',[1300 400 1340 430]);

% ------------------------------------------------------------ wiring
W = @(a,b) add_line(mdl, a, b, 'autorouting','smart');
% PLC
W('FaultInjection/1','PLC/1'); W('Electrical/2','PLC/2'); W('CHW_Plant/2','PLC/3'); W('cmd_z/1','PLC/4');
W('FaultInjection/1','GridStatus/1'); W('GridStatus/1','ATS_Sequence/1');
W('ATS_Sequence/1','AtsPack/1'); W('ATS_Sequence/2','AtsPack/2'); W('AtsPack/1','PLC/5');
% Racks
W('Disturbances/1','IT_Racks/1'); W('FaultInjection/1','IT_Racks/2'); W('PLC/1','IT_Racks/3'); W('Air_Side/2','IT_Racks/4');
% Air
W('Disturbances/1','Air_Side/1'); W('FaultInjection/1','Air_Side/2'); W('PLC/1','Air_Side/3'); W('IT_Racks/2','Air_Side/4');
W('CHW_Hydraulics/2','Air_Side/5'); W('CHW_Plant/2','Air_Side/6'); W('Controllers/1','Air_Side/7');
% Hydraulics
W('FaultInjection/1','CHW_Hydraulics/1'); W('PLC/1','CHW_Hydraulics/2'); W('Air_Side/2','CHW_Hydraulics/3'); W('Controllers/1','CHW_Hydraulics/4');
% CHW plant
W('Disturbances/1','CHW_Plant/1'); W('FaultInjection/1','CHW_Plant/2'); W('PLC/1','CHW_Plant/3'); W('Air_Side/2','CHW_Plant/4');
W('CHW_Hydraulics/2','CHW_Plant/5'); W('Controllers/1','CHW_Plant/6'); W('sp_z/1','CHW_Plant/7');
% Electrical
W('FaultInjection/1','Electrical/1'); W('PLC/1','Electrical/2'); W('IT_Racks/2','Electrical/3'); W('Air_Side/2','Electrical/4');
W('CHW_Hydraulics/2','Electrical/5'); W('CHW_Plant/2','Electrical/6');
% Controllers
W('Air_Side/2','Controllers/1'); W('CHW_Hydraulics/2','Controllers/2'); W('CHW_Plant/2','Controllers/3');
W('PLC/1','Controllers/4'); W('sp_z/1','Controllers/5');
% virtual sensors (current-step domain outputs) and SCADA bridge (delayed back into PLC/controls)
W('IT_Racks/1','Sensors/1'); W('Air_Side/1','Sensors/2'); W('CHW_Hydraulics/1','Sensors/3'); W('CHW_Plant/1','Sensors/4');
W('Electrical/1','Sensors/5'); W('PLC/1','Sensors/6'); W('FaultInjection/1','Sensors/7'); W('Disturbances/1','Sensors/8');
W('SensorNoise/1','Sensors/9');
W('t_next/1','SCADA_Bridge/1'); W('Sensors/1','SCADA_Bridge/2'); W('Sensors/2','SCADA_Bridge/3'); W('Sensors/3','SCADA_Bridge/4');
W('Sensors/4','SCADA_Bridge/5'); W('PLC/1','SCADA_Bridge/6');
W('SCADA_Bridge/1','cmd_z/1'); W('SCADA_Bridge/2','sp_z/1');

% ------------------------------------------------------------ logging
logs = {'PLC',1,'O'; 'IT_Racks',1,'R'; 'Air_Side',1,'A'; 'CHW_Hydraulics',1,'H'; 'CHW_Plant',1,'C'; ...
        'Electrical',1,'E'; 'Controllers',1,'ctrl'; 'FaultInjection',1,'F'; ...
        'Sensors',1,'meas'; 'Sensors',2,'q'; 'Sensors',3,'st'; 'Sensors',4,'fac'; 'Sensors',5,'truth'; 'sp_z',1,'sp'};
for i = 1:size(logs,1)
    ph = get_param([mdl '/' logs{i,1}], 'PortHandles');
    set_param(ph.Outport(logs{i,2}), 'DataLogging','on', 'DataLoggingNameMode','Custom', 'DataLoggingName', logs{i,3});

end
add_block('built-in/Note', [mdl '/About'], 'Position', [40 480]);
set_param([mdl '/About'], 'Text', sprintf(['DATACORE-X facility digital twin (Ts = 1 s)\n' ...
    'Built by dcx_build_model.m - physics in matlab/plant/dcx_*.m\n' ...
    'Design assumptions only; see docs for calibration status.']));
if opts.Save
    save_system(mdl, f);
end
end

% =====================================================================
function mlf(mdl, name, code, params, outs, pos)
% Add a MATLAB Function block; params = parameter-scope data; outs = {name,type,...}
b = [mdl '/' name];
add_block('simulink/User-Defined Functions/MATLAB Function', b, 'Position', pos);
ch = find(sfroot, '-isa', 'Stateflow.EMChart', 'Path', b);
ch.Script = sprintf(code);
for i = 1:numel(params)
    d = ch.find('-isa','Stateflow.Data','Name',params{i});
    d.Scope = 'Parameter'; d.Tunable = false;
end
for i = 1:2:numel(outs)
    d = ch.find('-isa','Stateflow.Data','Name',outs{i});
    d.DataType = outs{i+1};
end
end

function dom(mdl, name, fn, ins, stBus, outBus, x0, y0, pos, body)
% Domain subsystem: MATLAB Function [Xn,y] = fn(X, ins..., P), state Unit
% Delay, output y (current) and yd (one-step delayed, IC = y0).
s = [mdl '/' name];
add_block('built-in/Subsystem', s, 'Position', pos);
for i = 1:numel(ins)
    add_block('built-in/Inport', [s '/' ins{i}], 'Position', [20 40+60*i 50 54+60*i]);
end
args = strjoin(ins, ', ');
if isempty(body), body = sprintf('[Xn, y] = %s(X, %s, P);', fn, args); end
code = sprintf('function [Xn, y] = fcn(X, %s, P)\n%s\n', args, body);
b = [s '/' fn]; add_block('simulink/User-Defined Functions/MATLAB Function', b, 'Position', [200 60 360 60+60*numel(ins)+60]);
ch = find(sfroot, '-isa', 'Stateflow.EMChart', 'Path', b);
ch.Script = code;
d = ch.find('-isa','Stateflow.Data','Name','P'); d.Scope = 'Parameter'; d.Tunable = false;
d = ch.find('-isa','Stateflow.Data','Name','Xn'); d.DataType = ['Bus: ' stBus];
d = ch.find('-isa','Stateflow.Data','Name','y'); d.DataType = ['Bus: ' outBus];
add_block('simulink/Discrete/Unit Delay', [s '/State'], 'InitialCondition', x0, 'SampleTime', '1', ...
    'Position', [250 10 290 40], 'Orientation', 'left');
add_line(s, [fn '/1'], 'State/1', 'autorouting','smart');
add_line(s, 'State/1', [fn '/1'], 'autorouting','smart');
for i = 1:numel(ins), add_line(s, [ins{i} '/1'], sprintf('%s/%d', fn, i+1)); end
add_block('built-in/Outport', [s '/y'], 'Position', [520 80 550 94]);
add_line(s, [fn '/2'], 'y/1');
add_block('built-in/Outport', [s '/yd'], 'Position', [520 160 550 174]);
if isempty(y0)
    add_line(s, [fn '/2'], 'yd/1');          % PLC output used in the same step
else
    add_block('simulink/Discrete/Unit Delay', [s '/z^-1'], 'InitialCondition', y0, 'SampleTime','1', 'Position', [430 150 470 180]);
    add_line(s, [fn '/2'], 'z^-1/1'); add_line(s, 'z^-1/1', 'yd/1');
end
end

function controllers(mdl, pos)
% Baseline (thermostatic/PI) control layer: 7 Discrete PID Controller blocks.
s = [mdl '/Controllers'];
add_block('built-in/Subsystem', s, 'Position', pos);
ins = {'Ad','Hd','Cd','O','sp'};
for i = 1:numel(ins), add_block('built-in/Inport', [s '/' ins{i}], 'Position', [20 40+50*i 50 54+50*i]); end
mlf(s, 'Errors', ['function e = fcn(Ad, Hd, Cd, O, sp)\n' ...
    '%% control errors: 4x CRAH supply air, fan trim (max inlet), CHW dP, tower leaving\n' ...
    'e = [Ad.Tsup - sp.supply_air_c, Ad.max_in - sp.max_inlet_c, sp.dp_kpa - Hd.H, Cd.Tctl - sp.tower_leaving_c];\n'], ...
    {}, {}, [100 60 220 300]);
for i = 1:numel(ins), add_line(s, [ins{i} '/1'], sprintf('Errors/%d', i)); end
add_block('simulink/Signal Routing/Demux', [s '/Demux'], 'Outputs', '7', 'Position', [270 60 275 400]);
add_line(s, 'Errors/1', 'Demux/1');
P = evalin('base', 'P');
cfg = {P.pi_valve, P.pi_valve, P.pi_valve, P.pi_valve, P.pi_fan, P.pi_pump, P.pi_tower};
names = {'PI_SAT_CRAH1','PI_SAT_CRAH2','PI_SAT_CRAH3','PI_SAT_CRAH4','PI_FanTrim','PI_CHW_dP','PI_Tower'};
add_block('simulink/Signal Routing/Mux', [s '/Mux'], 'Inputs', '7', 'Position', [520 60 525 400]);
for i = 1:7
    b = [s '/' names{i}]; c = cfg{i};
    add_block('simulink/Discrete/Discrete PID Controller', b, 'Position', [330 50+48*(i-1) 430 80+48*(i-1)]);
    set_param(b, 'Controller','PI', 'P', num2str(c.kp), 'I', num2str(c.ki), 'SampleTime','1', ...
        'IntegratorMethod','Forward Euler', 'LimitOutput','on', 'UpperSaturationLimit', num2str(c.hi), ...
        'LowerSaturationLimit', num2str(c.lo), 'AntiWindupMode','clamping', ...
        'InitialConditionForIntegrator', num2str(c.u0));
    add_line(s, sprintf('Demux/%d', i), [names{i} '/1']);
    add_line(s, [names{i} '/1'], sprintf('Mux/%d', i));
end
mlf(s, 'Pack', ['function ctrl = fcn(u, O)\n' ...
    'tw = u(7); if ~any(O.tower_run > 0), tw = 0; end\n' ...
    'ctrl = struct(''fan_trim'', u(5), ''valve_cmd'', reshape(u(1:4),1,4), ''pump_cmd'', u(6), ''tower_cmd'', tw);\n'], ...
    {}, {'ctrl','Bus: CtrlBus'}, [580 180 680 260]);
add_line(s, 'Mux/1', 'Pack/1'); add_line(s, 'O/1', 'Pack/2');
chP = find(sfroot, '-isa', 'Stateflow.EMChart', 'Path', [s '/Pack']);
du = chP.find('-isa','Stateflow.Data','Name','u'); du.Props.Array.Size = '7';
chE = find(sfroot, '-isa', 'Stateflow.EMChart', 'Path', [s '/Errors']);
de = chE.find('-isa','Stateflow.Data','Name','e'); de.Props.Array.Size = '[1 7]';
add_block('built-in/Outport', [s '/ctrl'], 'Position', [740 210 770 224]);
add_line(s, 'Pack/1', 'ctrl/1');
end
