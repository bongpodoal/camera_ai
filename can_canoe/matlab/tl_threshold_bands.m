% 3번째 줄: 신호등(빨강·초록·노랑) 신뢰도 임계값 0.05~0.95 (0.1 간격) 비교 (car_threshold_bands.m 과 같은 형식)
% 임계값 10개 = 무지개색 (0.05 빨강 -> 0.95 보라). 박스 색 = 그 박스가 통과하는 가장 높은 임계값.
% 1차 촬영은 빨간불 위주, 2차는 초록불 위주라 빨강은 1차에서, 초록은 2차에서 프레임 3장씩 고른다. 노랑은 표본이 적어 개수 표에만 넣는다.
% 실행: MATLAB 명령창에서 tl_threshold_bands   (터미널: matlab -batch "outDir=pwd; run('tl_threshold_bands.m')")
%   baseDir(촬영 폴더들이 있는 곳), outDir 을 먼저 지정하면 그 값을 쓴다
if ~exist('baseDir','var'), baseDir = '/Volumes/T7/camera_ai/can_canoe/runs'; end
if ~exist('outDir','var'), outDir = fileparts(mfilename('fullpath')); end
if usejava('desktop'), vis = 'on'; else, vis = 'off'; end
T = 0.05:0.10:0.95;  n = numel(T);   % 임계값 10개
IOU = 0.7;  W = 512; H = 288;
cmap = hsv2rgb([linspace(0,0.78,n)' ones(n,2)]);   % 1단계(0.05)=빨강 ... 10단계(0.95)=보라
scr = get(0,'ScreenSize'); if ~usejava('desktop'), scr = [1 1 2200 1300]; end   % MATLAB 창으로 볼 때만 화면 크기에 맞춤 (화면보다 큰 창은 줄어 제목이 겹침), 파일 저장(-batch)은 원래 크기
fitpos = @(w,h) [0 0 min(w,scr(3)-80) min(h,scr(4)-120)];
bright = @(im) bright_auto(im);   % 어두운 영상이라 화면 표시만 프레임마다 평균 밝기 약 0.3 으로 맞춤 (감마 0.5~1, 박스·depth 값은 그대로)

% 촬영 2개: {폴더, 이름, 프레임 3장을 고를 색}
runs = { '20261027_tl_60s',    '1차(빨강 위주)', 'red',   [30 116 200];
         '20261027_tl_60s_r2', '2차(초록 위주)', 'green', [302 202 288] };
colors = {'red','green','yellow'};  cname = struct('red','빨강','green','초록','yellow','노랑');
if exist('seqsRed','var'), runs{1,4} = seqsRed; end
if exist('seqsGreen','var'), runs{2,4} = seqsGreen; end

cnt = struct();   % cnt.(run).(색) = [총 박스 수; 검출 있는 프레임 비율] x 임계값
for k = 1:size(runs,1)
    runDir = fullfile(baseDir, runs{k,1});  rname = runs{k,2};  col = runs{k,3};  seqs = runs{k,4};
    cd_ = readtable(fullfile(runDir,'raw_ai_candidates.csv'));
    allSeq = unique(cd_.frame_seq);
    B = struct();
    for ci = 1:3
        c = colors{ci};  sc_all = cd_.(['score_tl_' c]);
        rows = cell(numel(allSeq),1);
        for f = 1:numel(allSeq)
            sel = cd_.frame_seq==allSeq(f) & sc_all >= T(1);
            if ~any(sel), continue; end
            box = [cd_.x1(sel) cd_.y1(sel) cd_.x2(sel) cd_.y2(sel)];  sc = sc_all(sel);
            keep = nms_greedy(box, sc, IOU);
            rows{f} = [repmat(allSeq(f),numel(keep),1) sc(keep) box(keep,:)];
        end
        B.(c) = array2table(cell2mat(rows),'VariableNames',{'seq','score','x1','y1','x2','y2'});
        B.(c).band = arrayfun(@(p) find(T <= p+1e-9, 1, 'last'), B.(c).score);
    end
    % 선택 색의 박스에 depth 붙이기 (박스 가운데 50% 영역의 0 아닌 depth 중앙값, m; 30% 미만이면 NaN)
    bx = B.(col);  z = nan(height(bx),1);  cache = containers.Map('KeyType','double','ValueType','any');
    for r = 1:height(bx)
        s = bx.seq(r);
        if ~isKey(cache,s)
            f = fullfile(runDir,'images',sprintf('%06d_depth.png',s));
            if isfile(f), cache(s) = double(imread(f)); else, cache(s) = []; end
        end
        d = cache(s);  if isempty(d), continue; end
        cx = (bx.x1(r)+bx.x2(r))/2*W; cy = (bx.y1(r)+bx.y2(r))/2*H; hw = (bx.x2(r)-bx.x1(r))*W/4; hh = (bx.y2(r)-bx.y1(r))*H/4;
        xs = max(1,round(cx-hw)):min(W,max(1,round(cx+hw)));  ys = max(1,round(cy-hh)):min(H,max(1,round(cy+hh)));
        v = d(ys,xs); v = v(v>0);
        if numel(v) >= 0.3*numel(d(ys,xs)), z(r) = median(v)/1000; end
    end
    bx.z_m = z;
    writetable(bx, fullfile(outDir,sprintf('신호등_%s_박스_nms005.csv',cname.(col))));
    fprintf('%s: %s 박스 %d개(0.05 이상), 선택 프레임 %s\n', rname, cname.(col), height(bx), mat2str(seqs));

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
        title(sprintf('신호등 %s 박스 (0.05 이상 %d개, 색 = 신뢰도 구간)',cname.(col),height(m)));
    end
    title(tl,sprintf('신호등 %s 임계값: %s 선택 프레임 %d장   빨강 0.05 ... 보라 0.95',cname.(col),rname,numel(seqs)));
    exportgraphics(fa, fullfile(outDir,sprintf('신호등_%s_A_구간지도.png',cname.(col))),'Resolution',100);
    if strcmp(vis,'off'), close(fa); end

    % ---- 그림 B: 프레임마다 임계값 10개로 각각 필터 ----
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
            title(sprintf('p >= %.2f  (%s %d개)',T(j),cname.(col),height(mj)),'FontSize',10);
        end
        title(tl,sprintf('신호등 %s seq %d: 임계값별 검출 (임계값 이상, 색 = 임계값, 글자 = 점수 / depth)',cname.(col),s)); tl.Title.FontSize = 12;
        exportgraphics(fb, fullfile(outDir,sprintf('신호등_%s_B_임계값10장_seq%d.png',cname.(col),s)),'Resolution',100);
        if strcmp(vis,'off'), close(fb); end
    end

    % ---- 3색 개수 (선택 프레임 밖 전체 프레임 기준) ----
    key = sprintf('r%d',k);
    for ci = 1:3
        c = colors{ci};  tot = zeros(1,n);  fr = zeros(1,n);
        for j = 1:n
            s_ = B.(c)(B.(c).score >= T(j) - 1e-9,:);
            tot(j) = height(s_);  fr(j) = numel(unique(s_.seq))/numel(allSeq);
        end
        cnt.(key).(c) = [tot; fr];
    end
    cnt.(key).nFrames = numel(allSeq);  cnt.(key).name = rname;
end

% ---- 표: 촬영별·색별 임계값별 박스 수와 검출 프레임 비율 ----
vn = arrayfun(@(x) sprintf('p%.2f',x),T,'UniformOutput',false);
lab = {}; val = [];
for k = 1:size(runs,1)
    key = sprintf('r%d',k);
    for ci = 1:3
        c = colors{ci};
        lab{end+1,1} = sprintf('%s_%s_박스수',cnt.(key).name,cname.(c)); val(end+1,:) = cnt.(key).(c)(1,:); %#ok<AGROW>
        lab{end+1,1} = sprintf('%s_%s_검출프레임비율',cnt.(key).name,cname.(c)); val(end+1,:) = cnt.(key).(c)(2,:); %#ok<AGROW>
    end
end
tb = addvars(array2table(val,'VariableNames',vn), lab, 'Before',1, 'NewVariableNames','항목');
writetable(tb, fullfile(outDir,'신호등_임계값별_개수.csv'));
disp(tb);

% ---- 그림 C: 촬영별 3색 검출 프레임 비율, 박스 수 ----
fc = figure('Visible',vis,'Position',[0 0 1500 900]); theme(fc,'dark'); tiledlayout(2,2,'TileSpacing','compact');
lc = struct('red',[0.85 0.1 0.1],'green',[0.1 0.65 0.2],'yellow',[0.9 0.7 0]);
for k = 1:size(runs,1)
    key = sprintf('r%d',k);
    nexttile; hold on;
    for ci = 1:3, c = colors{ci}; plot(T,100*cnt.(key).(c)(2,:),'-o','LineWidth',1.5,'Color',lc.(c),'DisplayName',cname.(c)); end
    grid on; ylim([0 100]); xlabel('임계값'); ylabel('검출 프레임 % (전체)'); legend('Location','northeast'); title(sprintf('%s: 임계값별 검출 프레임 비율 (%d프레임)',cnt.(key).name,cnt.(key).nFrames));
end
for k = 1:size(runs,1)
    key = sprintf('r%d',k);
    nexttile; hold on;
    for ci = 1:3, c = colors{ci}; plot(T,max(cnt.(key).(c)(1,:),0.5),'-o','LineWidth',1.5,'Color',lc.(c),'DisplayName',cname.(c)); end
    set(gca,'YScale','log'); grid on; xlabel('임계값'); ylabel('박스 수 (log, 0 은 0.5 로 표시)'); legend('Location','northeast'); title(sprintf('%s: 임계값별 박스 수',cnt.(key).name));
end
exportgraphics(fc, fullfile(outDir,'신호등_C_임계값별_개수.png'),'Resolution',110);
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
