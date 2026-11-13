function [S, O] = dcx_plc(S, F, soc, plr, cmd, P, ats)
%DCX_PLC Supervisory PLC logic (L2): trips, generator/ATS sequence, UPS modes,
%   CRAH availability, CHW pump duty/standby, chiller lead/lag with
%   anti-recycle, operator commands with interlocks and acknowledgement.
%   Discrete, sample time P.dt. Code-generation compatible.
%   cmd: struct seq, code, asset, value
%     code 1 pump_start 2 pump_stop 3 pump_changeover(value=target pump 1..3)
%          4 crah_enable 5 crah_disable 6 chiller_lead 7 reset_trip 8 maintenance_complete
%          9 chiller_prestart (value 1 = force standby chiller on, 0 = release)
%     asset: pump 11..13, CRAH 21..24, chiller 31..32
%   ats (optional) = [valid bus gen_state] from the Stateflow ATS_Sequence
%       chart in DCX_Facility; when valid = 1 the chart's bus and generator
%       state are used, otherwise (MATLAB stepper) the equivalent logic below.
%   ack_code: 0 accepted, 1 tripped, 2 last pump, 3 crah tripped,
%             4 min-2 CRAH, 5 trip cause present, 6 invalid
dt = P.dt;

% ---------------- operator command (edge on sequence number) -------------
if cmd.seq ~= S.ack_seq && cmd.seq > 0
    code = 0; typ = floor(cmd.asset/10); i = max(1, mod(cmd.asset,10));
    switch cmd.code
        case 1
            if typ ~= 1 || i > 3, code = 6;
            elseif S.pump_trip(i) > 0, code = 1;
            else, S.pump_duty(i) = 1; S.pump_run(i) = 1; S.pump_opstop(i) = 0; end
        case 2
            if typ ~= 1 || i > 3, code = 6;
            else
                others = S.pump_run; others(i) = 0;
                if sum(others) < 1, code = 2;
                else, S.pump_duty(i) = 0; S.pump_run(i) = 0; S.pump_opstop(i) = 1; end
            end
        case 3
            tg = round(cmd.value);
            if typ ~= 1 || i > 3 || tg < 1 || tg > 3 || tg == i, code = 6;
            elseif S.pump_trip(tg) > 0, code = 1;
            else
                S.pump_duty(tg) = 1; S.pump_run(tg) = 1; S.pump_opstop(tg) = 0;
                S.pump_duty(i) = 0; S.pump_run(i) = 0; S.pump_opstop(i) = 1;
            end
        case 4
            if typ ~= 2 || i > 4, code = 6;
            elseif S.crah_trip(i) > 0, code = 3;
            else, S.crah_en(i) = 1; end
        case 5
            if typ ~= 2 || i > 4, code = 6;
            else
                run = S.crah_en & ~S.crah_trip; run(i) = 0;
                if sum(run) < 2, code = 4; else, S.crah_en(i) = 0; end
            end
        case 6
            if typ ~= 3 || i > 2, code = 6; else, S.ch_lead = i; end
        case 9
            if typ ~= 3 || i > 2, code = 6; else, S.ch_force(i) = double(cmd.value > 0); end
        case {7, 8}
            if typ == 1 && i <= 3
                if cmd.code == 7 && F.pump_trip(i) > 0, code = 5; else, S.pump_trip(i) = 0; end
            elseif typ == 2 && i <= 4
                if cmd.code == 7 && F.crah_trip(i) > 0, code = 5; else, S.crah_trip(i) = 0; end
            elseif typ == 3 && i <= 2
                if cmd.code == 7 && F.ch_trip(i) > 0, code = 5; else, S.ch_trip(i) = 0; end
            else
                code = 6;
            end
        otherwise
            code = 6;
    end
    S.ack_seq = cmd.seq; S.ack_code = code;
end

% ---------------- protective trips --------------------------------------
for p = 1:3
    if F.pump_trip(p) > 0 && S.pump_trip(p) == 0, S.pump_trip(p) = 1; S.pump_run(p) = 0; end
end
for c = 1:4
    if F.crah_trip(c) > 0, S.crah_trip(c) = 1; end
end
for c = 1:2
    if F.ch_trip(c) > 0, S.ch_trip(c) = 1; end
end
grid_ok = F.utility <= 0;

% ---------------- generator + ATS (0 STOPPED 1 STARTING 2 RUNNING 3 COOLDOWN)
if ~grid_ok
    S.retransfer_t = 0;
    if S.gen_state == 0 || S.gen_state == 3, S.gen_state = 1; S.gen_t = 0; end
    if S.gen_state == 1
        S.gen_t = S.gen_t + dt;
        if S.gen_t >= P.gen_start_s, S.gen_state = 2; end
    end
    if S.bus == 1, S.bus = 0; S.ats_t = 0; S.mech_t = 0; end
    if S.bus == 0 && S.gen_state == 2
        S.ats_t = S.ats_t + dt;
        if S.ats_t >= P.ats_s, S.bus = 2; end
    end
else
    if S.bus == 0, S.bus = 1; end
    if S.bus == 2
        S.retransfer_t = S.retransfer_t + dt;
        if S.retransfer_t >= P.retransfer_s, S.bus = 1; S.gen_state = 3; S.gen_t = 0; end
    end
    if S.gen_state == 3
        S.gen_t = S.gen_t + dt;
        if S.gen_t >= P.cooldown_s, S.gen_state = 0; end
    end
    if S.gen_state == 1, S.gen_state = 0; end
end
if nargin >= 7 && ats(1) > 0
    S.bus = ats(2); S.gen_state = ats(3);          % Stateflow chart is authoritative
end
if S.gen_state == 2 || S.gen_state == 3, S.gen_run_s = S.gen_run_s + dt; end
bus_ok = S.bus ~= 0;
if bus_ok, S.mech_t = S.mech_t + dt; else, S.mech_t = 0; end
mech_ready = bus_ok && S.mech_t >= P.mech_restart_s;

% ---------------- UPS (0 DOUBLE_CONVERSION 1 BATTERY 2 OUTPUT_OFF) -----------
ups_mode = zeros(1,2);
for u = 1:2
    in_ok = bus_ok && F.ups_batt(u) <= 0;
    if in_ok
        if S.bus == 2, S.ups_walkin(u) = min(1, S.ups_walkin(u) + dt/5); else, S.ups_walkin(u) = 1; end
    else
        S.ups_walkin(u) = 0;
    end
    if S.ups_outok(u) == 0 && in_ok, S.ups_outok(u) = 1; end
    if in_ok && S.ups_walkin(u) >= 1, m = 0; else, m = 1; end
    if soc(u) <= 0.01 && m == 1, S.ups_outok(u) = 0; end
    if S.ups_outok(u) == 0, m = 2; end
    ups_mode(u) = m;
end

% ---------------- CRAH availability -------------------------------------
crah_run = double(S.crah_en & ~S.crah_trip & mech_ready);

% ---------------- CHW pumps: duty / standby ---------------------------------
for p = 1:3
    if S.pump_duty(p) && ~S.pump_trip(p), S.pump_run(p) = 1; end
end
if sum(S.pump_duty & ~S.pump_trip) < 2
    for p = 1:3
        if ~S.pump_duty(p) && ~S.pump_trip(p) && ~S.pump_opstop(p)
            S.sb_t(p) = S.sb_t(p) + dt;
            if S.sb_t(p) >= 5
                S.pump_duty(p) = 1; S.pump_run(p) = 1; S.sb_t(p) = 0;
            end
            break
        end
    end
end
pump_run = double(S.pump_run & ~S.pump_trip & mech_ready);

% ---------------- chillers: lead/lag + start-up delay (anti-recycle) ----------
L = S.ch_lead; G = 3 - L;
lead_ok = ~S.ch_trip(L) && mech_ready;
need_lag = ~lead_ok || S.ch_hiplr(L) >= P.ch_hiplr_s;
ch_run = zeros(1,2);
ch_run(L) = double(lead_ok);
ch_run(G) = double((need_lag || S.ch_force(G) > 0) && ~S.ch_trip(G) && mech_ready);
for c = 1:2      % start-up timer runs only while the chiller is commanded on
    if ch_run(c) > 0, S.ch_restart(c) = S.ch_restart(c) + dt; else, S.ch_restart(c) = 0; end
end
ch_avail = double(ch_run & (S.ch_restart >= P.ch_restart_s));
for c = 1:2
    if ch_avail(c) && plr(c) > 0.95, S.ch_hiplr(c) = S.ch_hiplr(c) + dt; else, S.ch_hiplr(c) = 0; end
end

O.grid_ok = double(grid_ok); O.bus = S.bus; O.bus_ok = double(bus_ok); O.mech_ready = double(mech_ready);
O.ups_mode = ups_mode; O.path_ok = S.ups_outok; O.it_powered = double(any(S.ups_outok));
O.ups_walkin = S.ups_walkin;
O.pump_run = pump_run; O.pump_trip = S.pump_trip; O.pump_duty = S.pump_duty;
O.crah_run = crah_run; O.crah_trip = S.crah_trip; O.crah_en = S.crah_en;
O.ch_run = ch_run; O.ch_avail = ch_avail; O.ch_trip = S.ch_trip; O.ch_lead = S.ch_lead;
O.ch_starting = double(ch_run & ~ch_avail);
O.tower_run = double([mech_ready mech_ready]);
O.gen_state = S.gen_state; O.gen_run_s = S.gen_run_s;
O.ack_seq = S.ack_seq; O.ack_code = S.ack_code;
end
