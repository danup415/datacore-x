function [X, y] = dcx_chwplant(X, D, F, O, Ap, Hp, ctrl, sp, P)
%DCX_CHWPLANT Chilled-water thermal loop: CHW return, waterside-economiser
%   plate HX (effectiveness-NTU), chillers (Carnot-fraction performance map,
%   part-load curve, capacity derate), condenser water and cooling towers
%   (approach model). States: Tchws Tchwr Tl(1x2) tspd(1x2) Tctl.
%   ctrl.tower_cmd = tower fan PI output.
dt = P.dt; cpw = P.cp_w;
q = Hp.q; Qc_tot = Ap.Q_tot;
C_chw = cpw*max(q, 0.05);
Tchwr = X.Tchwr;
if q > 0.05, tgt = X.Tchws + Qc_tot/C_chw; else, tgt = Tchwr; end
Tchwr = Tchwr + (tgt - Tchwr)*min(1, dt/P.tau.Tchwr);
cw_on = O.mech_ready > 0;
if cw_on, qcw = P.q_cw; else, qcw = 0; end
C_cw = cpw*max(qcw, 0.05);
Tctl = X.Tctl;
Qhx = 0; eps_hx = 0;
if cw_on && q > 0.05 && Tctl < Tchwr - 1
    eps_hx = P.hx_eps*(1 - 0.85*F.hx_foul);
    Qhx = eps_hx*min(C_chw, C_cw)*(Tchwr - Tctl);
end
Taft = Tchwr - Qhx/C_chw;
if cw_on, Tcwe = Tctl + Qhx/C_cw; else, Tcwe = Tctl; end
% chillers
av = O.ch_avail > 0;
nav = sum(av);
if q > 0.05, Qreq = max(0, C_chw*(Taft - sp.chws_c)); else, Qreq = 0; end
if nav > 0, share = Qreq/nav; else, share = 0; end
Qc = zeros(1,2); Pc = zeros(1,2); cop = zeros(1,2); plr = zeros(1,2); cap = zeros(1,2);
cwl = zeros(1,2); chws_c = zeros(1,2);
for c = 1:2
    cap(c) = P.ch_cap_nom*(1 - 0.012*(Tcwe - 24))*(1 - 0.25*F.ch_deg(c));
    if av(c)
        Qc(c) = min(share, cap(c));
        plr(c) = Qc(c)/P.ch_cap_nom;
        Tev = sp.chws_c - 2 + 273.15; Tcd = Tcwe + 5.5 + 273.15;
        plrf = 1 - P.ch_plr_a*(1 - max(plr(c), 0.15))^2;
        cop(c) = min(12, P.ch_carnot*Tev/max(3, Tcd - Tev)*plrf*(1 - 0.30*F.ch_deg(c)));
        if Qc(c) > 0, Pc(c) = Qc(c)/cop(c); else, Pc(c) = 3.0; end
    end
    if cw_on, cwl(c) = Tcwe + (Qc(c) + Pc(c))/C_cw; else, cwl(c) = Tcwe; end
end
Tleave = Taft;
Tchws = X.Tchws;
if q > 0.05
    Tleave = Taft - sum(Qc)/C_chw;
    Tchws = Tchws + (Tleave - Tchws)*min(1, dt/P.tau.Tchws);
else
    Tchws = Tchws + (Ap.Tha - 6 - Tchws)*min(1, dt/1800);
end
for c = 1:2
    if av(c), chws_c(c) = Tleave; else, chws_c(c) = Taft; end
end
% cooling towers
Qrej = Qhx + sum(Qc) + sum(Pc);
trun = O.tower_run > 0; nt = sum(trun);
Tl = X.Tl; tspd = X.tspd;
Qi = zeros(1,2); app = zeros(1,2); fkw = zeros(1,2); ent = zeros(1,2);
lsum = 0;
for c = 1:2
    if trun(c), cmd = ctrl.tower_cmd; else, cmd = 0; end
    tspd(c) = tspd(c) + (cmd - tspd(c))*min(1, dt/P.tau.tower_fan);
    if nt > 0, Qi(c) = Qrej/nt; end
    a_ = P.tower_app_nom*(max(Qi(c),1)/P.tower_Qnom)^0.6/(0.15 + 0.85*tspd(c))^0.7*(1 + 1.6*F.tower_deg(c));
    if trun(c) && cw_on, tg = D.wb + a_; else, tg = D.db; end
    Tl(c) = Tl(c) + (tg - Tl(c))*min(1, dt/P.tau.Tctl);
    if trun(c), lsum = lsum + Tl(c); end
    app(c) = Tl(c) - D.wb;
    fkw(c) = P.tower_fan_kw*tspd(c)^3;
    if cw_on, ent(c) = Tctl + Qrej/C_cw; else, ent(c) = Tctl; end
end
if nt > 0, Tctl = lsum/nt; else, Tctl = Tctl + (D.db - Tctl)*min(1, dt/P.tau.Tctl); end
X.Tchws = Tchws; X.Tchwr = Tchwr; X.Tl = Tl; X.tspd = tspd; X.Tctl = Tctl;
if cw_on, cwp = P.cwp_kw; else, cwp = 0; end
y = struct('Tchws', Tchws, 'Tchwr', Tchwr, 'Qhx', Qhx, 'eps_hx', eps_hx, 'Taft', Taft, 'Tcwe', Tcwe, ...
    'Qc', Qc, 'Pc', Pc, 'cop', cop, 'plr', plr, 'cap', cap, 'cwl', cwl, 'chws_c', chws_c, ...
    'Qrej', Qrej, 'tspd', tspd, 'tower_kw', fkw, 'Qi', Qi, 'app', app, 'Tl', Tl, 'Tent', ent, ...
    'Tctl', Tctl, 'qcw', qcw, 'cwp_kw', cwp, 'ua_hx', eps_hx*min(C_chw, C_cw)*double(Qhx > 0), ...
    'P_ch', sum(Pc), 'P_tower', sum(fkw));
end
