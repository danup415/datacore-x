function mdl = dcx_build_hydraulics_ssc(P, opts)
%DCX_BUILD_HYDRAULICS_SSC Build DCX_CHW_Hydraulics_SSC.slx - a Simscape Fluids
%   (Isothermal Liquid) model of the chilled-water distribution loop, used to
%   validate the reduced-order hydraulics in plant/dcx_hydraulics.m (item 2).
%
%   Network (open reservoirs stand in for the closed loop's expansion tank):
%     suction reservoir -> 2 x Centrifugal Pump (IL), each with an isolation
%     restriction -> header -> constant-dP element (the reduced model's Hs
%     term) -> 4 parallel CRAH branches, each Pipe (IL) DN40 x 40 m + fixed
%     coil restriction + variable control-valve restriction -> return
%   Pump: tabulated head-flow at reference speed taken from the DCX curve
%   H = H0 - kp q^2 (affinity laws scale it with speed inside the block).
%   Inputs (Constant blocks, tunable for Fast Restart): ssc_n (speed 0..1),
%   ssc_iso (1x2, 1 = pump running), ssc_v (1x4 valve openings).
%   Outputs: H (header-to-suction dp, kPa), q (loop mass flow, kg/s),
%   q1/q2 pump mass flows (kg/s); divide by rho/1000 for L/s.
arguments
    P struct = dcx_params()
    opts.CoilArea (1,1) double = 2.55e-4      % m^2, fixed coil restriction
    opts.ValveArea (1,1) double = 1.31e-4     % m^2, control valve fully open
    opts.Save (1,1) logical = true
end
mdl = 'DCX_CHW_Hydraulics_SSC';
if bdIsLoaded(mdl), set_param(mdl, 'FastRestart', 'off'); close_system(mdl, 0); end
new_system(mdl); load_system('fl_lib'); load_system('nesl_utility'); load_system('SimscapeFluids_lib');
nl = newline;
LIB.pump = ['SimscapeFluids_lib/Isothermal Liquid/Pumps & Motors/Centrifugal Pump' nl '(IL)'];
LIB.pipe = 'fl_lib/Isothermal Liquid/Elements/Pipe (IL)';
LIB.lr   = ['fl_lib/Isothermal Liquid/Elements/Local Restriction' nl '(IL)'];
LIB.res  = 'fl_lib/Isothermal Liquid/Elements/Reservoir (IL)';
LIB.ps   = 'fl_lib/Isothermal Liquid/Sources/Pressure Source (IL)';
LIB.fs   = ['fl_lib/Isothermal Liquid/Sensors/Flow Rate Sensor' nl '(IL)'];
LIB.prs  = 'fl_lib/Isothermal Liquid/Sensors/Pressure Sensor (IL)';
LIB.prop = ['fl_lib/Isothermal Liquid/Utilities/Isothermal Liquid' nl 'Properties (IL)'];
LIB.w    = ['fl_lib/Mechanical/Mechanical Sources/Ideal Angular' nl 'Velocity Source'];
LIB.mref = ['fl_lib/Mechanical/Rotational Elements/Mechanical' nl 'Rotational Reference'];
LIB.sps  = ['nesl_utility/Simulink-PS' nl 'Converter'];
LIB.pss  = ['nesl_utility/PS-Simulink' nl 'Converter'];
LIB.solv = ['nesl_utility/Solver' nl 'Configuration'];
rho = 998.21; g0 = 9.80665;
% ---- pump table from the reduced model curve (per pump, a = 1)
q = linspace(0, 0.97*sqrt(P.pump_H0/P.pump_kp), 12);           % L/s
Hk = P.pump_H0 - P.pump_kp*q.^2;                                % kPa
x = q/P.pump_q_bep; eta = max(0.15, P.pump_eta_bep*(1 - 0.8*(x - 1).^2));
Pk = max(0.2, q.*Hk/1000./eta);                                 % kW (not validated here)
blk0 = @(lib, name, pos) add_block(lib, [mdl '/' name], 'Position', pos);
blk = @(lib, name, pos) pressurize(blk0(lib, name, pos), lib, LIB);
blk(LIB.solv, 'Solver', [20 20 80 50]);
blk(LIB.prop, 'Water', [100 20 160 50]);
blk(LIB.mref, 'Gnd', [20 400 60 430]);
c = constant(mdl, 'n_cmd', 'ssc_n', [20 300 70 320]);
s = blk(LIB.sps, 'n_ps', [100 300 130 320]); set_param(s, 'Unit', 'rpm'); 
add_block('simulink/Math Operations/Gain', [mdl '/rpm'], 'Gain', '1450', 'Position', [80 300 90 320]);
delete_line_safe(mdl); %#ok<*NASGU>
add_line(mdl, 'n_cmd/1', 'rpm/1'); add_line(mdl, 'rpm/1', 'n_ps/1');
blk(LIB.res, 'ResS', [160 120 200 150]);
for i = 1:2
    y = 100 + 140*(i-1);
    blk(LIB.w, sprintf('W%d', i), [160 y+80 200 y+110]);
    p = blk(LIB.pump, sprintf('Pump%d', i), [240 y 300 y+60]);
    set_param(p, 'pump_parameterization', 'fluids.isothermal_liquid.pumps_motors.enum.centrifugal_pump_spec.table1D', ...
        'capacity_ref_1D_TLU', mat2str(q/1000, 6), 'capacity_ref_1D_TLU_unit', 'm^3/s', ...
        'head_ref_1D_TLU', mat2str(Hk*1000/(rho*g0), 6), 'head_ref_1D_TLU_unit', 'm', ...
        'power_ref_1D_TLU', mat2str(Pk, 6), 'power_ref_1D_TLU_unit', 'kW', ...
        'omega_ref_1D', '1450', 'omega_ref_1D_unit', 'rpm', 'rho_ref_1D', num2str(rho));
    r = blk(LIB.lr, sprintf('Iso%d', i), [340 y 380 y+40]);
    set_param(r, 'restriction_type', 'foundation.enum.restriction_type.variable', 'min_area', '1e-9', 'max_area', '0.01', 'Cd', '0.9');
    constant(mdl, sprintf('iso%d_cmd', i), sprintf('ssc_iso(%d)*0.01', i), [300 y+60 350 y+75]);
    s = blk(LIB.sps, sprintf('iso%d_ps', i), [360 y+60 390 y+75]); set_param(s, 'Unit', 'm^2');
    add_line(mdl, sprintf('iso%d_cmd/1', i), sprintf('iso%d_ps/1', i));
    blk(LIB.fs, sprintf('FQ%d', i), [420 y 460 y+40]);
    blk(LIB.pss, sprintf('q%d_s', i), [480 y+50 510 y+65]); set_param([mdl sprintf('/q%d_s', i)], 'Unit', 'kg/s');
end
blk(LIB.fs, 'FQ', [560 160 600 200]); blk(LIB.pss, 'q_s', [620 210 650 225]); set_param([mdl '/q_s'], 'Unit', 'kg/s');
blk(LIB.prs, 'DP', [560 40 600 80]); blk(LIB.res, 'ResP', [640 40 680 70]);
blk(LIB.pss, 'H_s', [620 90 650 105]); set_param([mdl '/H_s'], 'Unit', 'kPa');
blk(LIB.ps, 'Hs', [660 160 700 200]);
constant(mdl, 'Hs_cmd', '-P.sys_Hs', [600 240 650 255]);
s = blk(LIB.sps, 'Hs_ps', [660 240 690 255]); set_param(s, 'Unit', 'kPa'); add_line(mdl, 'Hs_cmd/1', 'Hs_ps/1');
for b = 1:4
    y = 60 + 110*(b-1);
    pp = blk(LIB.pipe, sprintf('Pipe%d', b), [760 y 800 y+40]);
    set_param(pp, 'length', '40', 'area', num2str(pi/4*0.041^2), 'Dh', '0.041', 'length_add', '6');
    cl = blk(LIB.lr, sprintf('Coil%d', b), [840 y 880 y+40]);
    set_param(cl, 'restriction_type', 'foundation.enum.restriction_type.fixed', 'restriction_area', num2str(opts.CoilArea), 'Cd', '0.64');
    vv = blk(LIB.lr, sprintf('Valve%d', b), [920 y 960 y+40]);
    set_param(vv, 'restriction_type', 'foundation.enum.restriction_type.variable', 'min_area', '1e-9', ...
        'max_area', num2str(opts.ValveArea), 'Cd', '0.64');
    constant(mdl, sprintf('v%d_cmd', b), sprintf('max(1e-5, ssc_v(%d))*%g', b, opts.ValveArea), [880 y+60 940 y+75]);
    s = blk(LIB.sps, sprintf('v%d_ps', b), [950 y+60 980 y+75]); set_param(s, 'Unit', 'm^2');
    add_line(mdl, sprintf('v%d_cmd/1', b), sprintf('v%d_ps/1', b));
    blk(LIB.res, sprintf('ResR%d', b), [1000 y 1040 y+30]);
end
% ---- physical connections (port order established for R2024a blocks)
PH = @(n) get_param([mdl '/' n], 'PortHandles');
C = @(a, b) add_line(mdl, a, b, 'autorouting', 'smart');
C(PH('Solver').RConn(1), PH('ResS').LConn(1));
for i = 1:2
    pu = PH(sprintf('Pump%d', i)); w = PH(sprintf('W%d', i)); iso = PH(sprintf('Iso%d', i)); fq = PH(sprintf('FQ%d', i));
    C(PH('ResS').LConn(1), pu.RConn(3));                     % suction (inlet)
    C(pu.LConn(1), iso.LConn(1));                            % discharge -> isolation
    C(PH('n_ps').RConn(1), w.RConn(1));                      % speed command
    C(w.LConn(1), pu.RConn(1));                              % source R -> pump shaft R
    C(w.RConn(2), PH('Gnd').LConn(1)); C(pu.RConn(2), PH('Gnd').LConn(1));   % cases to reference
    C(PH(sprintf('iso%d_ps', i)).RConn(1), iso.LConn(2));
    C(iso.RConn(1), fq.LConn(1));
    C(fq.RConn(1), PH('FQ').LConn(1));                       % header
    C(fq.RConn(2), PH(sprintf('q%d_s', i)).LConn(1));
end
C(PH('FQ').LConn(1), PH('DP').LConn(1)); C(PH('DP').RConn(1), PH('ResP').LConn(1));
C(PH('DP').RConn(2), PH('H_s').LConn(1));
C(PH('FQ').RConn(2), PH('q_s').LConn(1));
C(PH('FQ').RConn(1), PH('Hs').LConn(1)); C(PH('Hs_ps').RConn(1), PH('Hs').LConn(2));
for b = 1:4
    pp = PH(sprintf('Pipe%d', b)); cl = PH(sprintf('Coil%d', b)); vv = PH(sprintf('Valve%d', b));
    C(PH('Hs').RConn(1), pp.LConn(1)); C(pp.RConn(1), cl.LConn(1)); C(cl.RConn(1), vv.LConn(1));
    C(PH(sprintf('v%d_ps', b)).RConn(1), vv.LConn(2)); C(vv.RConn(1), PH(sprintf('ResR%d', b)).LConn(1));
end
outs = {'H_s','q_s','q1_s','q2_s'};
for k = 1:numel(outs)
    add_block('simulink/Sinks/Out1', [mdl '/' strrep(outs{k}, '_s', '')], 'Position', [700 300+40*k 730 314+40*k]);
    add_line(mdl, [outs{k} '/1'], [strrep(outs{k}, '_s', '') '/1']);
end
set_param(mdl, 'StopTime', '30', 'Solver', 'ode23t', 'MaxStep', '0.5', 'SaveOutput', 'on', ...
    'SaveFormat', 'Array', 'ReturnWorkspaceOutputs', 'on', 'SaveTime', 'on');
add_block('built-in/Note', [mdl '/About'], 'Position', [40 520]);
set_param([mdl '/About'], 'Text', sprintf(['DATACORE-X CHW loop - Simscape Fluids (Isothermal Liquid)\n' ...
    'Built by dcx_build_hydraulics_ssc.m; validates plant/dcx_hydraulics.m\n' ...
    'Run dcx_validate_hydraulics for the comparison table.']));
if opts.Save, save_system(mdl, fullfile(fileparts(mfilename('fullpath')), [mdl '.slx'])); end
end

function b = constant(mdl, name, val, pos)
b = add_block('simulink/Sources/Constant', [mdl '/' name], 'Value', val, 'Position', pos);
end
function delete_line_safe(~), end
function b = pressurize(b, lib, LIB)
% closed loop held at a 600 kPa(abs) fill pressure by the expansion tank
if strcmp(lib, LIB.res)
    set_param(b, 'pressure_spec', 'foundation.enum.pressure_spec.specified', 'reservoir_pressure', '0.6', 'reservoir_pressure_unit', 'MPa');
elseif strcmp(lib, LIB.pipe)
    set_param(b, 'p0', '0.6', 'p0_unit', 'MPa');
end
end
