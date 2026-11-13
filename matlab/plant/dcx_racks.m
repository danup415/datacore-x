function [X, y] = dcx_racks(X, D, F, O, Ap, P)
%DCX_RACKS IT workload, rack power/heat and rack outlet thermal RC (Subsystem 01).
%   X.Tout (1x8) state. Ap = previous air-side outputs (Tin, Tha).
dt = P.dt;
U = zeros(1,8);
for r = 1:8
    U(r) = min(1, max(0.05, (P.u_base(r) + D.diurnal + D.ou(r)) * (1 + F.it_inc)));
end
% workload placement: redistribute at constant total utilisation (water-filling)
w = ones(1,8);
if F.placement == 1, w = [1.7 1.7 1.7 1.7 0.3 0.3 0.3 0.3];
elseif F.placement == 2, w = [1.8 0.2 0.2 1.8 1.8 0.2 0.2 1.8];
end
if F.placement > 0
    tot = sum(U); alloc = zeros(1,8); free = true(1,8); rem = tot;
    for it = 1:8
        ws = sum(w(free));
        if ws <= 0 || rem <= 1e-9, break; end
        alloc(free) = alloc(free) + rem * w(free) / ws;
        rem = 0;
        for r = 1:8
            if free(r) && alloc(r) > 1
                rem = rem + alloc(r) - 1; alloc(r) = 1; free(r) = false;
            end
        end
    end
    U = max(0.05, alloc);
end
Pw = zeros(1,8); m = zeros(1,8); util = zeros(1,8); gpu = zeros(1,8);
on = O.it_powered > 0;
for r = 1:8
    u = U(r);
    if Ap.Tin(r) > 35, u = u * max(0.3, 1 - 0.12*(Ap.Tin(r) - 35)); end  % server thermal throttling
    if on
        Pw(r) = P.rack_P_idle + P.rack_P_span*u + F.rack_extra(r);
        m(r) = Pw(r) / (P.cp_air * P.rack_dT);
        util(r) = 100*u;
        gpu(r) = P.rack_gpu(r) * min(100, 112*u);
    end
end
% outlet temperature RC (explicit Euler, matches the Python surrogate)
Tout = X.Tout;
for r = 1:8
    if Pw(r) > 0
        dT = (Pw(r) - m(r)*P.cp_air*(Tout(r) - Ap.Tin(r))) / P.rack_C;
    else
        dT = (Ap.Tha - Tout(r)) / 300;
    end
    Tout(r) = Tout(r) + dT*dt;
end
X.Tout = Tout;
y = struct('P', Pw, 'm', m, 'util', util, 'gpu', gpu, 'Tout', Tout, 'airflow', m / P.rho_air, ...
    'P_it', sum(Pw), 'm_tot', sum(m));
end
