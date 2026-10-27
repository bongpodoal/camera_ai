% 3번째 줄: 차 신뢰도 임계값 0.05~0.95 (0.1 간격) 비교 (1~2줄 lane_threshold_bands.m 과 같은 형식)
% 임계값 10개 = 무지개색 (0.05 빨강 -> 0.95 보라). 박스 색 = 그 박스가 통과하는 가장 높은 임계값. depth 가 찍힌 이미지에서 차 2대 이상인 프레임 3장을 골라 비교
% 실행: MATLAB 명령창에서 car_threshold_bands   (터미널: matlab -batch "run('car_threshold_bands.m')")
%   runDir, outDir, seqs 를 먼저 지정하면 그 값을 쓴다 (seqs 를 안 주면 자동으로 3장 선택)
if ~exist('runDir','var'), runDir = '/Volumes/T7/camera_ai/can_canoe/runs/20261027_objthr_90s'; end
if ~exist('outDir','var'), outDir = fileparts(mfilename('fullpath')); end
if usejava('desktop'), vis = 'on'; else, vis = 'off'; end
T = 0.05:0.10:0.95;  n = numel(T);   % 임계값 10개
IOU = 0.7;                           % 호스트 후처리와 같은 NMS 기준
W = 512; H = 288;                    % 후보 박스 좌표(0~1) -> 이미지 픽셀
cmap = hsv2rgb([linspace(0,0.78,n)' ones(n,2)]);   % 1단계(0.05)=빨강 ... 10단계(0.95)=보라
name = '차 인식률 임계값';
scr = get(0,'ScreenSize'); if ~usejava('desktop'), scr = [1 1 2200 1300]; end   % MATLAB 창으로 볼 때만 화면 크기에 맞춤 (화면보다 큰 창은 줄어 제목이 겹침), 파일 저장(-batch)은 원래 크기
fitpos = @(w,h) [0 0 min(w,scr(3)-80) min(h,scr(4)-120)];
bright = @(im) bright_auto(im);   % 야간 영상이 어두워서 화면 표시만 프레임마다 평균 밝기 약 0.3 으로 맞춤 (감마 0.5~1, 박스·depth 값은 그대로)

% ---- 후보(NMS 전)에서 차 점수만 꺼내 프레임마다 NMS ----
cd_ = readtable(fullfile(runDir,'raw_ai_candidates.csv'));
allSeq = unique(cd_.frame_seq);
rows = cell(numel(allSeq),1);
for k = 1:numel(allSeq)
    c = cd_(cd_.frame_seq==allSeq(k) & cd_.score_car >= T(1),:);
    if isempty(c), continue; end
    box = [c.x1 c.y1 c.x2 c.y2]; sc = c.score_car;
    keep = nms_greedy(box, sc, IOU);
    rows{k} = [repmat(allSeq(k),numel(keep),1) sc(keep) box(keep,:)];
end
B = cell2mat(rows);
bx = array2table(B,'VariableNames',{'seq','score','x1','y1','x2','y2'});
fprintf('프레임 %d개, 차 박스(0.05 이상, NMS 후) %d개\n', numel(allSeq), height(bx));

% ---- 박스마다 depth (박스 가운데 50% 영역의 0 아닌 depth 중앙값, m). depth 가 없으면 NaN ----
z = nan(height(bx),1);  cache = containers.Map('KeyType','double','ValueType','any');
for r = 1:height(bx)
    s = bx.seq(r);
    if ~isKey(cache,s)
        f = fullfile(runDir,'images',sprintf('%06d_depth.png',s));
        if isfile(f), cache(s) = double(imread(f)); else, cache(s) = []; end
    end
    d = cache(s);  if isempty(d), continue; end
    x1 = bx.x1(r)*W; x2 = bx.x2(r)*W; y1 = bx.y1(r)*H; y2 = bx.y2(r)*H;
    cx = (x1+x2)/2; cy = (y1+y2)/2; hw = (x2-x1)/4; hh = (y2-y1)/4;
    xs = max(1,round(cx-hw)):min(W,round(cx+hw));  ys = max(1,round(cy-hh)):min(H,round(cy+hh));
    v = d(ys,xs); v = v(v>0);
    if numel(v) >= 0.3*numel(d(ys,xs)), z(r) = median(v)/1000; end   % 가운데 영역의 30% 이상에 depth 가 있을 때만
end
bx.z_m = z;
bx.band = arrayfun(@(p) find(T <= p+1e-9, 1, 'last'), bx.score);   % 통과하는 가장 높은 임계값 번호 (1~10)
writetable(bx, fullfile(outDir,'차_박스_nms005.csv'));

% ---- 3장 선택: 차 2대 이상(점수 0.5 이상, depth 있음)이 또렷이 보이고 박스 점수가 0.9~0.08 로 퍼진 서로 다른 장면 (후보 17프레임을 눈으로 확인해 고름) ----
%   50: 도로 끝 흰 승용차 + 먼 차 (depth 약 9~10 m) / 90: 가까운 흰 승용차 + 먼 차 / 315: 오른쪽 가까운 SUV + 먼 차 (깊이 4~6 m)
if ~exist('seqs','var'), seqs = [50 90 315]; end
fprintf('선택한 프레임: %s\n', mat2str(seqs));

% ---- 그림 A: 프레임별 [원본 | depth | 박스 색 = 점수 구간] ----
fa = figure('Visible',vis,'Position',fitpos(1900,1000)); theme(fa,'dark');
tl = tiledlayout(numel(seqs),3,'TileSpacing','compact','Padding','compact');
for i = 1:numel(seqs)
    s = seqs(i);  bg = imread(fullfile(runDir,'raw_rgb',sprintf('%06d.png',s)));
    d = double(imread(fullfile(runDir,'images',sprintf('%06d_depth.png',s))));
    m = bx(bx.seq==s,:);
    nexttile; imshow(bright(bg)); title(sprintf('seq %d 원본 (표시용 밝기 보정, 프레임별 자동)',s));
    nexttile; dm = d/1000; dm(d==0) = NaN; im = imagesc(dm,[0 12]); set(im,'AlphaData',~isnan(dm)); axis image off; set(gca,'Color',[0 0 0]);
    colormap(gca,turbo); cb = colorbar; cb.Label.String = 'depth (m)'; title('depth (검정 = 값 없음)');
    nexttile; imshow(bright(bg)); hold on; draw_boxes(m, W, H, cmap, true); colormap(gca,cmap); clim([0 n]);
    cb = colorbar; cb.Ticks = 0.5:1:n; cb.TickLabels = arrayfun(@(x) sprintf('%.2f',x),T,'UniformOutput',false);
    title(sprintf('차 박스 (0.05 이상 %d개, 색 = 신뢰도 구간)',height(m)));
end
title(tl,sprintf('%s: 선택 프레임 %d장 (depth 있는 차 2대 이상)  빨강 0.05 ... 보라 0.95',name,numel(seqs)));
exportgraphics(fa, fullfile(outDir,'차_A_구간지도.png'),'Resolution',100);
if strcmp(vis,'off'), close(fa); end

% ---- 그림 B: 프레임마다 임계값 10개로 각각 필터 (임계값 이상 박스만, 색 = 임계값, 글자 = 점수·depth) ----
for i = 1:numel(seqs)
    s = seqs(i);  bg = imread(fullfile(runDir,'raw_rgb',sprintf('%06d.png',s)));
    m = bx(bx.seq==s,:);
    fb = figure('Visible',vis,'Position',fitpos(2000,560)); theme(fb,'dark');
    tl = tiledlayout(2,5,'TileSpacing','compact','Padding','loose');
    for j = 1:n
        mj = m(m.score >= T(j) - 1e-9,:);
        nexttile; imshow(bright(bg)); hold on;
        for r = 1:height(mj)
            rectangle('Position',[mj.x1(r)*W mj.y1(r)*H (mj.x2(r)-mj.x1(r))*W (mj.y2(r)-mj.y1(r))*H],'EdgeColor',cmap(j,:),'LineWidth',1.6);
            text(mj.x1(r)*W+2, max(mj.y1(r)*H-6,9), depth_label(mj.score(r),mj.z_m(r)),'Color',cmap(j,:),'FontSize',8,'FontWeight','bold','BackgroundColor',[0 0 0 0.5],'Clipping','on');
        end
        title(sprintf('p >= %.2f  (차 %d대)',T(j),height(mj)),'FontSize',10);
    end
    title(tl,sprintf('seq %d: 임계값별 차 검출 (임계값 이상, 색 = 임계값, 글자 = 점수 / depth)',s)); tl.Title.FontSize = 12;
    exportgraphics(fb, fullfile(outDir,sprintf('차_B_임계값10장_seq%d.png',s)),'Resolution',100);
    if strcmp(vis,'off'), close(fb); end
end

% ---- 표: 임계값별 차 수 (선택 프레임별 + 전체 455프레임 합계, 차가 1대·2대 이상 있는 프레임 비율) ----
cnt = zeros(numel(seqs),n);  tot = zeros(1,n);  f1 = zeros(1,n);  f2 = zeros(1,n);
for j = 1:n
    s_ = bx(bx.score >= T(j) - 1e-9,:);
    for i = 1:numel(seqs), cnt(i,j) = sum(s_.seq == seqs(i)); end
    tot(j) = height(s_);
    [u,~,ic] = unique(s_.seq);  per = accumarray(ic,1);
    f1(j) = numel(u)/numel(allSeq);  f2(j) = sum(per>=2)/numel(allSeq);
end
vn = arrayfun(@(x) sprintf('p%.2f',x),T,'UniformOutput',false);
tb = array2table([cnt; tot; tot/numel(allSeq); f1; f2],'VariableNames',vn);
tb = addvars(tb, [arrayfun(@(s) sprintf('seq%d',s),seqs(:),'UniformOutput',false); {'전체_차수'; '프레임당_평균'; '차_1대이상_프레임비율'; '차_2대이상_프레임비율'}], 'Before',1,'NewVariableNames','항목');
writetable(tb, fullfile(outDir,'차_임계값별_개수.csv'));
disp(tb);

% ---- 그림 C: 임계값별 개수 ----
fc = figure('Visible',vis,'Position',[0 0 1500 600]); theme(fc,'dark'); tiledlayout(1,2,'TileSpacing','compact');
nexttile; hold on;
for i = 1:numel(seqs), plot(T,cnt(i,:),'-o','LineWidth',1.5,'DisplayName',sprintf('seq %d',seqs(i))); end
grid on; xlabel('임계값'); ylabel('프레임 안 차 박스 수'); legend('Location','northeast'); title('선택 프레임: 임계값별 차 수');
nexttile; plot(T,100*f1,'-o','LineWidth',1.5,'DisplayName','차 1대 이상'); hold on; plot(T,100*f2,'-s','LineWidth',1.5,'DisplayName','차 2대 이상');
grid on; ylim([0 100]); xlabel('임계값'); ylabel('프레임 % (전체)'); legend('Location','northeast'); title(sprintf('임계값별 검출 프레임 비율 (전체 %d프레임)',numel(allSeq)));
exportgraphics(fc, fullfile(outDir,'차_C_임계값별_개수.png'),'Resolution',110);
if strcmp(vis,'off'), close(fc); end
if ~usejava('desktop') && ~exist('keepOpen','var'), exit(0); end

function out = bright_auto(im)
x = double(im)/255;  mu = max(mean(x(:)),1e-3);
g = min(1,max(0.5, log(0.3)/log(mu)));   % 평균이 0.3 이 되는 감마 (이미 밝으면 1, 너무 어두운 프레임은 0.5 까지만: 더 올리면 압축 잡음이 점무늬로 보임)
out = uint8(255*x.^g);
end

function draw_boxes(m, W, H, cmap, withText)
for r = 1:height(m)
    c = cmap(m.band(r),:);
    rectangle('Position',[m.x1(r)*W m.y1(r)*H (m.x2(r)-m.x1(r))*W (m.y2(r)-m.y1(r))*H],'EdgeColor',c,'LineWidth',1.6);
    if withText, text(m.x1(r)*W+2, max(m.y1(r)*H-6,9), depth_label(m.score(r),m.z_m(r)),'Color',c,'FontSize',8,'FontWeight','bold','BackgroundColor',[0 0 0 0.5],'Clipping','on'); end
end
end

function t = depth_label(score, z)
if isnan(z), t = sprintf('%.2f',score); else, t = sprintf('%.2f  %.1fm',score,z); end
end

function keep = nms_greedy(b, s, thr)
% b: [x1 y1 x2 y2], s: 점수. 점수 내림차순 탐욕 NMS, 남길 행 번호
[~,o] = sort(s,'descend'); keep = [];
while ~isempty(o)
    i = o(1); keep(end+1) = i; %#ok<AGROW>
    if numel(o) == 1, break; end
    r = o(2:end);
    ix1 = max(b(i,1),b(r,1)); iy1 = max(b(i,2),b(r,2)); ix2 = min(b(i,3),b(r,3)); iy2 = min(b(i,4),b(r,4));
    inter = max(0,ix2-ix1) .* max(0,iy2-iy1);
    a1 = (b(i,3)-b(i,1))*(b(i,4)-b(i,2)); a2 = (b(r,3)-b(r,1)).*(b(r,4)-b(r,2));
    o = r(inter ./ (a1 + a2 - inter + 1e-9) <= thr);
end
end
