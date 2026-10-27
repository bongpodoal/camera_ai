% 3번째 줄: 객체(차·사람·신호등) 신뢰도 임계값 0.05~0.95(0.1 간격) 비교
% 입력: 노트북+카메라로 1분 30초 촬영한 실행 폴더 (raw_ai_candidates.csv, raw_rgb/, 있으면 detections.csv)
%   촬영 예: can_demo.py --model a_yolom_n --raw on --video on --mode debug --save-every 0 --depth-check on --log-files all ...
% 실행: runDir 를 지정한 뒤 object_threshold_compare   (예: runDir = '/path/to/run'; object_threshold_compare)
% 출력(runDir/matlab_object_threshold/): 01_샘플프레임.png, 02_임계값별_개수.png, object_threshold_counts.csv, object_boxes_nms005.csv
if ~exist('runDir','var'), runDir = uigetdir(pwd,'촬영 실행 폴더'); end
outDir = fullfile(runDir,'matlab_object_threshold'); if ~exist(outDir,'dir'), mkdir(outDir); end
if usejava('desktop'), vis = 'on'; else, vis = 'off'; end
T = 0.05:0.10:0.95;  n = numel(T);   % 비교할 임계값
IOU = 0.7;                           % 호스트 후처리와 같은 NMS 기준 (클래스별)
W = 512; H = 288;                    % 후보 박스 좌표(0~1)를 모델 입력 크기로 환산
names = {'person','car','tl_red','tl_green','tl_yellow'};
cmap = hsv2rgb([linspace(0,0.78,n)' ones(n,2)]);   % 0.05 빨강 ... 0.95 보라

cd_ = readtable(fullfile(runDir,'raw_ai_candidates.csv'));
seqs = unique(cd_.frame_seq);
fprintf('프레임 %d개, 후보 %d행\n', numel(seqs), height(cd_));

% ---- 프레임마다 점수 0.05 이상 후보를 클래스별 NMS ----
% 임계값 T 이상만 남긴 NMS 결과는 "0.05 로 NMS 한 뒤 점수 >= T 만 고른 것"과 같다 (탐욕 NMS 는 점수 순이라서)
rows = cell(numel(seqs),1);
trunc = 0;                           % 후보 상위 200개 제한 때문에 0.05 이상이 잘렸을 수 있는 프레임 수
for k = 1:numel(seqs)
    c = cd_(cd_.frame_seq==seqs(k),:);
    if height(c) >= 200 && min(c.max_score) > T(1), trunc = trunc + 1; end
    c = c(c.max_score >= T(1),:);
    if isempty(c), continue; end
    cls = cellfun(@(x) find(strcmp(names,x),1), c.max_cls) - 1;
    box = [c.x1 c.y1 c.x2 c.y2]; sc = c.max_score;
    keep = false(height(c),1);
    for q = unique(cls)'
        id = find(cls==q);
        keep(id(nms_greedy(box(id,:), sc(id), IOU))) = true;
    end
    rows{k} = [repmat(seqs(k),nnz(keep),1) cls(keep) sc(keep) box(keep,:)];
end
B = cell2mat(rows);
bx = array2table(B,'VariableNames',{'seq','cls','score','x1','y1','x2','y2'});
bx.name = names(bx.cls+1)';
writetable(bx, fullfile(outDir,'object_boxes_nms005.csv'));
if trunc > 0
    warning('%d 개 프레임은 후보가 상위 200개로 잘려 0.05 이상 일부가 없을 수 있음 (낮은 임계값 개수는 하한)', trunc);
end

% ---- 임계값별 개수 (클래스별 총 개수, 검출 있는 프레임 비율) ----
cnt = zeros(numel(names),n);  fr = zeros(1,n);
for j = 1:n
    s = bx(bx.score >= T(j),:);
    for q = 0:numel(names)-1, cnt(q+1,j) = sum(s.cls==q); end
    fr(j) = numel(unique(s.seq)) / numel(seqs);
end
tb = array2table(cnt,'VariableNames',arrayfun(@(x) sprintf('p%.2f',x),T,'UniformOutput',false),'RowNames',names);
tb.Properties.DimensionNames{1} = 'class';
tb2 = [array2table(fr,'VariableNames',tb.Properties.VariableNames,'RowNames',{'frame_fraction'})];
writetable([tb(:,:); tb2], fullfile(outDir,'object_threshold_counts.csv'), 'WriteRowNames', true);
disp(tb);

% ---- 그림 2: 임계값별 개수 ----
f2 = figure('Visible',vis,'Position',[0 0 1500 600]); tiledlayout(1,2,'TileSpacing','compact');
nexttile; hold on;
for q = 1:numel(names), plot(T,cnt(q,:),'-o','LineWidth',1.5); end
set(gca,'YScale','log'); grid on; xlabel('임계값'); ylabel('검출 박스 수 (log)'); legend(names,'Location','northeast'); title('임계값별 클래스 검출 수');
nexttile; plot(T,100*fr,'-o','LineWidth',1.5); grid on; ylim([0 100]); xlabel('임계값'); ylabel('검출 있는 프레임 %'); title('임계값별 검출 프레임 비율');
exportgraphics(f2, fullfile(outDir,'02_임계값별_개수.png'),'Resolution',110); if strcmp(vis,'off'), close(f2); end

% ---- 그림 1: 샘플 프레임 (박스 색 = 점수 구간, 무지개) ----
nb = arrayfun(@(s) sum(bx.seq==s & bx.score>=0.25), seqs);
[~,o] = sort(nb,'descend');  pick = seqs(o(unique(round(linspace(1,max(1,min(numel(o),60)),6)))));   % 검출 많은 프레임 중 6개
f1 = figure('Visible',vis,'Position',[0 0 1800 1100]); tl = tiledlayout(2,3,'TileSpacing','compact','Padding','compact');
for i = 1:numel(pick)
    s = pick(i);
    imf = fullfile(runDir,'raw_rgb',sprintf('%06d.png',s));
    nexttile; if isfile(imf), imshow(imread(imf)); else, imshow(zeros(H,W,3)); end
    hold on; m = bx(bx.seq==s,:);
    for r = 1:height(m)
        band = find(T <= m.score(r), 1, 'last');
        rectangle('Position',[m.x1(r)*W m.y1(r)*H (m.x2(r)-m.x1(r))*W (m.y2(r)-m.y1(r))*H],'EdgeColor',cmap(band,:),'LineWidth',1.8);
        text(m.x1(r)*W+2, m.y1(r)*H+9, sprintf('%s %.2f',m.name{r},m.score(r)),'Color',cmap(band,:),'FontSize',8,'FontWeight','bold','BackgroundColor',[0 0 0 0.45]);
    end
    title(sprintf('seq %d  (0.05 이상 %d개, 0.25 이상 %d개)',s,height(m),sum(m.score>=0.25)));
end
colormap(cmap); cb = colorbar; cb.Layout.Tile = 'east'; clim([0 n]); cb.Ticks = 0.5:1:n; cb.TickLabels = arrayfun(@(x) sprintf('%.2f',x),T,'UniformOutput',false);
title(tl,'객체 신뢰도 구간별 박스 색 (빨강 0.05 ... 보라 0.95, NMS IoU 0.7)');
exportgraphics(f1, fullfile(outDir,'01_샘플프레임.png'),'Resolution',100); if strcmp(vis,'off'), close(f1); end

% ---- 확인: 장비 기록 detections.csv(0.25 이상)와 개수 비교 ----
dfile = fullfile(runDir,'detections.csv');
if isfile(dfile)
    dt = readtable(dfile); fprintf('detections.csv %d건 / 이 스크립트 0.25 이상 %d건\n', height(dt), sum(bx.score>0.25));
end
if ~usejava('desktop') && ~exist('keepOpen','var'), exit(0); end

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
