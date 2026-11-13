function dcx_model_data(P)
%DCX_MODEL_DATA Create the base-workspace data and bus objects DCX_Facility
%   needs (called by the model's PreLoadFcn and by dcx_build_model).
%   Pass a parameter struct to override; otherwise an existing base P is
%   kept, or dcx_params() is used.
if nargin < 1
    if evalin('base', 'exist(''P'',''var'')'), P = evalin('base', 'P'); else, P = dcx_params(); end
end
[Y0, X0, ctrl0] = dcx_bootstrap(P);
if evalin('base', 'exist(''FT'',''var'')'), FT = evalin('base', 'FT'); else, FT = zeros(32,9); end
CMD = struct('seq',0,'code',0,'asset',0,'value',0);
SP = P.sp;
n = size(P.ou_noise, 1);
dcx_ou = [(0:n-1)'*P.dt, P.ou_noise];
D = dcx_disturbance(0, zeros(1,8), P);
F = dcx_faults(0, zeros(32,9));
if ~evalin('base','exist(''BRIDGE'',''var'')'), put('BRIDGE', 0); end
put('ats_gen_start_s', P.gen_start_s); put('ats_ats_s', P.ats_s);
put('ats_retransfer_s', P.retransfer_s); put('ats_cooldown_s', P.cooldown_s);
put('P', P); put('X0', X0); put('Y0', Y0); put('FT', FT); put('CMD', CMD); put('SP', SP); put('dcx_ou', dcx_ou);
mkbus('DistBus', D); mkbus('FaultBus', F); mkbus('CmdBus', CMD); mkbus('SpBus', SP); mkbus('CtrlBus', ctrl0);
mkbus('PlcStateBus', X0.plc); mkbus('PlcOutBus', Y0.O);
mkbus('RackStateBus', X0.rack); mkbus('RackBus', Y0.R);
mkbus('AirStateBus', X0.air);   mkbus('AirBus', Y0.A);
mkbus('HydStateBus', X0.hyd);   mkbus('HydBus', Y0.H);
mkbus('ChwStateBus', X0.chw);   mkbus('ChwBus', Y0.C);
mkbus('ElecStateBus', X0.elec); mkbus('ElecBus', Y0.E);
end

function put(n, v), assignin('base', n, v); end

function mkbus(name, s)
bi = Simulink.Bus.createObject(s);
b = evalin('base', bi.busName);
assignin('base', name, b);
if ~strcmp(bi.busName, name), evalin('base', ['clear ' bi.busName]); end
end
