function root = dcx_startup()
%DCX_STARTUP Add the DATACORE-X MATLAB/Simulink project folders to the path.
root = fileparts(mfilename('fullpath'));
addpath(fullfile(root,'params'), fullfile(root,'plant'), fullfile(root,'model'), ...
        fullfile(root,'tests'), fullfile(root,'control'), fullfile(root,'pdm'), fullfile(root,'bridge'));
fprintf('DATACORE-X MATLAB project on path: %s\n', root);
end
