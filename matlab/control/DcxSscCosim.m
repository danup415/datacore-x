classdef DcxSscCosim < handle
    %DCXSSCCOSIM Simscape Fluids CHW hydraulics in the closed loop.
    %   Co-simulation of the Simscape Fluids (Isothermal Liquid) network
    %   DCX_CHW_Hydraulics_SSC with the DATACORE-X plant stepper. Every
    %   macro step (default 10 s) the Simscape network is advanced from its
    %   saved operating point with the plant's current inputs:
    %     VFD speed n (driven by the plant's DP PI loop), pump run states
    %     (PLC duty/standby, supervisor changeover, trips) and the four CRAH
    %     valve openings (supply-air PI loops).
    %   Its outputs - header dp H, loop flow q and the per-pump flows - then
    %   REPLACE the reduced-order hydraulics for the following macro step:
    %   the DP controller regulates on the Simscape dp, the coils transfer
    %   heat with the Simscape flow, and pump power / efficiency / current
    %   are recomputed from the Simscape per-pump flows (same equations as
    %   plant/dcx_hydraulics.m). Pump vibration keeps its own model.
    %   The network has two pump trains; the (at most two) running pumps of
    %   the three are mapped onto them in index order.
    %   Use:  C = DcxSscCosim(P);  L = dcx_sim_matlab(P, FT, T, ..., 'HydHook', @C.hook)
    properties
        mdl = 'DCX_CHW_Hydraulics_SSC'
        Tm = 10                 % s, macro (exchange) step
        P
        kg2l = 1000/998.21
        xop = []                % Simscape operating point carried between macro steps
        toff = 0                % Simscape time = plant time + toff
        y = []                  % last Simscape outputs [H q qp(1x3)]
        nCalls = 0
        wall = 0
        log = zeros(0, 9)       % [t n run(1x3) H q q1 q2]
    end
    methods
        function obj = DcxSscCosim(P, opts)
            arguments
                P struct
                opts.MacroStep (1,1) double = 10
            end
            obj.P = P; obj.Tm = opts.MacroStep;
            here = fileparts(mfilename('fullpath'));
            addpath(fullfile(fileparts(here), 'simscape'));
            if bdIsLoaded(obj.mdl), set_param(obj.mdl, 'FastRestart', 'off'); end
            load_system(fullfile(fileparts(here), 'simscape', [obj.mdl '.slx']));
            assignin('base', 'P', P);
            assignin('base', 'ssc_n', 0.75); assignin('base', 'ssc_iso', [1 1]); assignin('base', 'ssc_v', [1 1 1 1]);
            set_param(obj.mdl, 'SaveFinalState', 'on', 'SaveOperatingPoint', 'on', 'FinalStateName', 'xFinal', ...
                'LoadInitialState', 'off', 'StopTime', '30', 'SimulationMode', 'normal');
        end
        function [X, H] = hook(obj, k, t, X, H, F, O, Ap)
            runp = O.pump_run > 0;
            if ~any(runp), obj.y = []; return; end          % loop stopped: keep the ROM decay
            if any(F.pump_cav > 0)
                error('DcxSscCosim:cav', 'cavitation (head derating) is not represented in the Simscape network');
            end
            if isempty(obj.y) || mod(t, obj.Tm) == 0 || ~isequal(runp, obj.y.runp)
                obj.advance(t, X.n, runp, Ap.valve.*(O.crah_run > 0));
            end
            [X, H] = obj.override(X, H, F);
        end
        function advance(obj, t, n, runp, v)
            idx = find(runp);
            if numel(idx) > 2, error('DcxSscCosim:pumps', 'network has two pump trains, %d pumps running', numel(idx)); end
            iso = zeros(1, 2); iso(1:numel(idx)) = 1;
            assignin('base', 'ssc_n', max(0.05, n)); assignin('base', 'ssc_iso', iso);
            assignin('base', 'ssc_v', max(1e-5, v));
            t0 = tic;
            if isempty(obj.xop)
                % first call: settle 30 s from rest with the current inputs, then turn on Fast Restart
                set_param(obj.mdl, 'FastRestart', 'off', 'LoadInitialState', 'off', 'StopTime', '30');
                so = sim(obj.mdl);
                obj.toff = 30 - t;
                set_param(obj.mdl, 'LoadInitialState', 'on', 'InitialState', 'ssc_xop');
                set_param(obj.mdl, 'FastRestart', 'on');
            else
                assignin('base', 'ssc_xop', obj.xop);
                set_param(obj.mdl, 'StopTime', num2str(t + obj.toff, 12));
                so = sim(obj.mdl);
            end
            obj.wall = obj.wall + toc(t0); obj.nCalls = obj.nCalls + 1;
            obj.xop = so.xFinal;
            yy = so.yout(end, :);
            qp = zeros(1, 3); q12 = yy(3:4)*obj.kg2l; qp(idx) = q12(1:numel(idx));
            obj.y = struct('H', yy(1), 'q', yy(2)*obj.kg2l, 'qp', qp, 'runp', runp);
            obj.log(end+1, :) = [t n double(runp) yy(1) yy(2)*obj.kg2l q12];
        end
        function [X, H] = override(obj, X, H, F)
            P = obj.P; n = X.n; Hh = obj.y.H; qp = obj.y.qp;
            for p = 1:3
                brg = F.pump_brg(p);
                eta_bep = P.pump_eta_bep*(1 - F.pump_effdrop(p))*(1 - 0.06*brg);
                if qp(p) > 0 && n > 0.05
                    x = qp(p)/(n*P.pump_q_bep);
                    H.eta(p) = max(0.15, eta_bep*(1 - 0.8*(x - 1)^2));
                    H.P(p) = qp(p)*Hh/1000/H.eta(p) + 0.05*brg;
                    H.cur(p) = H.P(p)*1000/(sqrt(3)*415*0.85*0.90);
                    H.head(p) = Hh;
                end
            end
            H.H = Hh; H.q = obj.y.q; H.qp = qp; H.P_tot = sum(H.P);
            X.H = Hh; X.q = obj.y.q;
        end
        function delete(obj)
            try, if bdIsLoaded(obj.mdl), set_param(obj.mdl, 'FastRestart', 'off'); end, catch, end
        end
    end
end
