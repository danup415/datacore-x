function C = dcx_calibrate(opts)
%DCX_CALIBRATE Calibrate the DCX plant against external reference data (item 3).
%   (1) Chiller performance map -> ASHRAE 90.1 Table 6.8.1-3 code-minimum,
%       water-cooled positive-displacement, < 75 ton class (Path A):
%       full load <= 0.750 kW/ton, IPLV.IP <= 0.600 kW/ton at AHRI 550/590
%       rating conditions (44 F leaving CHW; ECWT 85/75/65/65 F at
%       100/75/50/25 % load; IPLV = 0.01A + 0.42B + 0.45C + 0.12D).
%       Unknowns: Carnot fraction eta_c and part-load coefficient a.
%   (2) Ambient: real hourly dry-bulb + RH for Pune (18.52 N, 73.86 E) from
%       the Open-Meteo historical archive; wet-bulb by Stull (2011).
%   (3) Cooling tower fan power -> ASHRAE 90.1 Table 6.8.1-7, propeller/axial
%       open-circuit tower: >= 40.2 gpm/hp at 95 F entering / 85 F leaving /
%       75 F entering wet-bulb (range = approach = 5.56 K). The tower's rated
%       flow at those conditions is found from the DCX approach model, then
%       fan power = gpm/40.2 hp (code-minimum), motor efficiency 0.90.
%   (4) CHW pumping check -> ASHRAE 90.1 Appendix G (G3.1.3.10) baseline
%       22 W/gpm at design flow; reported, pump curve kept if within 10 %.
%   (5) CRAH fan check -> 90.1 fan power limitation, variable volume,
%       Option 1: nameplate hp <= cfm x 0.0015 (Table 6.5.3.1-1).
%   (6) Grid emission factor -> CEA CO2 Baseline Database v20.0 (Dec 2024,
%       FY 2023-24): weighted average 0.727 tCO2/MWh (combined margin 0.757).
%   Writes params/dcx_calibration.mat, used by dcx_params('Profile','calibrated').
%   Replace (1) with the selected product's AHRI-certified data sheet when a
%   specific chiller is chosen.
arguments
    opts.Year (1,1) double = 2025
    opts.Lat (1,1) double = 18.52
    opts.Lon (1,1) double = 73.86
end
here = fileparts(mfilename('fullpath'));
% ---------------- (1) chiller map ------------------------------------------
TON = 3.517;                       % kW per ton
cop_fl = TON/0.750; cop_iplv = TON/0.600;
f2c = @(F) (F - 32)/1.8;
Tlwt = f2c(44); ecwt = f2c([85 75 65 65]); plr = [1 0.75 0.5 0.25];
model = @(x, p, e) x(1)*(Tlwt - 2 + 273.15)./((e + 5.5 + 273.15) - (Tlwt - 2 + 273.15)).*(1 - x(2)*(1 - max(p, 0.15)).^2);
res = @(x) [model(x, 1, ecwt(1)) - cop_fl; ...
            [0.01 0.42 0.45 0.12]*model(x, plr, ecwt)' - cop_iplv];
x = fsolve(res, [0.45 0.35], optimoptions('fsolve', 'Display', 'off'));
C.ch_carnot = x(1); C.ch_plr_a = x(2);
C.chiller_check = table(plr', ecwt', model(x, plr, ecwt)', TON./model(x, plr, ecwt)', ...
    'VariableNames', {'plr','ecwt_c','cop','kw_per_ton'});
C.chiller_source = 'ASHRAE 90.1 Table 6.8.1-3, water-cooled positive displacement < 75 tons, Path A (FL 0.750, IPLV 0.600 kW/ton), AHRI 550/590 rating conditions';
P0 = dcx_params();
C.cop_design_point_before = model([P0.ch_carnot 0.35], 0.4, 25);
C.cop_design_point_after = model(x, 0.4, 25);
% ---------------- (2) weather ------------------------------------------------
url = sprintf(['https://archive-api.open-meteo.com/v1/archive?latitude=%.2f&longitude=%.2f' ...
    '&start_date=%d-01-01&end_date=%d-12-31&hourly=temperature_2m,relative_humidity_2m&timezone=Asia%%2FKolkata'], ...
    opts.Lat, opts.Lon, opts.Year, opts.Year);
W = webread(url, weboptions('Timeout', 60));
T = W.hourly.temperature_2m(:); RH = W.hourly.relative_humidity_2m(:);
ok = ~isnan(T) & ~isnan(RH);
T = fillmissing(T, 'linear'); RH = fillmissing(RH, 'linear');
Tw = T.*atan(0.151977*sqrt(RH + 8.313659)) + atan(T + RH) - atan(RH - 1.676331) ...
     + 0.00391838*RH.^1.5.*atan(0.023101*RH) - 4.686035;          % Stull (2011), RH in %
n = min(8760, numel(T));
C.weather = struct('db', T(1:n)', 'wb', Tw(1:n)', 'rh', RH(1:n)', 'year', opts.Year, ...
    'source', sprintf('Open-Meteo historical archive (ERA5-based), lat %.2f lon %.2f, %d, hourly; wet-bulb Stull (2011)', opts.Lat, opts.Lon, opts.Year), ...
    'valid_fraction', mean(ok));
C.weather_stats = struct('db_max', max(T), 'wb_max', max(Tw), 'wb_p996', prctile(Tw, 99.6), 'wb_mean', mean(Tw), 'db_mean', mean(T));
% ---------------- (3) cooling tower fan power --------------------------------
GPM = 15.850; HP = 0.7457; eta_m = 0.90;
dT_r = 10/1.8;                                    % 10 F range = 10 F approach
Qr = P0.tower_Qnom*(dT_r/P0.tower_app_nom)^(1/0.6);   % kW at approach 5.56 K, full speed
m_r = Qr/(4.186*dT_r);                            % kg/s ~ L/s
gpm_r = m_r*GPM;
C.tower_fan_kw = gpm_r/40.2*HP/eta_m;
C.tower_check = struct('rated_kw', Qr, 'rated_gpm', gpm_r, 'fan_hp_max', gpm_r/40.2, ...
    'fan_kw_before', P0.tower_fan_kw, 'fan_kw_after', C.tower_fan_kw, ...
    'gpm_per_hp_before', gpm_r/(P0.tower_fan_kw*eta_m/HP), ...
    'source', 'ASHRAE 90.1 Table 6.8.1-7 propeller/axial open-circuit tower >= 40.2 gpm/hp at 95/85/75 F');
% ---------------- (4) CHW pumping check ---------------------------------------
ks = P0.sys_ks0; H0 = P0.pump_H0; kp = P0.pump_kp; Hs = P0.sys_Hs;
H = fzero(@(H) sqrt(max(0,(H0-H)/kp)) - sqrt(max(0,(H-Hs)/ks)), [Hs H0]);
qd = sqrt((H0-H)/kp); x = qd/P0.pump_q_bep; eta = P0.pump_eta_bep*(1-0.8*(x-1)^2);
C.pump_check = struct('design_q_lps', qd, 'design_gpm', qd*GPM, 'head_kpa', H, 'kw', qd*H/1000/eta, ...
    'w_per_gpm', 1000*qd*H/1000/eta/(qd*GPM), 'target_w_per_gpm', 22, ...
    'source', 'ASHRAE 90.1 Appendix G, G3.1.3.10: 22 W/gpm CHW system pumping at design flow');
C.pump_check.within_10pct = abs(C.pump_check.w_per_gpm/22 - 1) <= 0.10;
% ---------------- (5) CRAH fan check -------------------------------------------
cfm = P0.crah_m_max/1.2*2118.88;
C.crah_check = struct('cfm', cfm, 'hp_allow', 0.0015*cfm, 'kw_allow', 0.0015*cfm*0.7457, ...
    'kw_model', P0.crah_fan_kw, 'compliant', P0.crah_fan_kw <= 0.0015*cfm*0.7457, ...
    'source', 'ASHRAE 90.1 fan power limitation, VAV Option 1, hp <= CFM x 0.0015 (as adopted in WAC 51-11C)');
% ---------------- (6) grid emission factor ------------------------------------
C.grid_ef_kg_per_kwh = 0.727;
C.grid_ef_source = 'CEA CO2 Baseline Database v20.0 (Dec 2024), FY2023-24 weighted average 0.727 tCO2/MWh (CM 0.757)';
C.created = datetime('now');
save(fullfile(here, 'dcx_calibration.mat'), 'C');
fprintf('Chiller map: eta_c %.3f (was %.2f), part-load a %.3f (was 0.35); COP at design point %.2f -> %.2f\n', ...
    C.ch_carnot, P0.ch_carnot, C.ch_plr_a, C.cop_design_point_before, C.cop_design_point_after);
disp(C.chiller_check);
fprintf('Tower: rated %.0f kW / %.0f gpm at 95/85/75 F; fan %.2f -> %.2f kW (was %.1f gpm/hp)\n', ...
    C.tower_check.rated_kw, C.tower_check.rated_gpm, P0.tower_fan_kw, C.tower_fan_kw, C.tower_check.gpm_per_hp_before);
fprintf('CHW pump design point: %.0f gpm, %.2f kW, %.1f W/gpm (Appendix G 22)\n', C.pump_check.design_gpm, C.pump_check.kw, C.pump_check.w_per_gpm);
fprintf('CRAH fan: %.0f cfm, model %.1f kW vs allowance %.1f kW (compliant %d)\n', C.crah_check.cfm, C.crah_check.kw_model, C.crah_check.kw_allow, C.crah_check.compliant);
fprintf('Weather %d: db max %.1f C, wb max %.1f C, wb 99.6%% %.1f C, wb mean %.1f C\n', opts.Year, ...
    C.weather_stats.db_max, C.weather_stats.wb_max, C.weather_stats.wb_p996, C.weather_stats.wb_mean);
end
