% 4번째 줄: 객체 + depth 확인. 프레임별 객체명·신뢰도·거리(칩/호스트), depth 박스(ROI)를 RGB·깊이 영상 위에 띄운다.
% 입력: can_demo.py --model a_yolom_n --raw on --video on --mode debug --save-every 0 --depth-check on --log-files all 로 촬영한 실행 폴더
%   (raw_rgb/, images/NNNNNN_depth.png(uint16 mm), detections.csv, raw_spatial.csv(칩 X/Y/Z·ROI), depth_boxes.csv(호스트 Z))
% 실행: runDir 를 지정한 뒤 object_depth_check
% 출력(runDir/matlab_objdepth/): frames/NNNNNN.png, objdepth.mp4, objects_depth_merged.csv, 01_거리_요약.png
% 정답 거리가 있으면 runDir/ground_truth.csv (열: t_start_s,t_end_s,z_true_mm, 시각은 첫 프레임 기준 초) 를 두면 오차도 계산한다.
if ~exist('runDir','var'), runDir = uigetdir(pwd,'촬영 실행 폴더'); end
outDir = fullfile(runDir,'matlab_objdepth'); fdir = fullfile(outDir,'frames');
if ~exist(fdir,'dir'), mkdir(fdir); end
if usejava('desktop'), vis = 'on'; else, vis = 'off'; end
W = 512; H = 288; ZMAX = 5000;       % 깊이 그림 색 범위(mm)
names = {'person','car','tl_red','tl_green','tl_yellow'};
bcol = [0 0.8 1; 1 0.5 0; 1 0 0; 0 0.9 0; 1 0.9 0];

det = readtable(fullfile(runDir,'detections.csv'));
rs  = readtable(fullfile(runDir,'raw_spatial.csv'));
db  = readtable(fullfile(runDir,'depth_boxes.csv'));
ds  = readtable(fullfile(runDir,'depth_stats.csv'));
fr  = readtable(fullfile(runDir,'frames.csv'));
% 같은 프레임 안 j 번째 검출 = 인덱스 j-1 (can_demo 가 신뢰도 순으로 보냄)
det.index = zeros(height(det),1);
for s = unique(det.seq)', id = find(det.seq==s); det.index(id) = (0:numel(id)-1)'; end
det = removevars(det, intersect(det.Properties.VariableNames,{'x_mm','y_mm','z_mm','roi_x','roi_y','roi_w','roi_h'}));   % 거리 열은 raw_spatial 에서 가져온다
rs.seq = rs.frame_seq;
M = outerjoin(det, rs(:,{'seq','index','x_mm','y_mm','z_mm','roi_x','roi_y','roi_w','roi_h'}), 'Keys',{'seq','index'}, 'Type','left', 'MergeKeys',true);
M = outerjoin(M, db(:,{'seq','index','z_host_mm','valid_ratio_in_box'}), 'Keys',{'seq','index'}, 'Type','left', 'MergeKeys',true);
M = sortrows(M,{'seq','index'});
t0 = ds.t_recv_s(1);
tmap = containers.Map(ds.seq, ds.t_recv_s - t0);
M.t_s = arrayfun(@(s) tmap_get(tmap,s), M.seq);
M.name = names(M.label+1)';
M.z_diff_mm = M.z_mm - M.z_host_mm;
writetable(M(:,{'seq','t_s','name','confidence','xmin','ymin','xmax','ymax','x_mm','y_mm','z_mm','z_host_mm','z_diff_mm','valid_ratio_in_box','roi_x','roi_y','roi_w','roi_h'}), fullfile(outDir,'objects_depth_merged.csv'));
fprintf('검출 %d건, 프레임 %d개\n', height(M), numel(unique(M.seq)));

% ---- 프레임별 그림 + 영상 ----
seqs = sort(ds.seq)';
vw = VideoWriter(fullfile(outDir,'objdepth.mp4'),'MPEG-4'); vw.FrameRate = 5; open(vw);
fh = figure('Visible',vis,'Position',[0 0 1500 460],'Color','w');
for s = seqs
    rgbf = fullfile(runDir,'raw_rgb',sprintf('%06d.png',s)); dpf = fullfile(runDir,'images',sprintf('%06d_depth.png',s));
    if ~isfile(rgbf) || ~isfile(dpf), continue; end
    rgb = imread(rgbf); dp = double(imread(dpf)); dm = dp; dm(dm==0) = NaN;
    clf(fh); tiledlayout(fh,1,2,'TileSpacing','compact','Padding','compact');
    ax1 = nexttile; imshow(rgb); hold on; ax2 = nexttile; imagesc(dm,'AlphaData',~isnan(dm)); axis image off; clim([0 ZMAX]); colormap(ax2,turbo); colorbar(ax2); hold on;
    m = M(M.seq==s,:);
    for r = 1:height(m)
        c = bcol(m.label(r)+1,:);
        x = m.xmin(r)*W; y = m.ymin(r)*H; w = (m.xmax(r)-m.xmin(r))*W; h = (m.ymax(r)-m.ymin(r))*H;
        rectangle(ax1,'Position',[x y w h],'EdgeColor',c,'LineWidth',2);
        rectangle(ax2,'Position',[x y w h],'EdgeColor',c,'LineWidth',1.2);
        if ~isnan(m.roi_w(r)), rectangle(ax2,'Position',[m.roi_x(r) m.roi_y(r) m.roi_w(r) m.roi_h(r)],'EdgeColor','w','LineWidth',2,'LineStyle','--'); end   % depth 박스(칩이 거리를 잰 영역)
        zt = '-'; if ~isnan(m.z_mm(r)), zt = sprintf('%d',round(m.z_mm(r))); end
        zh = '-'; if ~isnan(m.z_host_mm(r)), zh = sprintf('%d',round(m.z_host_mm(r))); end
        text(ax1,x+2,y+10,sprintf('%s %.2f  z=%s mm',m.name{r},m.confidence(r),zt),'Color',c,'FontSize',10,'FontWeight','bold','BackgroundColor',[0 0 0 0.5]);
        text(ax2,x+2,y+h+10,sprintf('칩 %s / 호스트 %s mm',zt,zh),'Color','w','FontSize',9,'BackgroundColor',[0 0 0 0.5]);
    end
    title(ax1,sprintf('seq %d  t=%.1fs  RGB + 객체명', s, tmap_get(tmap,s))); title(ax2,sprintf('Depth(mm) 유효 %.1f%%  흰 점선=depth 박스(ROI)', 100*mean(dp(:)>0)));
    exportgraphics(fh, fullfile(fdir,sprintf('%06d.png',s)),'Resolution',90);
    writeVideo(vw, imresize(imread(fullfile(fdir,sprintf('%06d.png',s))), [460 1500]));
end
close(vw); if strcmp(vis,'off'), close(fh); end

% ---- 거리 요약 그림 ----
f1 = figure('Visible',vis,'Position',[0 0 1700 500]); tiledlayout(1,3,'TileSpacing','compact');
nexttile; hold on; hl = []; ll = {};
for q = 0:4, k = M.label==q; if any(k), hl(end+1) = plot(M.t_s(k),M.z_mm(k),'.','MarkerSize',14,'Color',bcol(q+1,:)); ll{end+1} = names{q+1}; end, end %#ok<AGROW>
grid on; xlabel('시간 s'); ylabel('칩 z mm'); title('객체 거리 (칩) 시간 변화'); if ~isempty(hl), legend(hl,ll,'Location','best'); end
nexttile; k = ~isnan(M.z_mm) & ~isnan(M.z_host_mm); scatter(M.z_host_mm(k),M.z_mm(k),20,'filled'); hold on; mx = max([M.z_mm(k);1]); plot([0 mx],[0 mx],'k--'); grid on; axis equal;
xlabel('호스트 z mm'); ylabel('칩 z mm'); title(sprintf('칩 vs 호스트 (차이 중앙값 %.1f mm, n=%d)',median(abs(M.z_diff_mm(k))),nnz(k)));
nexttile; histogram(100*M.valid_ratio_in_box,0:10:100); grid on; xlabel('박스 안 유효 깊이 %'); ylabel('검출 수'); title('depth 박스 유효 비율');
exportgraphics(f1, fullfile(outDir,'01_거리_요약.png'),'Resolution',110); if strcmp(vis,'off'), close(f1); end

% ---- 정답 거리가 있으면 오차 ----
gtf = fullfile(runDir,'ground_truth.csv');
if isfile(gtf)
    g = readtable(gtf); err = [];
    for i = 1:height(g)
        k = M.t_s >= g.t_start_s(i) & M.t_s <= g.t_end_s(i) & ~isnan(M.z_mm);
        if any(k), err(end+1,:) = [g.z_true_mm(i), median(M.z_mm(k)), median(M.z_mm(k))-g.z_true_mm(i), nnz(k)]; end %#ok<AGROW>
    end
    te = array2table(err,'VariableNames',{'z_true_mm','z_chip_median_mm','error_mm','n'}); te.error_pct = 100*te.error_mm./te.z_true_mm;
    writetable(te, fullfile(outDir,'ground_truth_error.csv')); disp(te);
end
if ~usejava('desktop') && ~exist('keepOpen','var'), exit(0); end

function v = tmap_get(m, s)
if isKey(m, s), v = m(s); else, v = NaN; end
end
