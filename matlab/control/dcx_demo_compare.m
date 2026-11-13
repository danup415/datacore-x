function out = dcx_demo_compare(varargin)
%DCX_DEMO_COMPARE Run the study's fault scenarios with health-blind EMPC and with
%   PI-HA-EMPC on identical conditions and export the time series for the
%   dashboard comparison page (app/datacore-x/frontend/compare/compare_runs.json).
%
%   These are real closed-loop runs of the same plant, controllers and fault
%   definitions used in the paper (dcx_study_run), logged every 60 s.
%
%   dcx_demo_compare                       % Pune, diurnal workload, seed 1
%   dcx_demo_compare('Seed', 3, 'Climate', "frankfurt")
o = struct('Seed', 1, 'Climate', "pune", 'Workload', "diurnal");
for i = 1:2:numel(varargin), o.(varargin{i}) = varargin{i+1}; end
here = fileparts(mfilename('fullpath'));
dst = fullfile(fileparts(fileparts(here)), 'app', 'datacore-x', 'frontend', 'compare', 'compare_runs.json');

scen = ["pump" "chiller"];
modes = ["empc" "haempc"];
out = struct('meta', struct('climate', o.Climate, 'workload', o.Workload, 'seed', o.Seed, ...
    'start_day', 15 + 36*(o.Seed - 1), 'step_s', 60, 'generated', char(datetime('now', 'Format', 'yyyy-MM-dd HH:mm')), ...
    'note', 'Closed-loop MATLAB runs from the PI-HA-EMPC study (dcx_study_run definitions), identical plant, weather, workload and fault for both controllers.'));
for sc = scen
    for md = modes
        fprintf('[demo] %s / %s ... ', sc, md); tw = tic;
        out.(char(sc)).(char(md)) = one_run(o, sc, md);
        fprintf('%.0f s\n', toc(tw));
    end
end
if ~isfolder(fileparts(dst)), mkdir(fileparts(dst)); end
fid = fopen(dst, 'w'); fwrite(fid, jsonencode(out), 'char'); fclose(fid);
fprintf('[demo] wrote %s\n', dst);
end

function R = one_run(o, scenario, mode)
Th = 6; T = Th*3600; dt = 60;
P = dcx_params('Seed', 40 + o.Seed, 'StartHour', 11, 'Horizon', T + 10, 'Profile', "calibrated", ...
    'Climate', o.Climate, 'Workload', o.Workload, 'StartDay', 15 + 36*(o.Seed - 1));
FT = dcx_fault_table('it_load_increase', 'DCX', 'Severity', 0.2, 'Ramp', 7200);
switch scenario
    case "chiller"
        FT = dcx_fault_table(FT, 'chiller_degradation', 'CH-01', 'Severity', 1.0, 'Onset', 3600, 'Ramp', 7200);
        FT = dcx_fault_table(FT, 'chiller_trip', 'CH-01', 'Onset', 3.2*3600);
    case "pump"
        ramp = 2.5*3600; on = 1800;
        FT = dcx_fault_table(FT, 'pump_bearing', 'P-01', 'Severity', 1.0, 'Onset', on, 'Ramp', ramp);
        FT = dcx_fault_table(FT, 'pump_trip', 'P-01', 'Onset', on + 0.94*ramp);
end
S = DcxSupervisor(char(mode), P, 'RulScale', 1);
L = dcx_sim_matlab(P, FT, T, 'Log', dt, 'Supervisor', @(t, ob) S.step(t, ob), 'SupTs', 60);
n = numel(L.t);
hi_p = nan(n, 3); rul_p = nan(n, 1); hi_c = nan(n, 1); rul_c = nan(n, 1); pre = false(n, 1);
for i = 1:numel(L.supervisor)
    s = L.supervisor{i}; [~, k] = min(abs(L.t - s.t));
    if isfield(s, 'HI') && isstruct(s.HI)
        hi_p(k, :) = s.HI.pump_hi; rul_p(k) = s.HI.pump_rul_min; hi_c(k) = s.HI.chiller_hi; rul_c(k) = s.HI.chiller_rul_min;
    end
    if isfield(s, 'precool'), pre(k) = s.precool; end
end
hi_p = fillmissing(hi_p, 'previous'); hi_c = fillmissing(hi_c, 'previous');
rul_p(~isfinite(rul_p)) = NaN; rul_c(~isfinite(rul_c)) = NaN;
r2 = @(x) round(x*100)/100;
R = struct('t_min', r2(L.t/60), 'vib', r2(L.vib_p), 'pump_run', double(L.pump_run > 0), ...
    'pump_trip', double(L.pump_trip > 0), 'ch_load', r2(L.Qch), 'ch_trip', double(L.ch_trip > 0), ...
    'max_inlet', r2(L.max_in), 'cool_kw', r2(L.cool), 'fac_kw', r2(L.fac), 'it_kw', r2(L.it), ...
    'pump_hi', r2(hi_p), 'pump_rul_min', r2(rul_p), 'chiller_hi', r2(hi_c), 'chiller_rul_min', r2(rul_c), ...
    'precool', double(pre), 'chws_sp', r2(L.sp(:, 1)), ...
    'energy_kwh', r2(L.E_fac(end) - L.E_fac(1)), 'cool_kwh', r2(sum(L.cool)*dt/3600), ...
    'pump_changeover', double(S.acted.pump), 'chiller_lead_transfer', double(S.acted.chiller_lead));
end
