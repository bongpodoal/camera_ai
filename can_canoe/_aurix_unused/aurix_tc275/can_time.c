#include "can_time.h"
#include "Ifx_Types.h"
#include "IfxCpu_Irq.h"
#include "IfxMultican_Can.h"
#include "IfxPort.h"
#include "IfxStm.h"

/* ---- 설정 (보드 문서와 다르면 여기만 고친다) ---- */
#define CAN_BAUDRATE        500000u
#define CAN_RX_PIN          IfxMultican_RXD0B_P20_7_IN      /* Lite Kit 의 CAN 트랜시버 연결 (확인 필요) */
#define CAN_TX_PIN          IfxMultican_TXD0_P20_8_OUT
#define LED_FRAME           &MODULE_P00, 5                  /* 프레임 받을 때마다 반전 (확인 필요) */
#define LED_DETECT          &MODULE_P00, 6                  /* 검출이 1개 이상이면 켬 */

#define ID_SYNC             0x100u
#define ID_ECHO             0x101u
#define ID_FRAME            0x300u
#define ID_DET              0x310u

#define ISR_PRIO_FRAME      10
#define ISR_PRIO_DET        11
#define SRC_FRAME           IfxMultican_SrcId_0
#define SRC_DET             IfxMultican_SrcId_1

volatile CanTime_Frame g_lastFrame;
volatile CanTime_Det   g_lastDet;
volatile uint32        g_frameCount, g_detCount, g_syncCount;

static IfxMultican_Can         g_can;
static IfxMultican_Can_Node    g_node;
static IfxMultican_Can_MsgObj  g_rxFrame, g_rxDet, g_txSync, g_txEcho;
static uint32                  g_ticksPerUs;
static uint32                  g_lastSyncUs;
static uint8                   g_syncCnt;

/* STM(64비트, 자유 실행) → µs. 32비트로 자르면 71.6분마다 0 으로 돌아가며 PC 가 이어 붙인다 */
static uint32 nowUs(void)
{
    return (uint32)(IfxStm_get(&MODULE_STM0) / g_ticksPerUs);
}

static void initMsgObj(IfxMultican_Can_MsgObj *obj, uint8 id, uint32 msgId, IfxMultican_Frame frame, boolean irq,
                       IfxMultican_SrcId src)
{
    IfxMultican_Can_MsgObjConfig cfg;
    IfxMultican_Can_MsgObj_initConfig(&cfg, &g_node);
    cfg.msgObjId              = id;
    cfg.messageId             = msgId;
    cfg.acceptanceMask        = 0x7FFFFFFFUL;               /* ID 가 정확히 같은 것만 */
    cfg.frame                 = frame;
    cfg.control.messageLen    = IfxMultican_DataLengthCode_8;
    cfg.control.extendedFrame = FALSE;                      /* 11비트 ID */
    cfg.control.matchingId    = TRUE;
    if (irq)
    {
        cfg.rxInterrupt.enabled = TRUE;
        cfg.rxInterrupt.srcId   = src;
    }
    IfxMultican_Can_MsgObj_init(obj, &cfg);
}

void CanTime_init(void)
{
    IfxMultican_Can_Config canCfg;
    IfxMultican_Can_initModuleConfig(&canCfg, &MODULE_CAN);
    canCfg.nodePointer[SRC_FRAME].priority     = ISR_PRIO_FRAME;
    canCfg.nodePointer[SRC_FRAME].typeOfService = IfxSrc_Tos_cpu0;
    canCfg.nodePointer[SRC_DET].priority       = ISR_PRIO_DET;
    canCfg.nodePointer[SRC_DET].typeOfService  = IfxSrc_Tos_cpu0;
    IfxMultican_Can_initModule(&g_can, &canCfg);

    IfxMultican_Can_NodeConfig nodeCfg;
    IfxMultican_Can_Node_initConfig(&nodeCfg, &g_can);
    nodeCfg.baudrate    = CAN_BAUDRATE;
    nodeCfg.nodeId      = IfxMultican_NodeId_0;
    nodeCfg.rxPin       = &CAN_RX_PIN;
    nodeCfg.rxPinMode   = IfxPort_InputMode_pullUp;
    nodeCfg.txPin       = &CAN_TX_PIN;
    nodeCfg.txPinMode   = IfxPort_OutputMode_pushPull;
    IfxMultican_Can_Node_init(&g_node, &nodeCfg);

    initMsgObj(&g_rxFrame, 0, ID_FRAME, IfxMultican_Frame_receive,  TRUE,  SRC_FRAME);
    initMsgObj(&g_rxDet,   1, ID_DET,   IfxMultican_Frame_receive,  TRUE,  SRC_DET);
    initMsgObj(&g_txSync,  2, ID_SYNC,  IfxMultican_Frame_transmit, FALSE, SRC_FRAME);
    initMsgObj(&g_txEcho,  3, ID_ECHO,  IfxMultican_Frame_transmit, FALSE, SRC_FRAME);

    g_ticksPerUs = (uint32)(IfxStm_getFrequency(&MODULE_STM0) / 1000000.0f);
    g_lastSyncUs = nowUs();

    IfxPort_setPinModeOutput(LED_FRAME, IfxPort_OutputMode_pushPull, IfxPort_OutputIdx_general);
    IfxPort_setPinModeOutput(LED_DETECT, IfxPort_OutputMode_pushPull, IfxPort_OutputIdx_general);
}

void CanTime_step(void)
{
    uint32 t = nowUs();
    if ((uint32)(t - g_lastSyncUs) >= 1000000u)             /* 래핑돼도 뺄셈은 맞다 */
    {
        IfxMultican_Message m;
        g_lastSyncUs += 1000000u;
        /* SYNC: SyncCnt = bit 0..7, TimeUs = bit 8..39 (리틀 엔디언) */
        IfxMultican_Message_init(&m, ID_SYNC, (uint32)g_syncCnt | (t << 8), t >> 24, IfxMultican_DataLengthCode_8);
        IfxMultican_Can_MsgObj_sendMessage(&g_txSync, &m);
        g_syncCnt++;
        g_syncCount++;
    }
}

/* ---- FRAME_STATUS 수신 인터럽트: 첫 줄에서 시각을 읽는 것이 핵심 (시간축 정확도가 여기서 결정됨) ---- */
IFX_INTERRUPT(CanTime_isrFrame, 0, ISR_PRIO_FRAME)
{
    uint32 t = nowUs();
    IfxMultican_Message m;
    IfxMultican_Message_init(&m, 0, 0, 0, IfxMultican_DataLengthCode_8);
    IfxMultican_Status st = IfxMultican_Can_MsgObj_readMessage(&g_rxFrame, &m);
    if (st != IfxMultican_Status_newData && st != IfxMultican_Status_newDataButOneLost)
    {
        return;
    }
    uint64 v = ((uint64)m.data[1] << 32) | m.data[0];
    g_lastFrame.seq      = (uint16)(v & 0xFFFF);
    g_lastFrame.detCount = (uint8)((v >> 16) & 0xFF);
    g_lastFrame.fpsX10   = (uint16)((v >> 24) & 0xFFFF);
    g_lastFrame.edgeMs   = (uint16)((v >> 40) & 0xFFF);
    g_lastFrame.modelId  = (uint8)((v >> 56) & 0xF);
    g_lastFrame.rawOn    = (uint8)((v >> 60) & 0x1);
    g_lastFrame.rxTimeUs = t;
    g_frameCount++;

    /* ECHO: Seq = bit 0..15, RxTimeUs = bit 16..47 */
    IfxMultican_Message e;
    IfxMultican_Message_init(&e, ID_ECHO, (uint32)g_lastFrame.seq | (t << 16), t >> 16, IfxMultican_DataLengthCode_8);
    IfxMultican_Can_MsgObj_sendMessage(&g_txEcho, &e);

    IfxPort_togglePin(LED_FRAME);
    IfxPort_setPinState(LED_DETECT, g_lastFrame.detCount ? IfxPort_State_high : IfxPort_State_low);
    /* 여기에 UART/디스플레이 출력을 붙이면 "AURIX 가 카메라 결과를 보여준다" 가 된다 (인터럽트 안에서는 짧게) */
}

IFX_INTERRUPT(CanTime_isrDet, 0, ISR_PRIO_DET)
{
    IfxMultican_Message m;
    IfxMultican_Message_init(&m, 0, 0, 0, IfxMultican_DataLengthCode_8);
    IfxMultican_Status st = IfxMultican_Can_MsgObj_readMessage(&g_rxDet, &m);
    if (st != IfxMultican_Status_newData && st != IfxMultican_Status_newDataButOneLost)
    {
        return;
    }
    uint64 v = ((uint64)m.data[1] << 32) | m.data[0];
    g_lastDet.seqLo   = (uint8)(v & 0xF);
    g_lastDet.index   = (uint8)((v >> 4) & 0xF);
    g_lastDet.label   = (uint8)((v >> 8) & 0x7F);
    g_lastDet.confPct = (uint8)((v >> 15) & 0x7F);
    g_lastDet.cx      = (uint16)((v >> 22) & 0x3FF);
    g_lastDet.cy      = (uint16)((v >> 32) & 0x3FF);
    g_lastDet.w       = (uint16)((v >> 42) & 0x3FF);
    g_lastDet.h       = (uint16)((v >> 52) & 0x3FF);
    g_detCount++;
}
