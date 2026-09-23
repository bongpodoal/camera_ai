### 엣지 처리 용량 (throughput - NN 포화, 모델 A/B 비교용)

| 라벨 | 모델 | 입력 | FPS | 메시지 | 측정(s) | 시각 |
|---|---|---|---|---|---|---|
| yolo26n-stock | luxonis/yolo26-nano:coco-512x288 | 512x288 | 17.99 | 550 | 30.571 | 2026-09-15T07:55:25 |
| yolov10n-stock | luxonis/yolov10-nano:coco-512x288 | 512x288 | 16.92 | 500 | 29.558 | 2026-09-15T07:53:37 |
| yolov6n-stock | luxonis/yolov6-nano:r2-coco-512x288 | 512x288 | 40.2 | 1200 | 29.852 | 2026-09-15T07:51:47 |
| yolov8n-traffic-edge-r1 | blob:benchmark/models/yolov8n_traffic_288x512_openvino_2022.1_6shave.blob | 512x288 | 33.39 | 320 | 9.583 | 2026-09-15T10:34:42 |
| yolov8n-traffic-edge-r2 | blob:benchmark/models/yolov8n_traffic_288x512_openvino_2022.1_6shave.blob | 512x288 | 33.38 | 320 | 9.586 | 2026-09-15T10:35:18 |
| yolov8n-traffic-edge-r3 | blob:benchmark/models/yolov8n_traffic_288x512_openvino_2022.1_6shave.blob | 512x288 | 33.53 | 320 | 9.543 | 2026-09-15T10:35:55 |

### 엣지 실제 경로 (camera - 카메라→NN, 차량 체감 성능)

| 라벨 | 모델 | 입력 | FPS | 지연 평균(ms) | p95(ms) | 메시지 | 측정(s) | 시각 |
|---|---|---|---|---|---|---|---|---|
| yolo26n-stock | luxonis/yolo26-nano:coco-512x288 | 512x288 | 17.07 | 464.56 | 479.43 | 500 | 29.285 | 2026-09-15T07:56:19 |
| yolov10n-fps15 | luxonis/yolov10-nano:coco-512x288 | 512x288 | 15.0 | 83.11 | 83.31 | 450 | 29.991 | 2026-09-15T07:57:44 |
| yolov10n-stock | luxonis/yolov10-nano:coco-512x288 | 512x288 | 16.13 | 492.15 | 506.89 | 500 | 30.993 | 2026-09-15T07:54:31 |
| yolov6n-stock | luxonis/yolov6-nano:r2-coco-512x288 | 512x288 | 30.01 | 49.07 | 49.17 | 900 | 29.99 | 2026-09-15T07:52:42 |
| yolov8n-traffic-edge | blob:benchmark/models/yolov8n_traffic_288x512_openvino_2022.1_6shave.blob | 512x288 | 30.01 | 90.65 | 90.99 | 900 | 29.99 | 2026-09-15T10:32:16 |

### 호스트 CPU 기준선 (onnxruntime - 엣지 이득 판단용)

| 라벨 | 모델 | 입력 | FPS | 지연 평균(ms) | p95(ms) | 메시지 | 측정(s) | 시각 |
|---|---|---|---|---|---|---|---|---|
| yolov8n-traffic-host-288x512 | benchmark/models/yolov8n_traffic_288x512.onnx | 512x288 | 49.19 | 20.33 | 20.38 | 984 | 20.006 | 2026-09-15T08:53:37 |
| yolov8n-traffic-host-640 | benchmark/models/yolov8n_traffic_640.onnx | 640x640 | 17.98 | 55.62 | 55.82 | 360 | 20.023 | 2026-09-15T08:54:02 |
