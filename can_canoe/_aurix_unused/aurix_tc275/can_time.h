/* AURIX TC275 Lite Kit: OAK-D 검출 결과 CAN 수신 + 시간축 마스터
 *
 *  - FRAME_STATUS(0x300) 를 받는 "순간" STM 타이머를 읽어 ECHO(0x101) 로 돌려준다 → PC 가 이 값을 시간축으로 쓴다
 *  - 1초마다 SYNC(0x100) 에 현재 STM(µs) 을 실어 보낸다 → PC 가 자기 시계와의 관계(드리프트)를 구한다
 *  - DET_BOX(0x310) 는 받아서 마지막 값을 저장한다 (AURIX 쪽 "결과 보기": 디버거 변수·LED·UART 후크)
 *
 * 메시지 비트 배치는 ../oakd_aurix.dbc 와 같다 (인텔 방식 = 리틀 엔디언).
 * 주의: 이 보드가 없는 맥에서 작성했다. 아직 컴파일·실행해 보지 않았다 (iLLD 버전에 따라 이름이 다를 수 있음).
 */
#ifndef CAN_TIME_H
#define CAN_TIME_H

#include "Ifx_Types.h"

typedef struct
{
    uint16 seq;
    uint8  detCount;
    uint16 fpsX10;      /* fps × 10 */
    uint16 edgeMs;      /* 칩 안 지연 (PC 가 칩 시계끼리 뺀 값) */
    uint8  modelId;     /* 0=yolov6n 1=yolov8n 2=traffic_light 3=traffic_light_11n */
    uint8  rawOn;
    uint32 rxTimeUs;    /* ★ 시간축: 이 프레임을 받은 순간의 AURIX 시각 (µs, 71.6분마다 0 으로 돌아감) */
} CanTime_Frame;

typedef struct
{
    uint8  seqLo, index, label;
    uint8  confPct;     /* 신뢰도 % */
    uint16 cx, cy, w, h;/* 0..1000 = 0..1 정규화 */
} CanTime_Det;

extern volatile CanTime_Frame g_lastFrame;
extern volatile CanTime_Det   g_lastDet;
extern volatile uint32        g_frameCount, g_detCount, g_syncCount;

void CanTime_init(void);    /* CAN 노드·메시지 객체·인터럽트 설정. 인터럽트 허용 전에 1번 호출 */
void CanTime_step(void);    /* main 의 while(1) 안에서 계속 호출: 1초마다 SYNC 송신 */

#endif
