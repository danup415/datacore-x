function mpcobj = dcx_design_mpc(M, lo, hi, Tmax, rate)
%DCX_DESIGN_MPC Economic supervisory MPC (MPC Toolbox) on the identified model.
%   MVs: CHW supply sp, supply-air sp, max-inlet target (deviation variables)
%   MDs: IT load, wet-bulb.  OVs: max rack inlet (constraint <= Tmax, soft),
%   facility power (economic term: tracked toward a reference far below the
%   achievable value, i.e. minimised; quadratic surrogate of the linear cost).
plant = setmpcsignals(M.sys, 'MV', 1:3, 'MD', 4:5);
plant.D(:, :) = 0;
mpcobj = mpc(plant, M.Ts);
mpcobj.PredictionHorizon = 20;              % 20 min
mpcobj.ControlHorizon = 4;
for i = 1:3
    mpcobj.MV(i).Min = lo(i) - M.U0(i); mpcobj.MV(i).Max = hi(i) - M.U0(i);
    mpcobj.MV(i).RateMin = -rate; mpcobj.MV(i).RateMax = rate;
    mpcobj.MV(i).ScaleFactor = hi(i) - lo(i);
end
mpcobj.OV(1).Max = Tmax - M.Y0(1);
mpcobj.OV(1).MaxECR = 0.2;                  % soft, strongly penalised
mpcobj.OV(1).ScaleFactor = 5; mpcobj.OV(2).ScaleFactor = 30;
mpcobj.Weights.OutputVariables = [0 1];      % economic: facility power
mpcobj.Weights.ManipulatedVariables = [0 0 0];
mpcobj.Weights.ManipulatedVariablesRate = [0.3 0.3 0.3];
mpcobj.Weights.ECR = 1e5;
setEstimator(mpcobj, 'default');
mpcverbosity off;
end
