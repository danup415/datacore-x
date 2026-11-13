function [st, u] = dcx_pi(st, err, cfg, dt)
%DCX_PI Discrete PI with conditional-integration anti-windup (reference
%   implementation identical to the Python surrogate; the Simulink model
%   uses Discrete PID Controller blocks with clamping).
uu = cfg.kp*err + st.i;
u = min(cfg.hi, max(cfg.lo, uu));
if u == uu || (uu > cfg.hi && err < 0) || (uu < cfg.lo && err > 0)
    st.i = min(cfg.hi, max(cfg.lo - cfg.hi, st.i + cfg.ki*err*dt));
end
end
