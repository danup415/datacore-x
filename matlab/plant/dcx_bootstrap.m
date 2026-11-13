function [Y0, X0, ctrl0] = dcx_bootstrap(P)
%DCX_BOOTSTRAP Consistent initial outputs of every subsystem (used as Unit
%   Delay initial conditions in DCX_Facility and by dcx_sim_matlab).
X0 = dcx_initial_state(P);
P0 = P; P0.dt = 0;                 % dry evaluation: outputs without advancing states
ctrl0 = struct('fan_trim', P.pi_fan.u0, 'valve_cmd', P.pi_valve.u0*ones(1,4), ...
    'pump_cmd', P.pi_pump.u0, 'tower_cmd', P.pi_tower.u0);
FT = zeros(32,9);
D = dcx_disturbance(0, zeros(1,8), P);
F = dcx_faults(0, FT);
cmd = struct('seq',0,'code',0,'asset',0,'value',0);
[~, O] = dcx_plc(X0.plc, F, [1 1], [0.4 0], cmd, P0);
Ap = struct('Tin', X0.air.Tin, 'Tha', X0.air.Tha, 'valve', X0.air.valve, 'Q_tot', 95, 'fan_kw', zeros(1,4));
Rp = struct('m_tot', 7.8, 'm', 7.8/8*ones(1,8), 'Tout', X0.rack.Tout, 'P_it', 95, 'P', 95/8*ones(1,8));
Hp = struct('q', X0.hyd.q, 'P_tot', 1.0);
Cp = struct('Tchws', X0.chw.Tchws, 'P_ch', 10, 'P_tower', 1, 'cwp_kw', P.cwp_kw);
for pass = 1:3
    [~, R] = dcx_racks(X0.rack, D, F, O, Ap, P0);
    [~, A] = dcx_air(X0.air, D, F, O, Rp, Hp, Cp, ctrl0, P0);
    [~, H] = dcx_hydraulics(X0.hyd, F, O, Ap, ctrl0, P0);
    [~, C] = dcx_chwplant(X0.chw, D, F, O, Ap, Hp, ctrl0, P.sp, P0);
    [~, E] = dcx_electrical(X0.elec, F, O, Rp, Ap, Hp, Cp, P0);
    Rp = R; Ap = A; Hp = H; Cp = C;
end
Y0 = struct('R', R, 'A', A, 'H', H, 'C', C, 'E', E, 'O', O);
end
