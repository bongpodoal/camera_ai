% 5번째 줄: RGB 송출 OFF 와 ON 일 때 지연 비교 (run_line45.sh STAGE=rgbonoff 결과)
% 입력: baseDir 아래 '*_rgbonoff_off_*', '*_rgbonoff_rgb_*' 폴더 (frames.csv, summary.csv)
% 실행: baseDir 를 지정한 뒤 rgb_onoff_delay     (예: baseDir = '/path/to/runs'; rgb_onoff_delay)
% 출력(baseDir/matlab_rgb_onoff/): 01_지연_비교.png, delay_by_run.csv, delay_summary.csv
%  edge_ms = 칩 안에서 걸린 시간, pc_ms = 칩 출력 → 호스트 수신까지, total = edge + pc (카메라 촬영 → 호스트 수신)
if ~exist('baseDir','var'), baseDir = uigetdir(pwd,'runs 폴더'); end
outDir = fullfile(baseDir,'matlab_rgb_onoff'); if ~exist(outDir,'dir'), mkdir(outDir); end
if usejava('desktop'), vis = 'on'; else, vis = 'off'; end
WARM = 15;                           % 앞 15프레임(5 fps 에서 3초)은 워밍업이라 뺀다
conds = {'off','rgb'}; label = {'RGB OFF','RGB ON'}; col = [0.2 0.4 0.8; 0.9 0.4 0.1];

R = struct('cond',{},'dir',{},'edge',{},'pc',{},'post',{},'fps',[],'eth',[],'run',[]);
for c = 1:2
    d = dir(fullfile(baseDir,sprintf('*_rgbonoff_%s_*',conds{c}))); d = d([d.isdir]);
    for i = 1:numel(d)
        fdir = fullfile(d(i).folder,d(i).name);
        if ~isfile(fullfile(fdir,'frames.csv')), continue; end
        f = readtable(fullfile(fdir,'frames.csv')); s = readtable(fullfile(fdir,'summary.csv'));
        f = f(WARM+1:end,:);
        ok = ~isnan(f.edge_ms) & f.edge_ms > 0 & ~isnan(f.pc_ms);      % 칩 지연값이 없던 프레임(0/빈칸) 제외
        R(end+1) = struct('cond',c,'dir',d(i).name,'edge',f.edge_ms(ok),'pc',f.pc_ms(ok),'post',f.post_ms(ok), ...
                          'fps',s.fps_avg(1),'eth',s.eth_MBps(1),'run',numel(R)+1); %#ok<AGROW>
    end
end
assert(~isempty(R), 'rgbonoff 폴더가 없다: %s', baseDir);
for c = 1:2, fprintf('%s: %d회\n', label{c}, nnz([R.cond]==c)); end

% ---- 실행별 표 ----
tb = table();
for i = 1:numel(R)
    tb(i,:) = {R(i).dir, label{R(i).cond}, numel(R(i).edge), R(i).fps, median(R(i).edge), prctile(R(i).edge,95), median(R(i).pc), prctile(R(i).pc,95), ...
               median(R(i).edge+R(i).pc), prctile(R(i).edge+R(i).pc,95), median(R(i).post), R(i).eth};
end
tb.Properties.VariableNames = {'run','condition','frames','fps','edge_med_ms','edge_p95_ms','pc_med_ms','pc_p95_ms','total_med_ms','total_p95_ms','post_med_ms','eth_MBps'};
writetable(tb, fullfile(outDir,'delay_by_run.csv')); disp(tb);

% ---- 조건별 합산·차이 (RGB ON - OFF), 프레임 단위 부트스트랩 95% 신뢰구간 ----
rng(0); nb = 1000; names_ = {'edge','pc','total'};
sm = table(); 
for m = 1:3
    v = cell(1,2);
    for c = 1:2
        k = find([R.cond]==c); x = [];
        for i = k, e = R(i).edge; p = R(i).pc; if m==1, x = [x; e]; elseif m==2, x = [x; p]; else, x = [x; e+p]; end, end %#ok<AGROW>
        v{c} = x;
    end
    d0 = median(v{2}) - median(v{1});
    bs = zeros(nb,1); for b = 1:nb, bs(b) = median(v{2}(randi(numel(v{2}),numel(v{2}),1))) - median(v{1}(randi(numel(v{1}),numel(v{1}),1))); end
    sm(m,:) = {names_{m}, median(v{1}), median(v{2}), d0, prctile(bs,2.5), prctile(bs,97.5), mean(v{1}), mean(v{2}), prctile(v{1},95), prctile(v{2},95)}; %#ok<AGROW>
end
sm.Properties.VariableNames = {'metric','off_median_ms','on_median_ms','diff_on_minus_off_ms','diff_ci_low','diff_ci_high','off_mean_ms','on_mean_ms','off_p95_ms','on_p95_ms'};
writetable(sm, fullfile(outDir,'delay_summary.csv')); disp(sm);

% ---- 그림 ----
f = figure('Visible',vis,'Position',[0 0 1800 1000]); tl = tiledlayout(2,3,'TileSpacing','compact','Padding','compact');
for m = 1:3
    nexttile; hold on; g = []; gv = [];
    for c = 1:2
        for i = find([R.cond]==c)
            if m==1, x = R(i).edge; elseif m==2, x = R(i).pc; else, x = R(i).edge + R(i).pc; end
            g = [g; repmat(c,numel(x),1)]; gv = [gv; x]; %#ok<AGROW>
        end
    end
    boxchart(categorical(g,[1 2],label), gv); grid on; ylabel('ms'); ttl = {'edge: 칩 안','pc: 칩 출력 → 호스트 수신','total: 촬영 → 호스트 수신'}; title(sprintf('%s 지연', ttl{m}));
end
nexttile([1 2]); hold on;
for i = 1:numel(R)
    x = R(i).edge + R(i).pc; plot(1:numel(x), x, 'Color', [col(R(i).cond,:) 0.6]);
end
grid on; xlabel('프레임(워밍업 제외)'); ylabel('total ms'); title('실행별 total 지연 (파랑=RGB OFF, 주황=RGB ON)');
nexttile; b = bar(categorical(label), [mean([tb.eth_MBps(strcmp(tb.condition,label{1}))]) mean([tb.eth_MBps(strcmp(tb.condition,label{2}))])]); grid on; ylabel('MB/s'); title('이더넷 수신량');
title(tl, sprintf('RGB OFF vs ON 지연 비교 (edge 차이 %+.1f ms [%.1f, %.1f], total 차이 %+.1f ms [%.1f, %.1f])', sm.diff_on_minus_off_ms(1), sm.diff_ci_low(1), sm.diff_ci_high(1), sm.diff_on_minus_off_ms(3), sm.diff_ci_low(3), sm.diff_ci_high(3)));
exportgraphics(f, fullfile(outDir,'01_지연_비교.png'),'Resolution',100); if strcmp(vis,'off'), close(f); end
if ~usejava('desktop') && ~exist('keepOpen','var'), exit(0); end
