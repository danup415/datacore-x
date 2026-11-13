function L = dcx_sim_matlab(P, FT, T, opts)
%DCX_SIM_MATLAB Reference time-stepping of the DATACORE-X plant in plain
%   MATLAB (same domain functions as DCX_Facility, PI controllers identical
%   to the Python surrogate). Used for unit tests and cross-verification.
%   L = dcx_sim_matlab(P, FT, T) simulates T seconds; returns 1 Hz logs.
arguments
    P struct
    FT (32,9) double = zeros(32,9)
    T (1,1) double = 3600
    opts.Log (1,1) double = 1          % log every N steps
    opts.Sensors (1,1) logical = false % also log the 217 measured points (+ fault severities)
    opts.Cmd = []                      % optional [t code asset value] rows (operator commands)
    opts.Supervisor = []               % handle: [sp, cmds, info] = f(t, obs) called every SupTs s
    opts.SupTs (1,1) double = 60
    opts.HydHook = []                  % optional co-simulation hook (e.g. Simscape Fluids hydraulics in the loop):
                                       % [Xhyd, H] = f(k, t, Xhyd, H, F, O, Ap) called after dcx_hydraulics each step
end
SP = P.sp; supinfo = {};
[Y0, X, ~] = dcx_bootstrap(P);
Rp = Y0.R; Ap = Y0.A; Hp = Y0.H; Cp = Y0.C; Ep = Y0.E;
pv = struct('i', P.pi_valve.u0); pv = repmat(pv, 1, 4);
pf = struct('i', P.pi_fan.u0); pp = struct('i', P.pi_pump.u0); pt = struct('i', P.pi_tower.u0);
ctrl = struct('fan_trim', 0, 'valve_cmd', P.pi_valve.u0*ones(1,4), 'pump_cmd', P.pi_pump.u0, 'tower_cmd', P.pi_tower.u0);
cmd = struct('seq',0,'code',0,'asset',0,'value',0);
n = round(T/P.dt); nl = floor(n/opts.Log);
L = struct('t', zeros(nl,1), 'it', zeros(nl,1), 'fac', zeros(nl,1), 'pue', zeros(nl,1), ...
    'max_in', zeros(nl,1), 'Tchws', zeros(nl,1), 'Tchwr', zeros(nl,1), 'Tha', zeros(nl,1), 'Tca', zeros(nl,1), ...
    'q', zeros(nl,1), 'H', zeros(nl,1), 'n', zeros(nl,1), 'cool', zeros(nl,1), 'Qhx', zeros(nl,1), ...
    'Qch', zeros(nl,2), 'cop', zeros(nl,2), 'fan', zeros(nl,4), 'valve', zeros(nl,4), 'Tin', zeros(nl,8), ...
    'soc', zeros(nl,2), 'bus', zeros(nl,1), 'Tctl', zeros(nl,1), 'pump_kw', zeros(nl,3), 'vib_p', zeros(nl,3), ...
    'E_fac', zeros(nl,1), 'CO2', zeros(nl,1), 'sp', zeros(nl,3), 'wb', zeros(nl,1), 'pump_run', zeros(nl,3), 'pump_trip', zeros(nl,3), 'ch_trip', zeros(nl,2), 'tower_kw', zeros(nl,2), 'Qrej', zeros(nl,1), 'crah_kw', zeros(nl,4), 'P_ch', zeros(nl,1), 'tspd', zeros(nl,2), 'Qi', zeros(nl,2), 'app', zeros(nl,2), 'Qcoil', zeros(nl,1), 'P_loss', zeros(nl,1), 'Tsup', zeros(nl,4), 'valve_cmd', zeros(nl,4), 'db', zeros(nl,1), 'Tpl', zeros(nl,1), 'rackP', zeros(nl,8));
if opts.Sensors
    L.meas = zeros(nl, 217); L.truth = zeros(nl, 217); L.fs = zeros(nl, 26); L.st = zeros(nl, 34);
    rng(P.seed + 4);
end
cseq = 0;
j = 0;
for k = 1:n
    t = k*P.dt;
    D = dcx_disturbance(t, P.ou_noise(min(k+1, size(P.ou_noise,1)),:), P);
    F = dcx_faults(t, FT);
    if ~isempty(opts.Cmd)
        r = find(opts.Cmd(:,1) == t, 1);
        if ~isempty(r), cseq = cseq + 1; cmd = struct('seq',cseq,'code',opts.Cmd(r,2),'asset',opts.Cmd(r,3),'value',opts.Cmd(r,4)); end
    end
    if ~isempty(opts.Supervisor) && mod(k, opts.SupTs) == 0
        [mo, ~, sto, fo] = dcx_sensors(Rp, Ap, Hp, Cp, Ep, O, F, D, randn(1,217));
        obs = struct('t', t, 'meas', mo, 'fac', fo, 'st', sto, 'sp', SP);
        [SP, cmds, inf_] = opts.Supervisor(t, obs);
        supinfo{end+1} = inf_; %#ok<AGROW>
        for ci = 1:size(cmds, 1)
            cseq = cseq + 1; cmd = struct('seq', cseq, 'code', cmds(ci,1), 'asset', cmds(ci,2), 'value', cmds(ci,3));
        end
    end
    [X.plc, O] = dcx_plc(X.plc, F, Ep.soc/100, Cp.plr, cmd, P);
    % controllers on previous-step measurements
    [pf, ctrl.fan_trim] = dcx_pi(pf, Ap.max_in - SP.max_inlet_c, P.pi_fan, P.dt);
    for c = 1:4
        if O.crah_run(c) > 0
            [pv(c), ctrl.valve_cmd(c)] = dcx_pi(pv(c), Ap.Tsup(c) - SP.supply_air_c, P.pi_valve, P.dt);
        end
    end
    if any(O.pump_run), [pp, ctrl.pump_cmd] = dcx_pi(pp, SP.dp_kpa - Hp.H, P.pi_pump, P.dt); end
    if any(O.tower_run), [pt, ctrl.tower_cmd] = dcx_pi(pt, Cp.Tctl - SP.tower_leaving_c, P.pi_tower, P.dt); else, ctrl.tower_cmd = 0; end
    [X.rack, R] = dcx_racks(X.rack, D, F, O, Ap, P);
    [X.air,  A] = dcx_air(X.air, D, F, O, Rp, Hp, Cp, ctrl, P);
    [X.hyd,  H] = dcx_hydraulics(X.hyd, F, O, Ap, ctrl, P);
    if ~isempty(opts.HydHook), [X.hyd, H] = opts.HydHook(k, t, X.hyd, H, F, O, Ap); end
    [X.chw,  C] = dcx_chwplant(X.chw, D, F, O, Ap, Hp, ctrl, SP, P);
    [X.elec, E] = dcx_electrical(X.elec, F, O, Rp, Ap, Hp, Cp, P);
    Rp = R; Ap = A; Hp = H; Cp = C; Ep = E;
    if mod(k, opts.Log) == 0
        j = j + 1;
        L.t(j) = t; L.it(j) = E.P_it; L.fac(j) = E.P_fac; L.pue(j) = E.pue; L.max_in(j) = A.max_in;
        L.Tchws(j) = C.Tchws; L.Tchwr(j) = C.Tchwr; L.Tha(j) = A.Tha; L.Tca(j) = A.Tca; L.q(j) = H.q;
        L.H(j) = H.H; L.n(j) = X.hyd.n; L.cool(j) = E.P_cool; L.Qhx(j) = C.Qhx; L.Qch(j,:) = C.Qc;
        L.cop(j,:) = C.cop; L.fan(j,:) = A.fan; L.valve(j,:) = A.valve; L.Tin(j,:) = A.Tin;
        L.soc(j,:) = E.soc; L.bus(j) = O.bus; L.Tctl(j) = C.Tctl; L.pump_kw(j,:) = H.P; L.vib_p(j,:) = H.vib;
        L.E_fac(j) = E.E_fac; L.CO2(j) = E.CO2; L.sp(j,:) = [SP.chws_c SP.supply_air_c SP.max_inlet_c]; L.wb(j) = D.wb;
        L.pump_run(j,:) = O.pump_run; L.pump_trip(j,:) = O.pump_trip; L.ch_trip(j,:) = O.ch_trip;
        L.tower_kw(j,:) = C.tower_kw; L.Qrej(j) = C.Qrej; L.crah_kw(j,:) = A.fan_kw; L.P_ch(j) = C.P_ch; L.tspd(j,:) = C.tspd; L.Qi(j,:) = C.Qi; L.app(j,:) = C.app; L.Qcoil(j) = A.Q_tot; L.P_loss(j) = E.P_loss; L.Tsup(j,:) = A.Tsup; L.valve_cmd(j,:) = ctrl.valve_cmd; L.db(j) = D.db; L.Tpl(j) = A.Tpl; L.rackP(j,:) = R.P;
        if opts.Sensors
            [L.meas(j,:), ~, L.st(j,:), ~, L.truth(j,:)] = dcx_sensors(R, A, H, C, E, O, F, D, randn(1,217));
            L.fs(j,:) = [F.pump_brg F.pump_cav F.pump_effdrop F.fan_imb F.fan_brg F.crah_block F.ch_deg F.hx_foul F.tower_deg];
        end
    end
end
L.supervisor = supinfo;
end
