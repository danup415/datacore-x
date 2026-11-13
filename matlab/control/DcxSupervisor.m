classdef DcxSupervisor < handle
    %DCXSUPERVISOR Supervisory controller for DATACORE-X (item 7).
    %   Mode 'fixed'   : baseline thermostatic control (constant setpoints;
    %                    the PI loops of the plant do the regulation).
    %   Mode 'empc'    : economic MPC (MPC Toolbox) on [CHW sp, supply-air sp,
    %                    max-inlet target] minimising facility power subject
    %                    to rack inlet <= T_max, measured IT load / wet-bulb as MDs.
    %   Mode 'haempc'  : PI-HA-EMPC = EMPC + live asset health:
    %                    (1) MV slew-rate bounds scaled by the health of the
    %                        equipment that each move stresses,
    %                    (2) pre-cooling (tightened inlet limit + lowered
    %                        setpoint bounds) when a critical cooling asset's
    %                        RUL falls inside the risk window,
    %                    (3) degradation-aware actions: standby-chiller
    %                        pre-start + lead transfer, CHW pump changeover
    %                        before predicted failure.
    %   Health (HI 0-100, RUL) is computed online from MEASURED values with
    %   physics residuals (no access to injected faults).
    %   Ablations (research E3): 'ha_noHI' (no HI-scaled slew bounds, no HI
    %   thresholds; RUL triggers only), 'ha_noRUL' (HI thresholds only),
    %   'ha_noPrecool' (no pre-cooling). Component ablations (E3b):
    %   'ha_noActions' (health inside the MPC only: HI-scaled slew bounds and
    %   pre-cooling, no discrete changeover / lead transfer), 'ha_actionsOnly'
    %   (health-blind MPC + the discrete actions), 'ha_none' (every health
    %   input off; must reproduce 'empc' exactly - sanity check). RulScale (E4) multiplies every RUL
    %   estimate: >1 optimistic (acts late), <1 pessimistic (acts early).
    %   info.solve_ms records the wall time of each mpcmove call (E6).
    properties
        mode = 'empc'
        P
        M
        mpcobj
        xmpc
        u_last
        Tmax = 26.8            % optimiser limit = 27.0 ASHRAE recommended max - 0.2 K back-off for model error
        Tsrv = 28.0            % hard service limit (reported)
        rate = 0.5             % nominal MV slew limit, K per minute
        lo = [16 19.5 23.0]
        hi = [22 25.0 26.5]
        rul_window_min = 25    % pre-cool / act when RUL < this
        hist = struct('t', [], 'pump_rv', [], 'ch_rc', [])
        acted = struct('pump', false, 'chiller_prestart', -1, 'chiller_lead', false)
        T                      % tag list
        useHI = true
        useRUL = true
        usePrecool = true
        useActions = true      % discrete health-triggered actions (changeover, lead transfer)
        useMpcHealth = true    % health inside the MPC (slew scaling, pre-cooling)
        RulScale = 1.0
        preG = 2               % chiller pre-started by the latched sequence
    end
    methods
        function obj = DcxSupervisor(mode, P, opts)
            arguments
                mode
                P
                opts.RulScale (1,1) double = 1.0
            end
            obj.mode = mode; obj.P = P; obj.T = dcx_tag_list(); obj.RulScale = opts.RulScale;
            obj.useHI = ~strcmp(mode, 'ha_noHI'); obj.useRUL = ~strcmp(mode, 'ha_noRUL');
            obj.usePrecool = ~strcmp(mode, 'ha_noPrecool');
            obj.useActions = ~ismember(mode, {'ha_noActions'});
            obj.useMpcHealth = ~ismember(mode, {'ha_actionsOnly'});
            if strcmp(mode, 'ha_none'), obj.useHI = false; obj.useRUL = false; obj.usePrecool = false; obj.useActions = false; end
            obj.u_last = [P.sp.chws_c P.sp.supply_air_c P.sp.max_inlet_c];
            if ~strcmp(mode, 'fixed')
                d = fileparts(mfilename('fullpath'));
                f = fullfile(d, sprintf('dcx_mpc_model_%s_%s.mat', P.profile, P.climate));
                if ~isfile(f), f = fullfile(d, sprintf('dcx_mpc_model_%s.mat', P.profile)); end
                S = load(f); obj.M = S.M;
                obj.mpcobj = dcx_design_mpc(obj.M, obj.lo, obj.hi, obj.Tmax, obj.rate);
                obj.xmpc = mpcstate(obj.mpcobj);
            end
        end
        function v = m(obj, obs, a, k)
            v = obs.meas(find(strcmp(obj.T.asset, a) & strcmp(obj.T.key, k), 1));
        end
        function [sp, cmds, info] = step(obj, t, obs)
            sp = obs.sp; cmds = zeros(0, 3);
            H = obj.health(t, obs);
            info = struct('t', t, 'u', obj.u_last, 'HI', H, 'precool', false, 'g', 1, 'solve_ms', NaN);
            if strcmp(obj.mode, 'fixed'), return; end
            % ---------------- MPC move -----------------------------------
            y = [obs.fac(6), obs.fac(2)] - obj.M.Y0;
            md = [obs.fac(1), obs.fac(9)] - obj.M.U0(4:5);
            opt = mpcmoveopt;
            lo_ = obj.lo; hi_ = obj.hi; ymax = obj.Tmax; g = 1;
            if startsWith(obj.mode, 'ha')
                % (1) health-scaled slew-rate bounds: CHW sp moves load the chillers/pumps
                if obj.useHI && obj.useMpcHealth, g = max(0.25, min([H.chiller_hi, H.pump_hi_min, 100])/100); end
                % (2) pre-cooling when a critical asset is predicted to fail soon
                risk = (obj.useRUL && (H.pump_rul_min < obj.rul_window_min || H.chiller_rul_min < obj.rul_window_min)) ...
                    || (obj.useHI && H.chiller_hi < 45);
                if obj.usePrecool && obj.useMpcHealth && risk && ~obj.acted.chiller_lead
                    ymax = 24.5; hi_ = [17.5 21.0 24.5]; info.precool = true;
                end
                info.g = g;
                % (3) degradation-aware discrete actions
                if obj.useActions, cmds = obj.actions(t, obs, H); end
            end
            r = obj.rate*g;
            opt.MVMin = max(lo_, obj.u_last - r) - obj.M.U0(1:3);
            opt.MVMax = min(hi_, obj.u_last + r) - obj.M.U0(1:3);
            opt.MVMax = max(opt.MVMax, opt.MVMin);
            opt.OutputMax = [ymax, Inf] - obj.M.Y0;
            opt.OutputMin = [-Inf, -Inf];
            t0 = tic;
            u = mpcmove(obj.mpcobj, obj.xmpc, y(:), [0; -1e3], md(:), opt);   % power reference far below -> minimise power
            info.solve_ms = 1000*toc(t0);
            u = u(:)' + obj.M.U0(1:3);
            obj.u_last = u;
            sp.chws_c = u(1); sp.supply_air_c = u(2); sp.max_inlet_c = u(3);
            info.u = u;
        end
        function H = health(obj, t, obs)
            % pumps: vibration residual vs speed-dependent healthy baseline
            rv = zeros(1,3) + NaN;
            for i = 1:3
                id = sprintf('P-%02d', i); n = obj.m(obs, id, 'speed_pct')/100;
                if n > 0.05, rv(i) = obj.m(obs, id, 'vib_mms') - (0.9 + 1.3*n^2); end
            end
            % lead chiller: COP residual vs performance map
            rc = NaN;
            for c = 1:2
                id = sprintf('CH-%02d', c);
                if obj.m(obs, id, 'load_kw') > 10
                    plr = max(0.15, obj.m(obs, id, 'plr_pct')/100); cwe = obj.m(obs, id, 'cwe_c');
                    Tev = obs.sp.chws_c - 2 + 273.15; Tcd = cwe + 5.5 + 273.15;
                    ce = min(12, obj.P.ch_carnot*Tev/max(3, Tcd - Tev)*(1 - obj.P.ch_plr_a*(1 - plr)^2));
                    if c == obj.leadChiller(obs), rc = (ce - obj.m(obs, id, 'cop'))/ce; end
                end
            end
            obj.hist.t(end+1) = t; obj.hist.pump_rv(end+1, :) = rv; obj.hist.ch_rc(end+1) = rc;
            H.pump_hi = 100*(1 - min(1, max(0, rv/5.45)));
            H.pump_hi(isnan(H.pump_hi)) = 100;
            H.pump_hi_min = min(H.pump_hi);
            H.pump_rul_min = inf; H.pump_rul = inf(1,3);
            for i = 1:3
                if isnan(rv(i)), H.pump_rul(i) = inf;      % not running -> carries no thermal risk now
                else, H.pump_rul(i) = obj.trendRUL(obj.hist.t, obj.hist.pump_rv(:, i)', 5.45); end
            end
            H.pump_rul = H.pump_rul*obj.RulScale;
            H.pump_rul_min = min(H.pump_rul);
            H.chiller_hi = 100*(1 - min(1, max(0, 2.2*rc))); if isnan(rc), H.chiller_hi = 100; end
            H.chiller_rul_min = obj.RulScale*obj.trendRUL(obj.hist.t, 2.2*obj.hist.ch_rc, 0.7);   % HI 30 <=> 2.2*r = 0.7
        end
        function L = leadChiller(obj, obs)
            L = 1; if obj.m(obs, 'CH-02', 'load_kw') > obj.m(obs, 'CH-01', 'load_kw'), L = 2; end
        end
        function cmds = actions(obj, t, obs, H)
            cmds = zeros(0, 3);
            % CHW pump changeover before predicted bearing failure
            [~, worst] = min(H.pump_hi);
            if ~obj.acted.pump && ((obj.useRUL && H.pump_rul(worst) < 15) || (obj.useHI && H.pump_hi(worst) < 25))
                sb = setdiff(1:3, worst); runs = arrayfun(@(i) obj.m(obs, sprintf('P-%02d', i), 'speed_pct') > 5, sb);
                tgt = sb(find(~runs, 1)); if isempty(tgt), tgt = sb(1); end
                cmds(end+1, :) = [3, 10 + worst, tgt]; obj.acted.pump = true;
            end
            % chiller: pre-start standby, then transfer lead once it is available
            L = obj.leadChiller(obs); G = 3 - L;
            % latched sequence: once the standby is pre-started, complete the lead transfer after
            % the start-up delay even if a noisy RUL estimate briefly leaves the risk window
            trig = (obj.useHI && H.chiller_hi < 45) || (obj.useRUL && H.chiller_rul_min < obj.rul_window_min);
            if ~obj.acted.chiller_lead
                if obj.acted.chiller_prestart < 0
                    if trig, cmds(end+1, :) = [9, 30 + G, 1]; obj.acted.chiller_prestart = t; end
                elseif t - obj.acted.chiller_prestart >= 240
                    cmds(end+1, :) = [6, 30 + obj.preG, 0]; obj.acted.chiller_lead = true;
                end
            end
            if obj.acted.chiller_prestart == t, obj.preG = G; end
        end
    end
    methods (Static)
        function r = trendRUL(t, v, thr)
            % minutes until v reaches thr by linear trend over the last 15 samples
            r = inf; ok = ~isnan(v); t = t(ok); v = v(ok);
            if numel(v) < 8, return; end
            t = t(max(1, end-14):end)/60; v = v(max(1, end-14):end);
            p = polyfit(t - t(end), v, 1);
            if p(1) > 1e-4 && v(end) < thr, r = (thr - p(2))/p(1); elseif v(end) >= thr, r = 0; end
        end
    end
end
