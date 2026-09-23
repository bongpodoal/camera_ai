% step2_train.m - 신호등 검출 YOLOX 학습 + 평가 + ONNX 내보내기.
%
% step1_check_toolchain.m이 통과한 뒤에만 실행할 것.
%
% 사전 준비 (리눅스 셸에서):
%     python3 training/check_dataset.py   <데이터셋_루트>
%     python3 training/yolo_to_matlab.py  <데이터셋_루트>
%
% 산출물:
%     traffic_yolox.mat    학습된 검출기
%     traffic_yolox.onnx   엣지 벤치마크용 (blobconverter 입력)

%% 설정 -----------------------------------------------------------------
csvDir    = "training/matlab";
inputSize = [288 512 3];        % 엣지 기준선과 동일 (MATLAB은 [h w c] 순서)
baseModel = "small-coco";       % 500장 규모에선 사전학습 필수. nano/tiny도 후보
classes   = "traffic light";    % 비교 기능을 신호등 검출로 한정

%% 데이터 ---------------------------------------------------------------
[dsTrain, dsVal] = load_dataset(csvDir);

%% 검출기 ---------------------------------------------------------------
detector = yoloxObjectDetector(baseModel, classes, InputSize=inputSize);

%% 학습 옵션 -------------------------------------------------------------
% 데이터가 500장 규모라 backbone을 얼면 과적합이 줄고 학습도 빨라진다.
% 정확도가 모자라면 FreezeSubNetwork="none"으로 풀어서 다시 돌릴 것.
options = trainingOptions("sgdm", ...
    InitialLearnRate   = 0.001, ...
    MiniBatchSize      = 16, ...
    MaxEpochs          = 50, ...
    ValidationData     = dsVal, ...
    ValidationFrequency= 20, ...
    Metrics            = mAPObjectDetectionMetric(Name="mAP50"), ...
    ObjectiveMetricName= "mAP50", ...
    OutputNetwork      = "best-validation", ...
    Shuffle            = "every-epoch", ...
    Plots              = "training-progress", ...
    Verbose            = true);

[detector, info] = trainYOLOXObjectDetector(dsTrain, detector, options, ...
                                            FreezeSubNetwork="backbone");

save("traffic_yolox.mat", "detector", "info");
fprintf("\n학습 완료 -> traffic_yolox.mat\n");

%% 정확도 평가 (엣지 비교 문서의 정확도 축) --------------------------------
fprintf("\n=== 검증셋 평가 ===\n");
results = detect(detector, dsVal);
metrics = evaluateObjectDetection(results, dsVal);
fprintf("  mAP@0.5     : %.4f\n", metrics.DatasetMetrics.mAP);
fprintf("  이 값을 기준선 문서의 정확도 축에 기록할 것.\n");

%% ONNX 내보내기 ---------------------------------------------------------
% 주의: 검출기 객체의 후처리(디코딩/NMS)는 ONNX에 담기지 않는다. 원시 head 텐서만
% 나가는데, 이건 엣지 기준선의 "호스트 디코딩" 경로와 조건이 같으므로 비교에 맞다.
% -> 기준선 33.38 FPS와 맞대면 된다 (칩 위 디코딩 31.79가 아니라).
onnxFile = "traffic_yolox.onnx";
exportONNXNetwork(detector.Network, onnxFile);
fprintf("\nONNX 내보내기 완료 -> %s\n", onnxFile);
fprintf("다음: 이 파일을 리눅스 셸의 blobconverter로 넘길 것.\n");
