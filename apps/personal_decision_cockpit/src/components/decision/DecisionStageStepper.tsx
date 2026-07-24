import { IconCheckCircle, IconChevronRight } from '../icons';
import { TRANSITION_CHAIN } from '../../api/orchestration';

/**
 * 决策会话阶段步骤条（spec §8 DecisionStageStepper）：
 * confirm → generate → publish → decide → preregister → action_start
 * → action_complete → observe → calibrate，当前阶段高亮。
 * 颜色一律配文字 + 图标（spec §9.2）。
 */

export interface DecisionStageStepperProps {
  /** 当前待执行的 transition（如 generate）；null = 链已全部走完 */
  currentTransition: string | null;
}

export function DecisionStageStepper({ currentTransition }: DecisionStageStepperProps) {
  const currentIndex = currentTransition
    ? TRANSITION_CHAIN.findIndex((meta) => meta.key === currentTransition)
    : -1;

  return (
    <ol className="flex flex-wrap items-center gap-y-2" aria-label="决策会话阶段">
      {TRANSITION_CHAIN.map((meta, index) => {
        const done = currentIndex === -1 || index < currentIndex;
        const current = index === currentIndex;
        return (
          <li key={meta.key} className="flex items-center">
            {index > 0 ? <IconChevronRight className="mx-1 h-3.5 w-3.5 text-muted" /> : null}
            <span
              className={`badge ${
                current
                  ? 'border-primary bg-primary-soft font-medium text-primary'
                  : done
                    ? 'border-verified bg-verified-soft text-verified'
                    : 'border-line bg-panel text-muted'
              }`}
              aria-current={current ? 'step' : undefined}
            >
              {done ? <IconCheckCircle className="h-3.5 w-3.5" /> : null}
              {meta.label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
