% load_dataset.m - yolo_to_matlab.py가 만든 CSV를 MATLAB 학습용 datastore로 읽는다.
%
% YOLO 데이터셋을 먼저 변환해 두어야 한다:
%     python3 training/yolo_to_matlab.py <데이터셋_루트>
%
% 반환하는 combine(imds, blds) 형태가 trainYOLOXObjectDetector 등이 바로 받는 입력이다.

function [dsTrain, dsVal, classNames] = load_dataset(csvDir)
arguments
    csvDir (1,1) string = "training/matlab"
end

[dsTrain, classNames] = loadSplit(fullfile(csvDir, "train.csv"));
valPath = fullfile(csvDir, "val.csv");
if isfile(valPath)
    dsVal = loadSplit(valPath);
else
    dsVal = [];
    warning("val.csv가 없습니다. 학습/검증 분할을 직접 해야 합니다.");
end

fprintf("클래스 %d개: %s\n", numel(classNames), strjoin(classNames, ", "));
end


function [ds, classNames] = loadSplit(csvPath)
% long-format CSV(박스 하나가 한 줄)를 이미지당 한 행인 테이블로 접는다.
T = readtable(csvPath, TextType="string");

classNames = unique(T.className);
files = unique(T.imageFilename, "stable");

% boxLabelDatastore는 클래스마다 컬럼 하나, 각 칸에 Mx4 행렬을 기대한다.
boxTable = table('Size', [numel(files), numel(classNames)], ...
                 'VariableTypes', repmat("cell", 1, numel(classNames)), ...
                 'VariableNames', cellstr(classNames));

for i = 1:numel(files)
    rowsForImage = T(T.imageFilename == files(i), :);
    for c = 1:numel(classNames)
        m = rowsForImage(rowsForImage.className == classNames(c), :);
        if isempty(m)
            boxTable{i, c} = {zeros(0, 4)};
        else
            boxTable{i, c} = {[m.x, m.y, m.width, m.height]};
        end
    end
end

imds = imageDatastore(files);
blds = boxLabelDatastore(boxTable);
ds = combine(imds, blds);
end
