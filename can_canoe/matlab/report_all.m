% 한 번에 실행: 차(07) → 신호등(08) → depth 거리(09). 그림은 모두 화면에 뜬다.
%   MATLAB에서:  cd can_canoe/matlab; report_all (결과는 이 폴더에 저장)
% T7(/Volumes/T7)이 연결되어 있어야 한다.
keepOpen = true;
here = fileparts(mfilename('fullpath'));
assert(isfolder('/Volumes/T7'), 'T7이 연결되어 있지 않습니다.');
jobs = {'car_threshold_bands.m', ...
        'tl_threshold_bands.m', ...
        'depth_distance_figs.m'};
for k = 1:numel(jobs)
    fprintf('[%d/%d] %s\n', k, numel(jobs), jobs{k});
    clearvars -except here jobs k keepOpen
    run(fullfile(here, jobs{k}));
end
fprintf('완료: figure %d개\n', numel(findall(groot,'Type','figure')));
