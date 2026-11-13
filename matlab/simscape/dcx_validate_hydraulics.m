function R = dcx_validate_hydraulics(opts)
%DCX_VALIDATE_HYDRAULICS Validate the reduced-order CHW hydraulics
%   (plant/dcx_hydraulics.m: parallel pumps H = a H0 n^2 - kp q^2 against
%   H = Hs + ks0/vmean^2 q^2) against the Simscape Fluids network built by
%   dcx_build_hydraulics_ssc (item 2).
%   1. Calibrate the control-valve area so both models share the design
%      operating point (one pump, full speed, valves open).
%   2. Sweep pump speed x number of pumps x valve opening (+ unequal valves)
%      and compare loop flow and pump differential pressure.
%   3. Fit the two-term law dp - Hs = (k_f + k_v/v^2) q^2 to the Simscape
%      points to quantify what the single-term law misses.
%   Writes simscape/results/hydraulics_validation_<profile>.csv/.mat/.png; the
%   design-profile run stores (k_f, k_v) in params/dcx_calibration.mat for the
%   calibrated profile.
arguments
    opts.Profile (1,1) string = "design"
end
here = fileparts(mfilename('fullpath')); out = fullfile(here, 'results'); if ~isfolder(out), mkdir(out); end
P = dcx_params('Profile', opts.Profile); assignin('base', 'P', P);
rho = 998.21; kg2l = 1000/rho;
% ---- reduced-model static operating point (same equations as dcx_hydraulics)
    function [H, q, qp] = rom(n, runp, v)
        ks = P.sys_kf + P.sys_kv/max(0.15, mean(v))^2;
        f = @(H) sum(runp.*sqrt(max(0, (P.pump_H0*n^2 - H)/P.pump_kp))) - sqrt(max(0, (H - P.sys_Hs)/ks));
        H = fzero(f, [P.sys_Hs, P.pump_H0*n^2]);
        qp = runp.*sqrt(max(0, (P.pump_H0*n^2 - H)/P.pump_kp)); q = sum(qp);
    end
% ---- 1. calibrate valve area at the design point
[Hd, qd] = rom(1, [1 0], [1 1 1 1]);
A = 1.31e-4; hist = [];
for it = 1:6
    dcx_build_hydraulics_ssc(P, 'ValveArea', A, 'Save', false);
    y = run1(1, [1 0], [1 1 1 1]); qs = y(2)*kg2l;
    hist(end+1, :) = [A qs y(1)]; %#ok<AGROW>
    if abs(qs/qd - 1) < 1e-4, break; end
    if it == 1, A2 = A*(qd/qs)^2; else
        A2 = A + (qd - qs)*(A - hist(end-1,1))/(qs - hist(end-1,2));
    end
    A = A2;
end
mdl = dcx_build_hydraulics_ssc(P, 'ValveArea', A, 'Save', true);
fprintf('valve area calibrated: %.4g m^2 (%d iterations), design q %.3f L/s (ROM %.3f)\n', A, it, qs, qd);
set_param(mdl, 'FastRestart', 'on');
% ---- 2. sweep
vs = [0.15 0.3 0.5 0.7 0.85 1.0]; ns = [0.5 0.75 1.0]; nps = [1 2];
cases = [];
for np = nps, for n = ns, for v = vs, cases(end+1,:) = [n np v v v v]; end, end, end %#ok<AGROW>
cases = [cases; 0.75 2 1 1 0.3 0.3; 0.75 2 1 0.6 0.6 0.2; 0.75 2 0.2 0.2 0.2 1; 1 1 1 1 1 0.15; 1 2 0.5 0.5 1 1];
rows = zeros(size(cases,1), 11);
for i = 1:size(cases,1)
    n = cases(i,1); runp = double((1:2) <= cases(i,2)); v = cases(i,3:6);
    y = run1(n, runp, v);
    [Hr, qr] = rom(n, runp, v);
    rows(i,:) = [n cases(i,2) v mean(v) y(1) y(2)*kg2l Hr qr];
end
set_param(mdl, 'FastRestart', 'off');
T = array2table(rows, 'VariableNames', {'speed','pumps','v1','v2','v3','v4','vmean','H_ssc_kpa','q_ssc_lps','H_rom_kpa','q_rom_lps'});
T.q_err_pct = 100*(T.q_rom_lps - T.q_ssc_lps)./T.q_ssc_lps;
T.H_err_kpa = T.H_rom_kpa - T.H_ssc_kpa;
% ---- 3. two-term fit on the uniform-valve points
u = all(abs(cases(:,3:6) - cases(:,3)) < 1e-12, 2);
X = [T.q_ssc_lps(u).^2, T.q_ssc_lps(u).^2./T.vmean(u).^2];
k2 = X \ (T.H_ssc_kpa(u) - P.sys_Hs);
pred2 = P.sys_Hs + X*k2;
R = struct('table', T, 'valve_area', A, 'calib_history', hist, ...
    'q_err_pct_max', max(abs(T.q_err_pct)), 'q_err_pct_rms', rms(T.q_err_pct), ...
    'q_err_pct_max_v_ge_0p3', max(abs(T.q_err_pct(T.vmean >= 0.3))), ...
    'H_err_kpa_max', max(abs(T.H_err_kpa)), 'k_two_term', k2, 'profile', opts.Profile, ...
    'two_term_dp_rmse_kpa', rms(pred2 - T.H_ssc_kpa(u)), 'one_term_dp_rmse_kpa', ...
    rms(P.sys_Hs + P.sys_ks0*T.q_ssc_lps(u).^2./T.vmean(u).^2 - T.H_ssc_kpa(u)));
tag = char(opts.Profile);
writetable(T, fullfile(out, ['hydraulics_validation_' tag '.csv']));
save(fullfile(out, ['hydraulics_validation_' tag '.mat']), 'R');
if opts.Profile == "design"
    % store the two-term system curve for the calibrated profile
    cf = fullfile(fileparts(here), 'params', 'dcx_calibration.mat');
    if isfile(cf)
        S = load(cf); C = S.C; C.sys_kf = k2(1); C.sys_kv = k2(2);
        C.sys_curve_source = 'Simscape Fluids (Isothermal Liquid) CHW network, dcx_validate_hydraulics';
        save(cf, 'C');
    end
end
fprintf(['%d operating points: flow error max %.2f %% (rms %.2f %%; max %.2f %% for vmean >= 0.3), ' ...
    'pump dp error max %.1f kPa\n'], height(T), R.q_err_pct_max, R.q_err_pct_rms, R.q_err_pct_max_v_ge_0p3, R.H_err_kpa_max);
fprintf('system-curve fit dp - Hs = (%.3f + %.3f/v^2) q^2: rmse %.2f kPa (single-term ks0/v^2: %.2f kPa)\n', ...
    k2(1), k2(2), R.two_term_dp_rmse_kpa, R.one_term_dp_rmse_kpa);
% ---- figure
f = figure('Visible', 'off', 'Position', [100 100 1100 420]);
subplot(1,2,1); hold on; grid on;
mk = {'o','s'}; 
for np = 1:2
    s = T.pumps == np;
    scatter(T.q_ssc_lps(s), T.q_rom_lps(s), 36, T.vmean(s), mk{np}, 'filled', 'DisplayName', sprintf('%d pump(s)', np));
end
lim = [0 max([T.q_ssc_lps; T.q_rom_lps])*1.05]; plot(lim, lim, 'k-', 'HandleVisibility', 'off');
xlabel('Simscape Fluids loop flow (L/s)'); ylabel('reduced-order model flow (L/s)'); legend('Location', 'northwest');
cb = colorbar; cb.Label.String = 'mean valve opening'; title('Loop flow');
subplot(1,2,2); hold on; grid on;
scatter(T.vmean, T.q_err_pct, 36, T.speed, 'filled');
xlabel('mean valve opening'); ylabel('flow error ROM - Simscape (%)'); cb = colorbar; cb.Label.String = 'pump speed';
yline(0, 'k-'); title('Flow error vs valve opening');
exportgraphics(f, fullfile(out, ['hydraulics_validation_' char(opts.Profile) '.png']), 'Resolution', 150); close(f);

    function y = run1(n, runp, v)
        assignin('base', 'ssc_n', n); assignin('base', 'ssc_iso', runp); assignin('base', 'ssc_v', v);
        so = sim('DCX_CHW_Hydraulics_SSC');
        y = so.yout(end, :);
    end
end
