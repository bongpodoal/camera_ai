% step1_check_toolchain.m - 학습 전에 툴체인을 먼저 검증한다.
%
% 이 스크립트는 학습을 하지 않는다. 몇 분 안에 끝나며, 목적은 하나다:
% "MATLAB에서 만든 검출기를 ONNX로 내보낼 수 있는가?"
%
% 이게 안 되면 뒤의 학습은 전부 헛수고가 된다. YOLOX 검출기의 Network 속성 접근은
% MathWorks 문서에 YOLOv2 기준으로만 나와 있어 YOLOX에서 되는지 확인이 필요하다.
%
% 필요: Deep Learning Toolbox, Computer Vision Toolbox,
%       Deep Learning Toolbox Converter for ONNX Model Format

fprintf("=== 1. 툴박스 확인 ===\n");
need = ["Deep Learning Toolbox", "Computer Vision Toolbox"];
v = ver;
have = string({v.Name});
for t = need
    if any(have == t)
        fprintf("  OK   %s\n", t);
    else
        fprintf("  없음 %s  <- 설치 필요\n", t);
    end
end
if isempty(which("exportONNXNetwork"))
    fprintf("  없음 exportONNXNetwork  <- ONNX Converter 지원 패키지 설치 필요\n");
else
    fprintf("  OK   exportONNXNetwork\n");
end

fprintf("\n=== 2. 검출기 생성 (학습 없음) ===\n");
% 엣지 기준선과 같은 입력 크기. MATLAB은 [height width channels] 순서다.
inputSize = [288 512 3];
classes   = "traffic light";          % 비교 기능을 신호등 검출로 한정

detector = yoloxObjectDetector("small-coco", classes, InputSize=inputSize);
fprintf("  생성됨: InputSize=[%d %d %d], 클래스=%s\n", ...
        detector.InputSize, strjoin(string(detector.ClassNames), ", "));

fprintf("\n=== 3. Network 속성 접근 (급소) ===\n");
net = [];
try
    net = detector.Network;
    fprintf("  OK   detector.Network 접근됨 (%s)\n", class(net));
catch ME
    fprintf("  실패 detector.Network: %s\n", ME.message);
    fprintf("  -> 아래 속성 목록에서 신경망을 담은 항목을 찾아야 한다:\n");
    disp(properties(detector));
end

fprintf("\n=== 4. ONNX 내보내기 ===\n");
if isempty(net)
    fprintf("  건너뜀 (3단계 실패)\n");
else
    outFile = "yolox_export_test.onnx";
    try
        exportONNXNetwork(net, outFile);
        d = dir(outFile);
        fprintf("  OK   %s (%.1f MB)\n", outFile, d.bytes/1e6);
        fprintf("\n  다음 단계: 이 ONNX를 blobconverter로 변환해 실제로 컴파일되는지 확인할 것.\n");
        fprintf("  (OpenVINO의 Myriad X 플러그인은 지원 연산자가 제한적이라 여기서 막힐 수 있다)\n");
    catch ME
        fprintf("  실패: %s\n", ME.message);
        fprintf("  -> 대안: trainYOLOv4ObjectDetector 또는 YOLOv2. 둘은 ONNX 내보내기가\n");
        fprintf("     문서화돼 있다. 정확도는 YOLOX보다 낮지만 경로가 확실하다.\n");
    end
end

fprintf("\n=== 검증 끝 ===\n");
fprintf("4단계까지 OK면 step2_train.m으로 진행. 막혔으면 거기서 경로를 바꿔야 한다.\n");
