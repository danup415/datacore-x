function C = dcx_credibility()
%DCX_CREDIBILITY Model-credibility evidence for the paper (simulation only).
%   1. Energy balances on the calibrated plant (Pune and Frankfurt, 6 h):
%        room air   : IT heat + envelope gain - CRAH coil duty  (vs IT heat)
%        CHW loop   : coil duty - (economiser HX + chiller evaporator duty)
%        condenser  : heat rejected - (HX + evaporator duty + compressor power)
%        electrical : facility - (IT + cooling + distribution losses + lighting)
%        energy     : metered facility energy vs integral of facility power
%   2. Step responses (closed loop, PI baseline): +20 % IT load step,
%      CHW supply setpoint 18 -> 20 C, supply-air setpoint 22 -> 23 C:
%      2 % settling time and overshoot of the controlled variables.
%   3. Calibration evidence figure (chiller map vs ASHRAE 90.1 ratings, weather,
%      Simscape hydraulic validation) and a summary table.
%   Writes control/results/credibility/{credibility.json, *.csv, *.pdf, *.png}.
here = fileparts(mfilename('fullpath')); out = fullfile(here, 'results', 'credibility');
if ~isfolder(out), mkdir(out); end
C = struct();
% ------------------------------------------------------------ 1. energy balances
rows = {};
for cl = ["pune" "frankfurt"]
    P = dcx_params('Seed', 41, 'StartHour', 11, 'Horizon', 6*3600 + 10, 'Profile', "calibrated", 'Climate', cl, 'StartDay', 196);
    FT = dcx_fault_table('it_load_increase', 'DCX', 'Severity', 0.2, 'Ramp', 7200);
    L = dcx_sim_matlab(P, FT, 6*3600, 'Log', 10);
    k = L.t > 2*3600;                                  % exclude start-up transient
    env = P.UA_env*(L.db + 4 - L.Tha);
    Qch = sum(L.Qch, 2);
    light = P.light_kw*double(L.bus ~= 0);
    % recirculation enthalpy: rack inlets are blended with hot-aisle air without removing that
    % air from the hot-aisle balance (model simplification) -> appears as extra coil load
    recirc = sum(L.rackP./P.rack_dT.*(L.Tin - L.Tca), 2);   % inlet blending relative to the cold aisle
    r_room_raw = mean(L.it(k) + env(k) - L.Qcoil(k))/mean(L.it(k));
    r_room = mean(L.it(k) + env(k) + recirc(k) - L.Qcoil(k))/mean(L.it(k));
    recirc_pct = 100*mean(recirc(k))/mean(L.Qcoil(k));
    r_chw = mean(L.Qcoil(k) - (L.Qhx(k) + Qch(k)))/mean(L.Qcoil(k));
    r_cw = mean(L.Qrej(k) - (L.Qhx(k) + Qch(k) + L.P_ch(k)))/mean(L.Qrej(k));
    r_el = max(abs(L.fac - (L.it + L.cool + L.P_loss + light)));
    Eint = sum(L.fac(2:end))*10/3600; Emet = L.E_fac(end) - L.E_fac(1);
    rows(end+1, :) = {cl, 100*r_room_raw, recirc_pct, 100*r_room, 100*r_chw, 100*r_cw, r_el, 100*(Emet - Eint)/Eint, mean(L.it(k)), mean(L.Qcoil(k)), mean(L.wb)}; %#ok<AGROW>
end
C.balance = cell2table(rows, 'VariableNames', {'climate','room_residual_raw_pct','recirc_term_pct_of_coil','room_residual_pct', ...
    'chw_residual_pct','condenser_residual_pct','electrical_max_abs_kw','energy_meter_vs_integral_pct','mean_it_kw','mean_coil_kw','mean_wb_c'});
writetable(C.balance, fullfile(out, 'energy_balance.csv'));
disp(C.balance)

% ------------------------------------------------------------ 2. step responses
T = 3*3600; ts = 3600;
P = dcx_params('Seed', 41, 'StartHour', 11, 'Horizon', T + 10, 'Profile', "calibrated", 'Climate', "pune", ...
    'StartDay', 196, 'UtilNoise', false, 'Workload', "flat");
P.weather_wb(:) = 20; P.weather_db(:) = 27;           % constant ambient isolates the step
steps = struct('name', {'IT load +20 %', 'CHW supply SP 18 -> 20 C', 'Supply-air SP 22 -> 23 C'}, ...
    'kind', {'it', 'chws', 'sat'});
srows = {}; f = figure('Visible', 'off', 'Position', [100 100 1100 330]);
for i = 1:3
    FT = zeros(32, 9); sup = [];
    switch steps(i).kind
        case 'it',   FT = dcx_fault_table('it_load_increase', 'DCX', 'Severity', 0.2, 'Onset', ts, 'Ramp', 0);
        case 'chws', sup = @(t, o) spstep(t, o, 'chws_c', 20, ts);
        case 'sat',  sup = @(t, o) spstep(t, o, 'supply_air_c', 23, ts);
    end
    if isempty(sup), L = dcx_sim_matlab(P, FT, T, 'Log', 10);
    else, L = dcx_sim_matlab(P, FT, T, 'Log', 10, 'Supervisor', sup, 'SupTs', 60); end
    sig = {'Tchws', L.Tchws; 'Tsup (mean)', mean(L.Tsup, 2); 'max inlet', L.max_in; 'facility kW', L.fac};
    subplot(1, 3, i); hold on; grid on;
    for j = 1:size(sig, 1)
        y = sig{j, 2}; [tset, ovs, dy, pk, mode] = stepmetrics(L.t, y, ts, j == 4);
        srows(end+1, :) = {steps(i).name, sig{j, 1}, mode, dy, tset/60, ovs, pk}; %#ok<AGROW>
        if j <= 3, plot((L.t - ts)/60, y - mean(y(L.t < ts & L.t > ts - 600)), 'LineWidth', 1.1, 'DisplayName', sig{j, 1}); end
    end
    xline(0, 'k:', 'HandleVisibility', 'off'); xlim([-10 120]); xlabel('time after step (min)'); ylabel('\Delta from pre-step (K)');
    title(steps(i).name); if i == 1, legend('Location', 'best'); end
end
exportgraphics(f, fullfile(out, 'fig_step_responses.pdf')); exportgraphics(f, fullfile(out, 'fig_step_responses.png'), 'Resolution', 200); close(f);
C.steps = cell2table(srows, 'VariableNames', {'step','signal','response','final_change','settling_min','overshoot_pct','peak_deviation'});
writetable(C.steps, fullfile(out, 'step_responses.csv'));
disp(C.steps)

% ------------------------------------------------------------ 3. calibration evidence
K = load(fullfile(fileparts(here), 'params', 'dcx_calibration.mat')); K = K.C;
Wp = load(fullfile(fileparts(here), 'params', 'weather_pune.mat')); Wf = load(fullfile(fileparts(here), 'params', 'weather_frankfurt.mat'));
f = figure('Visible', 'off', 'Position', [100 100 1100 330]);
subplot(1, 3, 1); hold on; grid on;
cc = K.chiller_check; plot(100*cc.plr, cc.kw_per_ton, 'o-', 'LineWidth', 1.2, 'DisplayName', 'model at AHRI conditions');
plot(100, 0.750, 'ks', 'MarkerFaceColor', 'k', 'DisplayName', 'ASHRAE 90.1 FL 0.750');
iplv = [0.01 0.42 0.45 0.12]*(3.517./cc.cop);  % harmonic-type check printed below
yline(0.600, 'k--', 'IPLV 0.600', 'HandleVisibility', 'off');
xlabel('part load (%)'); ylabel('kW/ton'); title('Chiller map vs ASHRAE 90.1 Table 6.8.1-3'); legend('Location', 'north');
subplot(1, 3, 2); hold on; grid on;
histogram(Wp.W.wb, 'BinWidth', 1, 'Normalization', 'probability', 'DisplayName', 'Pune 2025');
histogram(Wf.W.wb, 'BinWidth', 1, 'Normalization', 'probability', 'DisplayName', 'Frankfurt 2025');
xlabel('wet-bulb temperature (\circC)'); ylabel('fraction of hours'); title('Weather years (Open-Meteo ERA5)'); legend;
subplot(1, 3, 3); hold on; grid on;
hv = fullfile(fileparts(here), 'simscape', 'results', 'hydraulics_validation_calibrated.csv');
if isfile(hv)
    H = readtable(hv); scatter(H.q_ssc_lps, H.q_rom_lps, 20, H.vmean, 'filled'); lim = [0 max(H.q_ssc_lps)*1.05];
    plot(lim, lim, 'k-'); xlabel('Simscape Fluids flow (L/s)'); ylabel('reduced-order flow (L/s)'); title('CHW hydraulics vs Simscape');
end
exportgraphics(f, fullfile(out, 'fig_calibration.pdf')); exportgraphics(f, fullfile(out, 'fig_calibration.png'), 'Resolution', 200); close(f);
C.calibration = struct('chiller_eta_c', K.ch_carnot, 'chiller_plr_a', K.ch_plr_a, 'chiller_check', cc, ...
    'iplv_kw_per_ton_model', 3.517/([0.01 0.42 0.45 0.12]*cc.cop), 'tower', K.tower_check, 'pump', K.pump_check, ...
    'crah', K.crah_check, 'grid_ef_india', K.grid_ef_kg_per_kwh, 'grid_ef_germany', Wf.W.grid_ef_kg_per_kwh, ...
    'weather_pune', Wp.W.stats, 'weather_frankfurt', Wf.W.stats);
fid = fopen(fullfile(out, 'credibility.json'), 'w'); fprintf(fid, '%s', jsonencode(C, 'PrettyPrint', true)); fclose(fid);
end

function [sp, cmds, info] = spstep(t, obs, field, val, ts)
sp = obs.sp; cmds = zeros(0, 3); info = struct('t', t);
if t >= ts, sp.(field) = val; end
end

function [tset, ovs, dy, pk, mode] = stepmetrics(t, y, ts, ispower)
% tracked response (final change > threshold): 2 % settling time and overshoot.
% regulated variable (returns to its setpoint): peak deviation and recovery time
% back inside +-0.1 K (+-0.5 kW for power).
y0 = mean(y(t < ts & t > ts - 600)); y1 = mean(y(t > t(end) - 1200));
dy = y1 - y0; after = t >= ts; ta = t(after); ya = y(after);
thr = 0.05; band_reg = 0.1; if ispower, thr = 0.5; band_reg = 0.5; end
pk = max(abs(ya - y0));
if abs(dy) >= thr
    mode = "tracked"; band = 0.02*abs(dy);
    out = find(abs(ya - y1) > band, 1, 'last');
    if isempty(out), tset = 0; else, tset = ta(min(out + 1, numel(ta))) - ts; end
    ovs = 100*max(0, max(sign(dy)*(ya - y1)))/abs(dy);
else
    mode = "regulated"; ovs = NaN;
    out = find(abs(ya - y0) > band_reg, 1, 'last');
    if isempty(out), tset = 0; else, tset = ta(min(out + 1, numel(ta))) - ts; end
end
end
