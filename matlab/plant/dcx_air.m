function [X, y] = dcx_air(X, D, F, O, Rp, Hp, Cp, ctrl, P)
%DCX_AIR CRAH units (fans, CHW coils), underfloor plenum, contained cold aisle,
%   rack inlets with recirculation, hot aisle / room return (Subsystem 02).
%   States: Tin(1x8) Tpl Tca Tha fan(1x4) valve(1x4).
%   Rp/Hp/Cp = previous-step outputs of racks / hydraulics / CHW plant.
%   ctrl.fan_trim (PI output), ctrl.valve_cmd (1x4 PI outputs).
dt = P.dt; cp = P.cp_air; mmax = P.crah_m_max;
run = O.crah_run > 0;
nrun = max(1, sum(run));
m_rack = Rp.m_tot;
if any(run), ff = 1.15*m_rack/(nrun*mmax); else, ff = 0; end
speed_cmd = min(1, max(0.30, ff + ctrl.fan_trim));
vsum = sum(X.valve.*run); if vsum <= 0, vsum = 1; end
m = zeros(1,4); Tsup = zeros(1,4); Q = zeros(1,4); qj = zeros(1,4); eps_ = zeros(1,4);
fkw = zeros(1,4); vib = zeros(1,4); Tsup_out = zeros(1,4);
fan = X.fan; valve = X.valve;
Tha = X.Tha; Tchws = Cp.Tchws; q = Hp.q;
for c = 1:4
    block = F.crah_block(c)*0.5;
    if run(c)
        fan(c) = fan(c) + (speed_cmd - fan(c))*min(1, dt/P.tau.fan_up);
    else
        fan(c) = fan(c) + (0 - fan(c))*min(1, dt/P.tau.fan_down);
    end
    m(c) = fan(c)*mmax*(1 - block);
    if run(c), qj(c) = q*valve(c)/vsum; end
    NTU = P.crah_NTU0*(max(valve(c),1e-3)^0.7)*(max(qj(c),1e-3)/P.crah_q_nom)^0.35;
    if run(c) && q > 0.05, eps_(c) = min(0.95, 1 - exp(-NTU)); end
    Tsup(c) = Tha - eps_(c)*(Tha - Tchws);
    Q(c) = m(c)*cp*(Tha - Tsup(c));
    if run(c)
        valve(c) = valve(c) + (ctrl.valve_cmd(c) - valve(c))*min(1, dt/P.tau.valve);
        Tsup_out(c) = Tsup(c);
    else
        Tsup_out(c) = Tha;
    end
    s = fan(c);
    if s > 0.05
        vib(c) = 0.8*s + 6.0*F.fan_imb(c)*s*s + 4.5*F.fan_brg(c)^1.3;
    end
    fkw(c) = P.crah_fan_kw*s^3*(1 + 0.18*F.fan_brg(c))*(1 + 0.6*block);
end
m_crah = sum(m);
% plenum and cold aisle
Tpl = X.Tpl;
if m_crah > 1e-3
    Tmix = sum(m.*Tsup)/m_crah;
    Tpl = Tpl + (Tmix - Tpl)*min(1, dt/P.tau.Tpl);
else
    Tpl = Tpl + (Tha - Tpl)*min(1, dt/240);
end
if m_rack > 0, deficit = max(0, 1 - m_crah/m_rack); else, deficit = 0; end
Tca = X.Tca + ((1 - deficit)*Tpl + deficit*Tha - X.Tca)*min(1, dt/P.tau.Tca);
% rack inlets
Tin = X.Tin; recirc = zeros(1,8);
for r = 1:8
    wsum = 0; wrun = 0;
    for c = 1:4
        wsum = wsum + P.crah_w(r,c);
        if m(c) > 0, wrun = wrun + P.crah_w(r,c)*m(c)/(mmax*0.55); end
    end
    loc = min(1, wrun/wsum);
    tile_m = m_crah/8;
    if Rp.m(r) > 0, def_i = max(0, 1 - tile_m/Rp.m(r)); else, def_i = 0; end
    rc = min(0.9, 0.02 + 0.10*(1 - loc) + 0.45*def_i*(1 + 0.5*P.rack_edge(r)));
    rs = 0.32*F.rack_ovh(r);
    tgt = (1 - rc - rs)*Tca + rc*Tha + rs*Rp.Tout(r);
    Tin(r) = Tin(r) + (tgt - Tin(r))*min(1, dt/P.tau.Tin);
    recirc(r) = rc + rs;
end
% hot aisle / room return energy balance
bypass = max(0, m_crah - m_rack);
qin = sum(Rp.m.*cp.*(Rp.Tout - Tha)) + bypass*cp*(Tpl - Tha) + P.UA_env*(D.db + 4 - Tha);
if m_rack <= 0, qin = qin + m_crah*cp*(Tpl - Tha); end
Tha = Tha + qin/P.C_ha*dt;

X.Tin = Tin; X.Tpl = Tpl; X.Tca = Tca; X.Tha = Tha; X.fan = fan; X.valve = valve;
y = struct('Tin', Tin, 'Tpl', Tpl, 'Tca', Tca, 'Tha', Tha, 'Tsup', Tsup_out, 'm', m, 'Q', Q, ...
    'qj', qj, 'fan_kw', fkw, 'vib', vib, 'valve', valve, 'fan', fan, 'recirc', recirc, 'eps', eps_, ...
    'rh_ca', dcx_rh(Tca, P), 'rh_ha', dcx_rh(Tha, P), 'Q_tot', sum(Q), 'm_crah', m_crah, ...
    'max_in', max(Tin), 'airflow', m/P.rho_air);
end

function rh = dcx_rh(T, P)
ps = 0.6112*exp(17.62*T/(243.12 + T));
pw = P.abs_hum*101.325/(0.622 + P.abs_hum);
rh = min(100, pw/ps*100);
end
