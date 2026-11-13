function R = dcx_ssc_loop(opts)
%DCX_SSC_LOOP Closed-loop run with the Simscape Fluids hydraulics in the loop
%   versus the same run on the reduced-order (Simulink/ROM) hydraulics.
%   Scenario = the study's pump-bearing fault (dcx_study_run "pump"):
%   6 h from 11:00, +20 % IT ramp, P-01 bearing degradation from 0.5 h over
%   2.5 h, ISO zone-D trip at 0.94 of the ramp. Pune, diurnal workload,
%   seed 1 (start day 15). Controllers: PI-HA-EMPC and health-blind EMPC.
%   Writes control/results/ssc_loop/ (runs .mat, summary .csv/.json, figure).
%   R = dcx_ssc_loop()                     full 6 h, both controllers
%   R = dcx_ssc_loop('Hours', 0.5, 'Modes', "haempc")   quick check
arguments
    opts.Hours (1,1) double = 6
    opts.Modes (1,:) string = ["haempc" "empc"]
    opts.Seed (1,1) double = 1
    opts.Climate (1,1) string = "pune"
    opts.MacroStep (1,1) double = 10
    opts.Tag (1,1) string = ""
end
here = fileparts(mfilename('fullpath'));
out = fullfile(here, 'results', 'ssc_loop'); if ~isfolder(out), mkdir(out); end
T = opts.Hours*3600; dt = 10;
P = dcx_params('Seed', 40 + opts.Seed, 'StartHour', 11, 'Horizon', T + 10, 'Profile', "calibrated", ...
    'Climate', opts.Climate, 'Workload', "diurnal", 'StartDay', 15 + 36*(opts.Seed - 1));
FT = dcx_fault_table('it_load_increase', 'DCX', 'Severity', 0.2, 'Ramp', 7200);
ramp = 2.5*3600; on = 1800;
FT = dcx_fault_table(FT, 'pump_bearing', 'P-01', 'Severity', 1.0, 'Onset', on, 'Ramp', ramp);
FT = dcx_fault_table(FT, 'pump_trip', 'P-01', 'Onset', on + 0.94*ramp);
rows = {}; runs = struct();
for md = opts.Modes
    for hyd = ["rom" "simscape"]
        S = DcxSupervisor(char(md), P);
        args = {'Log', dt, 'Supervisor', @(t, o) S.step(t, o), 'SupTs', 60};
        C = [];
        if hyd == "simscape"
            C = DcxSscCosim(P, 'MacroStep', opts.MacroStep);
            args = [args, {'HydHook', @(k, t, X, H, F, O, Ap) C.hook(k, t, X, H, F, O, Ap)}]; %#ok<AGROW>
        end
        fprintf('[ssc-loop] %s / %s ...\n', md, hyd); tw = tic;
        L = dcx_sim_matlab(P, FT, T, args{:});
        wall = toc(tw);
        m = metrics(L, S, dt);
        m.mode = md; m.hydraulics = hyd; m.wall_s = wall;
        if ~isempty(C), m.ssc_calls = C.nCalls; m.ssc_wall_s = C.wall; clog = C.log; delete(C); else, m.ssc_calls = 0; m.ssc_wall_s = 0; clog = []; end
        rows{end+1} = m; %#ok<AGROW>
        runs.(md + "_" + hyd) = struct('L', rmfield(L, 'supervisor'), 'ssc_log', clog, 'm', m);
        fprintf('[ssc-loop] %s / %s: %.0f s wall, trips %d, changeover %s, peak inlet %.2f C, E %.1f kWh\n', ...
            md, hyd, wall, m.unplanned_trips, num2str(m.changeover_h), m.peak_inlet_c, m.energy_kwh);
    end
end
Tsum = struct2table([rows{:}]);
% ---------------- agreement Simscape-in-loop vs ROM (same controller)
cmp = {};
for md = opts.Modes
    a = runs.(md + "_rom").L; b = runs.(md + "_simscape").L;
    ok = a.t > 600;    % skip the first 10 min (Simscape start-up from rest)
    e = @(x, y) struct('rms', rms(x(ok) - y(ok)), 'max', max(abs(x(ok) - y(ok))), 'rel_rms_pct', 100*rms(x(ok) - y(ok))/max(eps, rms(x(ok))));
    c = struct('mode', md, 'flow_lps', e(a.q, b.q), 'dp_kpa', e(a.H, b.H), 'speed', e(a.n, b.n), ...
        'max_inlet_c', e(a.max_in, b.max_in), 'Tchws_c', e(a.Tchws, b.Tchws), 'pump_kw', e(sum(a.pump_kw, 2), sum(b.pump_kw, 2)), ...
        'facility_kw', e(a.fac, b.fac));
    cmp{end+1} = c; %#ok<AGROW>
end
R = struct('summary', Tsum, 'agreement', {cmp}, 'opts', opts, 'scenario', 'pump bearing (dcx_study_run "pump")');
tag = char(opts.Tag);
save(fullfile(out, ['ssc_loop' tag '.mat']), 'R', 'runs', '-v7.3');
writetable(Tsum, fullfile(out, ['ssc_loop_summary' tag '.csv']));
fid = fopen(fullfile(out, ['ssc_loop' tag '.json']), 'w'); fprintf(fid, '%s', jsonencode(struct('summary', table2struct(Tsum), 'agreement', {cmp}), 'PrettyPrint', true)); fclose(fid);
disp(Tsum(:, {'mode','hydraulics','unplanned_trips','changeover_h','trip_h','peak_inlet_c','t_above_27_s','energy_kwh','risk_zoneCD_s','wall_s','ssc_calls'}));
end

function m = metrics(L, S, dt)
Ef = L.E_fac(end) - L.E_fac(1);
trips = 0; trip_h = NaN;
for p = 1:3
    k = find(diff(L.pump_trip(:, p)) > 0, 1);
    if ~isempty(k) && L.pump_run(k, p) > 0, trips = trips + 1; trip_h = L.t(k+1)/3600; end
end
% changeover = first time P-01 stops running while not tripped
k = find(L.pump_run(:, 1) == 0 & L.pump_trip(:, 1) == 0 & L.t > 600, 1);
co = NaN; if ~isempty(k) && S.acted.pump, co = L.t(k)/3600; end
m = struct('energy_kwh', Ef, 'peak_inlet_c', max(L.max_in), 't_above_27_s', sum(L.max_in > 27)*dt, ...
    't_above_28_s', sum(L.max_in > 28)*dt, 'unplanned_trips', trips, 'trip_h', trip_h, 'changeover_h', co, ...
    'risk_zoneCD_s', sum(any(L.pump_run > 0 & L.vib_p > 4.5, 2))*dt, ...
    'mean_flow_lps', mean(L.q), 'mean_dp_kpa', mean(L.H), 'mean_pump_kw', mean(sum(L.pump_kw, 2)));
end
