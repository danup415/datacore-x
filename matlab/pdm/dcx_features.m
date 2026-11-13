function Fx = dcx_features(L, P, sp, win, hop)
%DCX_FEATURES Window features (sensor-only + physics-residual) per asset class
%   from a measured run L (dcx_sim_matlab with 'Sensors',true).
%   Returns struct of tables: pump, crah, plant. Labels come from the
%   injected-fault severities (ground truth), used ONLY as training targets.
if nargin < 4, win = 120; end
if nargin < 5, hop = 60; end
T = dcx_tag_list();
col = @(a,k) find(strcmp(T.asset, a) & strcmp(T.key, k), 1);
M = L.meas; n = size(M,1);
starts = 1:hop:(n - win + 1);
pump = []; crah = []; plant = [];
for w = starts
    ix = w:(w + win - 1);
    m = @(a,k) mean(M(ix, col(a,k)), 'omitnan');
    sd = @(a,k) std(M(ix, col(a,k)), 'omitnan');
    fs = L.fs(ix(end), :);
    % ---------------- pumps ------------------------------------------------
    for i = 1:3
        id = sprintf('P-%02d', i);
        spd = m(id,'speed_pct');
        if spd < 5, continue; end
        nn = spd/100; q = m(id,'flow_ls'); h = m(id,'head_kpa'); pw = m(id,'power_kw'); vib = m(id,'vib_mms');
        Hexp = P.pump_H0*nn^2 - P.pump_kp*q^2;
        x = q/(nn*P.pump_q_bep); eexp = max(0.15, P.pump_eta_bep*(1 - 0.8*(x - 1)^2));
        em = q*h/1000/max(pw, 1e-3);
        sev = [fs(i), fs(3+i), fs(6+i)/0.4];
        pump = [pump; nn, q, h, pw, m(id,'eff_pct'), vib, sd(id,'vib_mms'), m(id,'current_a'), ...
            (Hexp - h)/max(Hexp,1), (eexp - em)/eexp, vib - (0.9 + 1.3*nn^2), sev, i, ix(end)]; %#ok<AGROW>
    end
    % ---------------- CRAH fans ----------------------------------------------
    for c = 1:4
        id = sprintf('CRAH-%02d', c);
        s = m(id,'fan_speed_pct')/100;
        if s < 0.1, continue; end
        vib = m(id,'vib_mms'); fk = m(id,'fan_kw'); af = m(id,'airflow_m3s');
        afe = s*P.crah_m_max/P.rho_air;
        sev = [fs(9+c), fs(13+c), fs(17+c)];
        crah = [crah; s, af, fk, vib, sd(id,'vib_mms'), m(id,'supply_c'), m(id,'valve_pct'), ...
            vib - 0.8*s, (fk - P.crah_fan_kw*s^3)/max(P.crah_fan_kw*s^3, 0.05), (afe - af)/afe, sev, c, ix(end)]; %#ok<AGROW>
    end
    % ---------------- chiller / HX / towers -------------------------------------
    if m('CH-01','load_kw') > 10
        plr = max(0.15, m('CH-01','plr_pct')/100); cwe = m('CH-01','cwe_c'); cop = m('CH-01','cop');
        Tev = sp.chws_c - 2 + 273.15; Tcd = cwe + 5.5 + 273.15;
        cexp = min(12, P.ch_carnot*Tev/max(3, Tcd - Tev)*(1 - P.ch_plr_a*(1 - plr)^2));
        q1 = m('PIPE-CHWS','flow_ls'); q2 = m('PIPE-CW','flow_ls');
        C1 = 4.186*q1; C2 = 4.186*max(q2, 0.1);
        dTm = m('HX-01','chw_in_c') - m('HX-01','cw_in_c');
        if m('HX-01','duty_kw') > 1 && dTm > 0.8
            epsm = C1*(m('HX-01','chw_in_c') - m('HX-01','chw_out_c'))/(min(C1,C2)*dTm);
        else
            epsm = P.hx_eps;
        end
        rt = zeros(1,2); appm = zeros(1,2);
        for k = 1:2
            id = sprintf('CT-%02d', k); s = m(id,'fan_speed_pct')/100; Qi = m(id,'heat_rej_kw');
            ae = P.tower_app_nom*(max(Qi,1)/P.tower_Qnom)^0.6/(0.15 + 0.85*s)^0.7;
            appm(k) = m(id,'leaving_c') - m(id,'wetbulb_c');
            rt(k) = (appm(k) - ae)/max(ae, 0.5);
        end
        sev = [max(fs(22:23)), fs(24), max(fs(25:26))];
        plant = [plant; m('CH-01','load_kw'), cop, plr, cwe, m('CH-01','chws_c'), m('HX-01','duty_kw'), ...
            m('HX-01','effectiveness_pct'), appm, m('CT-01','fan_speed_pct'), m('CT-02','fan_speed_pct'), ...
            m('CH-01','power_kw'), (cexp - cop)/cexp, P.hx_eps - epsm, rt, sev, 0, ix(end)]; %#ok<AGROW>
    end
end
Fx.pump = array2table(pump, 'VariableNames', {'speed','flow','head','power','eff','vib','vib_sd','current', ...
    'r_head','r_eff','r_vib','sev_brg','sev_cav','sev_eff','asset','t'});
Fx.crah = array2table(crah, 'VariableNames', {'speed','airflow','fan_kw','vib','vib_sd','supply','valve', ...
    'r_vib','r_power','r_airflow','sev_imb','sev_brg','sev_block','asset','t'});
Fx.plant = array2table(plant, 'VariableNames', {'ch_load','cop','plr','cwe','chws','hx_duty','hx_eff', ...
    'app1','app2','ct1_fan','ct2_fan','ch_power','r_cop','r_hx','r_ct1','r_ct2','sev_ch','sev_hx','sev_ct','asset','t'});
end
