% depthtest 스크린샷 10장(촬영 순서 = 1m~10m)을 거리 2개씩 figure 5개에 위아래로 배치
if ~exist('srcDir','var'), srcDir = '/Volumes/T7/depthtest'; end
if ~exist('outDir','var'), outDir = fileparts(mfilename('fullpath')); end
d = dir(fullfile(srcDir,'Screenshot from *.png'));
d = d(~startsWith({d.name},'.'));
[~,i] = sort({d.name}); d = d(i);
assert(numel(d)==10, '스크린샷 10장이 필요합니다 (현재 %d장)', numel(d));
for k = 1:5
    m = [2*k-1 2*k];
    f = figure('Name',sprintf('Figure %d: %d~%dm',k,m(1),m(2)),'Position',[50 50 1150 800]);
    theme(f,'dark');
    tl = tiledlayout(f,2,1,'TileSpacing','compact','Padding','compact');
    title(tl,sprintf('Depth 거리 테스트 %d m ~ %d m',m(1),m(2)),'FontSize',14,'FontWeight','bold');
    for j = 1:2
        nexttile(tl);
        imshow(imread(fullfile(srcDir,d(m(j)).name)));
        title(sprintf('%d m',m(j)),'FontSize',12);
    end
    exportgraphics(f,fullfile(outDir,sprintf('depth거리_figure%d_%d-%dm.png',k,m(1),m(2))),'Resolution',150,'BackgroundColor',f.Color);
end
