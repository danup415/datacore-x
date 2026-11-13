function r = dcx_study_run(s)
%DCX_STUDY_RUN One closed-loop run of the study (see dcx_study_plan).
%   s: struct with climate, workload, scenario, seed, mode, rul_scale, start_day, key, experiment.
%   Scenarios (6 h from 11:00, +20 % IT ramp over 2 h in all scenarios):
%     normal  : no equipment fault
%     chiller : CH-01 degradation (onset 1 h, ramp 2 h), protection trip at 3.2 h
%     pump    : P-01 bearing degradation (onset 0.5 h, ramp 2.5 h), ISO zone-D trip at 0.94 of the ramp
%   A trip is UNPLANNED if the asset is still on duty (pump running / chiller carrying load) when it trips.
Th = 6; T = Th*3600; dt = 10;
P = dcx_params('Seed', 40 + s.seed, 'StartHour', 11, 'Horizon', T + 10, 'Profile', "calibrated", ...
    'Climate', s.climate, 'Workload', s.workload, 'StartDay', s.start_day);
FT = dcx_fault_table('it_load_increase', 'DCX', 'Severity', 0.2, 'Ramp', 7200);
switch s.scenario
    case "chiller"
        FT = dcx_fault_table(FT, 'chiller_degradation', 'CH-01', 'Severity', 1.0, 'Onset', 3600, 'Ramp', 7200);
        FT = dcx_fault_table(FT, 'chiller_trip', 'CH-01', 'Onset', 3.2*3600);
    case "pump"
        ramp = 2.5*3600; on = 1800;
        FT = dcx_fault_table(FT, 'pump_bearing', 'P-01', 'Severity', 1.0, 'Onset', on, 'Ramp', ramp);
        FT = dcx_fault_table(FT, 'pump_trip', 'P-01', 'Onset', on + 0.94*ramp);
end
S = DcxSupervisor(char(s.mode), P, 'RulScale', s.rul_scale);
tw = tic;
L = dcx_sim_matlab(P, FT, T, 'Log', dt, 'Supervisor', @(t, o) S.step(t, o), 'SupTs', 60);
wall = toc(tw);
% ---------------- energy / thermal
Ef = L.E_fac(end) - L.E_fac(1); Eit = sum(L.it)*dt/3600; Ec = sum(L.cool)*dt/3600;
% ---------------- unplanned trips (generic: asset on duty at trip time)
trips = 0; trip_pump = 0; trip_ch = 0;
for p = 1:3
    k = find(diff(L.pump_trip(:, p)) > 0, 1);
    if ~isempty(k) && L.pump_run(k, p) > 0, trips = trips + 1; trip_pump = 1; end
end
for c = 1:2
    k = find(diff(L.ch_trip(:, c)) > 0, 1);
    if ~isempty(k) && L.Qch(k, c) > 5, trips = trips + 1; trip_ch = 1; end
end
% ---------------- equipment risk exposure: time a running pump is in ISO 10816 zone C/D (> 4.5 mm/s)
risk_s = sum(any(L.pump_run > 0 & L.vib_p > 4.5, 2))*dt;
% ---------------- supervisor statistics
inf_ = L.supervisor; sm = NaN(1, numel(inf_)); pre = false(1, numel(inf_));
for i = 1:numel(inf_)
    if isfield(inf_{i}, 'solve_ms'), sm(i) = inf_{i}.solve_ms; end
    if isfield(inf_{i}, 'precool'), pre(i) = inf_{i}.precool; end
end
sm = sm(~isnan(sm));
if isempty(sm), sm = NaN; end
r = struct('key', s.key, 'experiment', s.experiment, 'climate', s.climate, 'workload', s.workload, ...
    'scenario', s.scenario, 'seed', s.seed, 'start_day', s.start_day, 'mode', s.mode, 'rul_scale', s.rul_scale, ...
    'energy_kwh', Ef, 'it_kwh', Eit, 'cooling_kwh', Ec, 'pue', Ef/Eit, 'peak_inlet_c', max(L.max_in), ...
    't_above_27_s', sum(L.max_in > 27)*dt, 't_above_28_s', sum(L.max_in > 28)*dt, ...
    'unplanned_trips', trips, 'trip_pump', trip_pump, 'trip_chiller', trip_ch, 'risk_zoneCD_s', risk_s, ...
    'pump_changeover', double(S.acted.pump), 'chiller_lead_transfer', double(S.acted.chiller_lead), ...
    'precool_min', sum(pre), 'mean_chws_sp', mean(L.sp(:, 1)), 'mean_sat_sp', mean(L.sp(:, 2)), ...
    'mean_wb_c', mean(L.wb), 'solve_ms_mean', mean(sm), 'solve_ms_p95', prctile(sm, 95), 'solve_ms_max', max(sm), ...
    'n_solves', sum(~isnan(sm)), 'wall_s', wall);
end
