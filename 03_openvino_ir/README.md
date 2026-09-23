# ③ OpenVINO IR (.xml + .bin) — 인텔 중간 표현

IR 파일은 **받은 파일에 없다.** 만든 명령만 `buildinfo.json`에 남아 있다.
근거: `05_nnarchive/example/*/report.md` 의 ③ 절.

| 옵션 | 의미 | 기본값 예제 | 512x288 예제 |
|---|---|---|---|
| `--input images[1,3,H,W]{f32}` | 입력 크기 고정 | 384×512 | 288×512 |
| `--mean_values [0,0,0]` | 평균 빼기 없음 | ✓ | ✓ |
| `--scale_values [255,255,255]` | 입력 ÷255 를 **모델 안에** 넣음 | ✓ | ✓ |
| `--reverse_input_channels` | BGR → RGB 를 모델 안에 넣음 | ✓ | ✓ |
| `--compress_to_fp16` | 가중치 FP16 압축 | ✓ | — |
| Model Optimizer 버전 | | 2022.3.0-9052 | 2022.3.0-9213 |

전처리(÷255, 채널 순서)가 여기서 모델에 들어가므로 ⑤ `config.json`의 scale은 1.0이다.

이 PC에는 Myriad X를 지원하는 OpenVINO 2022가 없어 IR을 직접 만들 수 없다 (PyPI의 Python 3.12용은 2024.1 이상뿐).
