/* AURIX Development Studio 프로젝트(예: MULTICAN_1_KIT_TC275_LK)의 Cpu0_Main.c 에서 core0_main() 만 이렇게 바꾼다.
 * can_time.c / can_time.h 를 프로젝트에 추가하고, 디버거의 Expressions 창에
 * g_lastFrame, g_lastDet, g_frameCount, g_detCount, g_syncCount 를 올려 두면 수신 결과가 실시간으로 보인다. */
#include "Ifx_Types.h"
#include "IfxCpu.h"
#include "IfxScuWdt.h"
#include "can_time.h"

extern IfxCpu_syncEvent g_cpuSyncEvent;

int core0_main(void)
{
    IfxCpu_enableInterrupts();
    IfxScuWdt_disableCpuWatchdog(IfxScuWdt_getCpuWatchdogPassword());
    IfxScuWdt_disableSafetyWatchdog(IfxScuWdt_getSafetyWatchdogPassword());
    IfxCpu_emitEvent(&g_cpuSyncEvent);
    IfxCpu_waitEvent(&g_cpuSyncEvent, 1);

    CanTime_init();
    while (1)
    {
        CanTime_step();
    }
    return 0;
}
