function M = dcx_ident(opts)
%DCX_IDENT Identify the supervisory prediction model for the MPC (item 7).
%   Excites the verified plant with random steps on the three supervisory
%   setpoints and identifies a discrete state-space model (Ts = 60 s):
%     inputs  u = [CHW supply sp, CRAH supply-air sp, max-inlet target] (MV)
%                 + [IT load kW, ambient wet-bulb] (measured disturbances)
%     outputs y = [max rack inlet degC, facility power kW]
%   Saves control/dcx_mpc_model.mat. Validation fit on a held-out record.
arguments
    opts.Hours (1,1) double = 12
    opts.Order (1,1) double = 4
    opts.Seed (1,1) double = 11
    opts.Profile (1,1) string = "design"
    opts.Method (1,1) string = "ssest"       % "ssest" | "n4sid" | "auto" (best validation fit)
    opts.Orders (1,:) double = []            % candidate orders for "auto"
    opts.Data = []                           % reuse a record from a previous call (M.data)
    opts.Climate (1,1) string = "pune"
    opts.Days (1,:) double = 130             % start days; >1 -> multi-experiment identification across seasons
end
here = fileparts(mfilename('fullpath'));
rng(opts.Seed);
nd = numel(opts.Days);
T = opts.Hours*3600/nd;                       % record length per start day
lo = [16 19.5 23.0]; hi = [21 24.0 26.5];
nseg = ceil(T/900);
rec = zeros(0, 8); exps = {};
    function [sp, cmds, info] = sup(t, obs)
        seg = min(nseg, floor(t/900) + 1);
        sp = obs.sp; sp.chws_c = U(seg,1); sp.supply_air_c = U(seg,2); sp.max_inlet_c = U(seg,3);
        cmds = zeros(0,3);
        info = [t, U(seg,:), obs.fac(1), obs.fac(9), obs.fac(6), obs.fac(2)];
        rec(end+1, :) = info;
    end
if isempty(opts.Data)
    for di = 1:nd
        P = dcx_params('Seed', opts.Seed + di - 1, 'StartHour', 0, 'Horizon', T + 10, 'Profile', opts.Profile, ...
            'Climate', opts.Climate, 'StartDay', opts.Days(di));
        FT = dcx_fault_table('it_load_increase', 'DCX', 'Severity', 0.25, 'Onset', T/3, 'Ramp', T/3);
        U = lo + (hi - lo).*rand(nseg, 3);
        rec = zeros(0, 8);
        dcx_sim_matlab(P, FT, T, 'Log', 60, 'Supervisor', @sup, 'SupTs', 60);
        exps{di} = rec; %#ok<AGROW>
    end
else
    exps = opts.Data; if ~iscell(exps), exps = {exps}; end
end
allr = vertcat(exps{:});
U0 = mean(allr(:, 2:6)); Y0 = mean(allr(:, 7:8));
ze = []; zv = [];
for di = 1:numel(exps)
    r_ = exps{di}; u = r_(:, 2:6) - U0; y = r_(:, 7:8) - Y0; n = size(u, 1); half = floor(n*0.7);
    e1 = iddata(y(1:half,:), u(1:half,:), 60); v1 = iddata(y(half+1:end,:), u(half+1:end,:), 60);
    if isempty(ze), ze = e1; zv = v1; else, ze = merge(ze, e1); zv = merge(zv, v1); end
end
ze.InputName = {'chws_sp','sat_sp','maxin_sp','it_kw','wb'}; ze.OutputName = {'max_inlet','p_fac'};
zv.InputName = ze.InputName; zv.OutputName = ze.OutputName;
if opts.Method == "auto"
    if isempty(opts.Orders), opts.Orders = [4 6 8 10 12]; end
    cand = {}; score = [];
    for o = opts.Orders
        for meth = ["ssest" "n4sid"]
            s_ = fitone(ze, o, meth); f_ = fitpct(zv, s_);
            cand{end+1} = struct('sys', s_, 'order', o, 'method', meth, 'fit', f_(:)'); %#ok<AGROW>
            score(end+1) = min(f_);  %#ok<AGROW>   % maximise the worse of the two outputs
            fprintf('  %-5s order %2d: fit inlet %.1f %%, power %.1f %%\n', meth, o, f_(1), f_(2));
        end
    end
    [~, b] = max(score); sys = cand{b}.sys; opts.Order = cand{b}.order; opts.Method = cand{b}.method;
else
    sys = fitone(ze, opts.Order, opts.Method);
end
fit = fitpct(zv, sys);
M = struct('sys', sys, 'U0', U0, 'Y0', Y0, 'fit_pct', fit(:)', 'Ts', 60, 'order', opts.Order, ...
    'method', opts.Method, 'hours', opts.Hours, 'data', {exps}, 'days', opts.Days, 'climate', char(opts.Climate), ...
    'note', sprintf('%s order-%d discrete model identified on the verified DCX plant; fit = NRMSE %% on held-out 30 %%', opts.Method, opts.Order));
if opts.Climate == "pune" && isscalar(opts.Days)
    save(fullfile(here, sprintf('dcx_mpc_model_%s.mat', opts.Profile)), 'M');
end
save(fullfile(here, sprintf('dcx_mpc_model_%s_%s.mat', opts.Profile, opts.Climate)), 'M');
fprintf('Identified model (%s, order %d): validation fit max_inlet %.1f %%, facility power %.1f %%\n', opts.Method, opts.Order, fit(1), fit(2));
end

function sys = fitone(ze, order, method)
if method == "n4sid"
    sys = n4sid(ze, order, 'Ts', 60, 'DisturbanceModel', 'none', 'Form', 'free');
else
    sys = ssest(ze, order, 'Ts', 60, 'DisturbanceModel', 'none', 'Form', 'free');
end
end

function f = fitpct(zv, sys)
% NRMSE fit (%) per output; multi-experiment data -> mean over experiments
[~, fit] = compare(zv, sys);
if iscell(fit), fit = mean(cat(2, fit{:}), 2); end
f = fit(:)';
end
