function [X, y] = dcx_hydraulics(X, F, O, Ap, ctrl, P)
%DCX_HYDRAULICS CHW pumps on a common header against a valve-dependent system
%   curve (Subsystem 03). States: n (VFD speed), q (loop flow), H (head).
%   Parallel-pump operating point solved by bisection on H.
%   ctrl.pump_cmd = DP PI controller output (speed demand 0.3..1).
dt = P.dt; H0 = P.pump_H0; kp = P.pump_kp; Hs = P.sys_Hs;
crun = O.crah_run > 0;
if any(crun), vmean = sum(Ap.valve.*crun)/sum(crun); else, vmean = 0.15; end
ks = P.sys_kf + P.sys_kv/max(0.15, vmean)^2;   % design: kf = 0, kv = ks0 (Python parity)
a = 1 - 0.28*F.pump_cav;
runp = O.pump_run > 0;
qp = zeros(1,3);
n = X.n; H = X.H; q = X.q;
if any(runp)
    n = n + (ctrl.pump_cmd - n)*min(1, dt/P.tau.vfd);
    lo = Hs; hi = max(a.*runp*H0*n*n);
    if hi > lo
        for it = 1:40
            mid = 0.5*(lo + hi);
            qs = 0;
            for p = 1:3
                if runp(p), qs = qs + sqrt(max(0, (a(p)*H0*n*n - mid)/kp)); end
            end
            if qs > sqrt(max(0, (mid - Hs)/ks)), lo = mid; else, hi = mid; end
        end
        H = 0.5*(lo + hi);
        for p = 1:3
            if runp(p), qp(p) = sqrt(max(0, (a(p)*H0*n*n - H)/kp)); end
        end
    else
        H = lo;
    end
    q = q + (sum(qp) - q)*min(1, dt/P.tau.flow);
else
    H = H + (0 - H)*min(1, dt/3);
    q = q + (0 - q)*min(1, dt/4);
end
Pw = zeros(1,3); eta = zeros(1,3); vib = zeros(1,3); cur = zeros(1,3); spd = zeros(1,3); head = zeros(1,3);
for p = 1:3
    brg = F.pump_brg(p);
    eta_bep = P.pump_eta_bep*(1 - F.pump_effdrop(p))*(1 - 0.06*brg);
    if runp(p) && n > 0.05
        x = qp(p)/(n*P.pump_q_bep);
        eta(p) = max(0.15, eta_bep*(1 - 0.8*(x - 1)^2));
        Pw(p) = qp(p)*H/1000/eta(p) + 0.05*brg;
        vib(p) = 0.9 + 1.3*n*n + 6.0*brg^1.5 + 3.5*F.pump_cav(p);
        cur(p) = Pw(p)*1000/(sqrt(3)*415*0.85*0.90);
        spd(p) = n; head(p) = H;
    end
end
X.n = n; X.H = H; X.q = q;
y = struct('H', H, 'q', q, 'qp', qp, 'P', Pw, 'eta', eta, 'vib', vib, 'cur', cur, ...
    'speed', spd, 'head', head, 'P_tot', sum(Pw));
end
