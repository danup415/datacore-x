function [X, y] = dcx_electrical(X, F, O, Rp, Ap, Hp, Cp, P)
%DCX_ELECTRICAL System-level power flow (Subsystems 04/05): transformer,
%   generator, LV switchgear, 2N UPS with equivalent-circuit Li-ion strings,
%   A/B PDUs with phase currents, facility KPIs, energy and CO2 integrals.
%   States: soc(1x2) Tb(1x2) txw fuel E_fac E_it E_cool CO2.
dt = P.dt;
bus_ok = O.bus_ok > 0; grid_ok = O.grid_ok > 0;
P_it = Rp.P_it;
P_cool = Cp.P_ch + Hp.P_tot + Cp.P_tower + Cp.cwp_kw + sum(Ap.fan_kw);
if bus_ok, P_light = P.light_kw; else, P_light = 0; end
P_mech = P_cool + P_light;
pA = O.path_ok(1) > 0; pB = O.path_ok(2) > 0;
if pA && pB, sA = 0.5; elseif pA, sA = 1; else, sA = 0; end
if O.it_powered > 0, sB = 1 - sA; else, sB = 0; end
sh = [sA sB];
pdu_kw = P_it*sh; pdu_pct = pdu_kw/P.pdu_rated*100;
Iph = zeros(2,3); imb = zeros(1,2);
for d = 1:2
    ph = zeros(1,3);
    for r = 1:8
        ph(P.rack_phase(r)) = ph(P.rack_phase(r)) + Rp.P(r)*sh(d);
    end
    I = ph*1000/240; Iph(d,:) = I;
    mI = mean(I);
    if mI > 0.1, imb(d) = (max(I) - mI)/mI*100; end
end
P_pdu_loss = 0.015*sum(pdu_kw);
soc = X.soc; Tb = X.Tb;
ups_kw = zeros(1,2); ups_pct = zeros(1,2); ups_eta = zeros(1,2); ups_loss = zeros(1,2); Pin = zeros(1,2);
Vb = zeros(1,2); Ib = zeros(1,2); soh = zeros(1,2); rint = zeros(1,2); runtime = zeros(1,2);
in_v = zeros(1,2); out_v = zeros(1,2);
for u = 1:2
    if O.path_ok(u) > 0, Pout = pdu_kw(u)*1.015; else, Pout = 0; end
    x = Pout/P.ups_rated;
    if Pout > 0, eta = 0.965 - 0.07*exp(-x/0.12); loss = Pout*(1/eta - 1); else, eta = 0; loss = 0; end
    sohf = 1 - 0.40*F.bat_deg(u); rf = 1 + 1.6*F.bat_deg(u);
    cap = P.bat_ah*sohf; R = P.bat_R*rf;
    Voc = P.bat_cells*(3.0 + 0.35*soc(u));
    I = 0; pin = 0;
    if O.ups_mode(u) == 1
        Pdc = (Pout + loss)*1000;
        disc = Voc*Voc - 4*R*Pdc;
        if disc > 0, I = (Voc - sqrt(disc))/(2*R); else, I = Voc/(2*R); end
    elseif O.ups_mode(u) == 0
        pch = 0;
        if soc(u) < 0.999
            I = -min(0.15*cap, 0.15*cap*max(0.05, (1 - soc(u))/0.05));
            pch = -I*Voc/1000/0.95;
        end
        pin = Pout + loss + pch;
    end
    soc(u) = min(1, max(0, soc(u) - I*dt/(3600*cap)));
    heat = I*I*R/1000 + 0.8*F.bat_ovh(u);
    Tb(u) = Tb(u) + (heat - P.bat_h*(Tb(u) - 24))/P.bat_Cth*dt;
    if Pout > 0, Pexp = max(1, Pout + loss); else, Pexp = max(1, P_it*0.5); end
    ups_kw(u) = Pout; ups_pct(u) = x*100; ups_eta(u) = eta*100; ups_loss(u) = loss; Pin(u) = pin;
    Vb(u) = Voc - I*R; Ib(u) = I; soh(u) = sohf*100; rint(u) = R*1000;
    runtime(u) = soc(u)*cap*P.bat_cells*3.2/1000/Pexp*60;
    if bus_ok && O.ups_mode(u) ~= 1, in_v(u) = 415; end
    if O.path_ok(u) > 0, out_v(u) = 415; end
end
P_bus = P_mech + sum(Pin);
if O.bus == 1, kva = P_bus/0.95; else, kva = 0; end
lx = kva/P.tx_kva;
if grid_ok, tx_loss = 0.9 + 4.5*lx*lx; lv = 415 - 6*lx; else, tx_loss = 0; lv = 0; end
txw = X.txw + ((30 + 55*lx^1.6) - X.txw)*min(1, dt/P.tau.tx);
if O.bus == 2, genP = P_bus; else, genP = 0; end
fuel = max(0, X.fuel - genP*dt/3600*P.gen_L_per_kWh/P.gen_tank_L*100);
if O.bus == 1, Vbus = 415 - 6*lx; elseif O.bus == 2, Vbus = 412; else, Vbus = 0; end
if bus_ok, Ibus = P_bus*1000/(sqrt(3)*415*0.95); fbus = 50; else, Ibus = 0; fbus = 0; end
if O.gen_state == 2 || O.gen_state == 3, fgen = 50; else, fgen = 0; end
P_loss = sum(ups_loss) + P_pdu_loss + tx_loss;
P_fac = P_it + P_cool + P_loss + P_light;
if P_it > 1, pue = P_fac/P_it; else, pue = 0; end
X.soc = soc; X.Tb = Tb; X.txw = txw; X.fuel = fuel;
X.E_fac = X.E_fac + P_fac*dt/3600; X.E_it = X.E_it + P_it*dt/3600;
X.E_cool = X.E_cool + P_cool*dt/3600;
X.CO2 = X.CO2 + P_fac*dt/3600*P.grid_ef_kg_per_kwh*double(O.bus ~= 2);   % generator CO2 not modelled
y = struct('pdu_kw', pdu_kw, 'pdu_pct', pdu_pct, 'Iph', Iph, 'imb', imb, ...
    'ups_kw', ups_kw, 'ups_pct', ups_pct, 'ups_eta', ups_eta, 'ups_loss', ups_loss, 'ups_pin', Pin, ...
    'in_v', in_v, 'out_v', out_v, 'soc', soc*100, 'soh', soh, 'Vb', Vb, 'Ib', Ib, 'Tb', Tb, ...
    'runtime', runtime, 'rint', rint, 'tx_kva', kva, 'tx_pct', lx*100, 'tx_loss', tx_loss, ...
    'txw', txw, 'lv', lv, 'genP', genP, 'fgen', fgen, 'fuel', fuel, 'Vbus', Vbus, 'Ibus', Ibus, ...
    'fbus', fbus, 'P_mech', P_mech, 'P_it', P_it, 'P_cool', P_cool, 'P_loss', P_loss, ...
    'P_fac', P_fac, 'pue', pue, 'E_fac', X.E_fac, 'E_it', X.E_it, 'E_cool', X.E_cool, 'CO2', X.CO2);
end
