function P = dcx_params(opts)
%DCX_PARAMS Parameters of the DATACORE-X reference facility (design assumptions).
%   P = dcx_params() returns the parameter struct shared by the MATLAB plant
%   functions, the Simulink model DCX_Facility and the tests. Values mirror
%   backend/datacorex/plant.py (Python surrogate) so both can be
%   cross-verified. All values are DESIGN ASSUMPTIONS for a hypothetical
%   8-rack facility, not measured data (calibration = item 3).
arguments
    opts.Seed (1,1) double = 7
    opts.StartHour (1,1) double = 10
    opts.UtilNoise (1,1) logical = true
    opts.Horizon (1,1) double = 6*3600
    opts.Profile (1,1) string = "design"      % "design" (Python-parity) | "calibrated" (item 3)
    opts.StartDay (1,1) double = 130          % day of year for weather-file runs (10 May: pre-monsoon peak)
    opts.Climate (1,1) string = "pune"        % weather year for the calibrated profile: "pune" | "frankfurt" (params/weather_<site>.mat)
    opts.Workload (1,1) string = "diurnal"    % IT utilisation profile: "diurnal" | "flat" | "bursty"
end
P.dt = 1.0;                       % s, plant/PLC/controller sample time
P.start_hour = opts.StartHour;
P.seed = opts.Seed;

% ---- physical constants
P.cp_air = 1.006; P.rho_air = 1.18; P.cp_w = 4.186; P.abs_hum = 0.0085;

% ---- geometry (registry, metres)
P.rack_x = [5.8 6.6 7.4 8.2 5.8 6.6 7.4 8.2];
P.rack_z = [4.6 4.6 4.6 4.6 7.4 7.4 7.4 7.4];
P.rack_phase = [1 2 3 1 2 3 1 2];          % L1/L2/L3 by rack index (i mod 3)
P.rack_gpu = [0 0 0 1 0 0 0 1];
P.rack_edge = double(P.rack_x == 5.8 | P.rack_x == 8.2);
P.crah_x = [3.5 10.5 3.5 10.5];
P.crah_z = [0.75 0.75 11.25 11.25];
w = zeros(8,4);
for r = 1:8
    for c = 1:4
        w(r,c) = 1/((P.rack_x(r)-P.crah_x(c))^2 + (P.rack_z(r)-P.crah_z(c))^2);
    end
end
P.crah_w = w;                                % inverse-square proximity weights

% ---- IT workload
rng(opts.Seed);
P.u_base = 0.55 + (0.72-0.55)*rand(1,8);
P.rack_P_idle = 3.0; P.rack_P_span = 13.0; P.rack_dT = 12.0; P.rack_C = 60.0;
% OU utilisation noise (tau 300 s, sigma 0.02), pre-generated for reproducibility
N = ceil(opts.Horizon/P.dt) + 2;
ou = zeros(N,8);
if opts.UtilNoise
    a = P.dt/300; s = 0.02*sqrt(2*P.dt/300);
    e = randn(N,8);
    for k = 2:N
        ou(k,:) = ou(k-1,:) - ou(k-1,:)*a + s*e(k,:);
    end
end
P.ou_noise = ou;     % used through a From Workspace block / indexed in MATLAB

% ---- CRAH
P.crah_m_max = 4.5; P.crah_fan_kw = 5.5; P.crah_NTU0 = 2.4; P.crah_q_nom = 1.6;
P.C_ha = 900.0; P.UA_env = 0.35;

% ---- CHW hydraulics
P.pump_H0 = 320; P.pump_kp = 2.2; P.sys_Hs = 40; P.sys_ks0 = 6.0;
P.sys_kf = 0; P.sys_kv = P.sys_ks0;   % system curve dp - Hs = (kf + kv/v^2) q^2
P.pump_q_bep = 5.0; P.pump_eta_bep = 0.72; P.pump_kw_rated = 4.0;

% ---- chillers / HX / towers
P.ch_cap_nom = 160; P.ch_carnot = 0.40; P.ch_plr_a = 0.35; P.ch_restart_s = 180; P.ch_hiplr_s = 120;
P.hx_eps = 0.72; P.q_cw = 9.0; P.cwp_kw = 3.2;
P.tower_app_nom = 3.0; P.tower_Qnom = 90; P.tower_fan_kw = 5.5;

% ---- electrical
P.ups_rated = 150; P.pdu_rated = 150; P.bat_cells = 160; P.bat_ah = 60; P.bat_R = 0.060;
P.bat_Cth = 180; P.bat_h = 0.04; P.tx_kva = 500; P.light_kw = 4.0;
P.gen_start_s = 10; P.ats_s = 2; P.retransfer_s = 60; P.cooldown_s = 120; P.mech_restart_s = 3;
P.gen_tank_L = 1200; P.gen_L_per_kWh = 0.27;

% ---- carbon: design profile keeps the Python-parity value; the calibrated
%      profile uses CEA CO2 Baseline Database v20.0 (FY2023-24) 0.727 kg/kWh
P.grid_ef_kg_per_kwh = 0.716;

% ---- ambient: synthetic diurnal (design) or measured weather year (calibrated)
P.use_weather = 0; P.start_day = opts.StartDay;
P.weather_db = zeros(1,8760); P.weather_wb = zeros(1,8760);
P.profile = char(opts.Profile);
P.climate = char(opts.Climate);
P.workload = find(opts.Workload == ["diurnal" "flat" "bursty"]);   % numeric code (code-generation friendly)
if isempty(P.workload), error('dcx:workload', 'Workload must be diurnal, flat or bursty'); end
if opts.Profile == "calibrated"
    f = fullfile(fileparts(mfilename('fullpath')), 'dcx_calibration.mat');
    if ~isfile(f), error('dcx:calib', 'run dcx_calibrate() first'); end
    S = load(f);
    P.ch_carnot = S.C.ch_carnot; P.ch_plr_a = S.C.ch_plr_a;
    if isfield(S.C, 'sys_kf'), P.sys_kf = S.C.sys_kf; P.sys_kv = S.C.sys_kv; end   % Simscape Fluids fit
    if isfield(S.C, 'tower_fan_kw'), P.tower_fan_kw = S.C.tower_fan_kw; end
    if isfield(S.C, 'grid_ef_kg_per_kwh'), P.grid_ef_kg_per_kwh = S.C.grid_ef_kg_per_kwh; end
    P.use_weather = 1; P.weather_db = S.C.weather.db; P.weather_wb = S.C.weather.wb;
    wf = fullfile(fileparts(mfilename('fullpath')), sprintf('weather_%s.mat', P.climate));
    if opts.Climate ~= "pune" || isfile(wf)
        if ~isfile(wf), error('dcx:weather', 'run dcx_weather("%s") first', P.climate); end
        Wd = load(wf); P.weather_db = Wd.W.db; P.weather_wb = Wd.W.wb;
        if isfield(Wd.W, 'grid_ef_kg_per_kwh'), P.grid_ef_kg_per_kwh = Wd.W.grid_ef_kg_per_kwh; end
    end
end

% ---- default setpoints (operator-adjustable)
P.sp = struct('supply_air_c',22.0,'chws_c',18.0,'dp_kpa',180.0, ...
              'tower_leaving_c',21.0,'max_inlet_c',25.0);

% ---- PI controller tunings (match the Python surrogate)
P.pi_valve = struct('kp',0.05,'ki',0.004,'lo',0.05,'hi',1.0,'u0',0.6);
P.pi_fan   = struct('kp',0.05,'ki',0.002,'lo',-0.3,'hi',0.5,'u0',0.0);
P.pi_pump  = struct('kp',0.0010,'ki',0.0002,'lo',0.30,'hi',1.0,'u0',0.75);
P.pi_tower = struct('kp',0.12,'ki',0.004,'lo',0.0,'hi',1.0,'u0',0.5);

% ---- actuator time constants (s)
P.tau = struct('valve',8,'fan_up',8,'fan_down',6,'vfd',5,'flow',3,'tower_fan',10, ...
               'Tpl',20,'Tca',15,'Tin',10,'Tchwr',40,'Tchws',60,'Tctl',90,'tx',600);
end
