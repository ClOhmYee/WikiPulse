import { ChevronLeft, ChevronRight, RotateCcw } from "lucide-react";
import {
  closestSnapshot,
  kstTime,
  kstTimestamp,
  snapshotKey,
} from "../../data/pulse/time.js";

export default function PulseTimeline({
  snapshots,
  selected,
  latest,
  onSelect,
}) {
  const index = snapshots.findIndex(
    (item) => snapshotKey(item) === snapshotKey(selected),
  );
  const start = Date.parse(snapshots[0].snapshotTs);
  const end = Date.parse(snapshots.at(-1).snapshotTs);
  const at = Date.parse(selected.snapshotTs);
  return (
    <section className="pulse-timeline" aria-label="스냅샷 시간 탐색">
      <div className="pulse-timeline__heading">
        <div>
          <span className="wp-muted">선택 시점</span>
          <strong>{kstTimestamp(selected.snapshotTs)}</strong>
        </div>
        <button
          className="wp-text-button"
          onClick={() => onSelect(latest)}
          disabled={snapshotKey(selected) === snapshotKey(latest)}
        >
          <RotateCcw size={14} />
          최신으로 이동
        </button>
      </div>
      <div className="pulse-timeline__track">
        <button
          className="wp-icon-button"
          aria-label="이전 시점"
          disabled={index <= 0}
          onClick={() => onSelect(snapshots[index - 1])}
        >
          <ChevronLeft size={18} />
        </button>
        <div className="pulse-timeline__rail">
          <input
            type="range"
            aria-label="스냅샷 시각"
            aria-valuetext={kstTimestamp(selected.snapshotTs)}
            min={start}
            max={end === start ? start + 1 : end}
            step="1"
            value={at}
            disabled={snapshots.length < 2}
            onChange={(e) =>
              onSelect(closestSnapshot(snapshots, Number(e.target.value)))
            }
            onKeyDown={(e) => {
              const next =
                e.key === "ArrowRight" || e.key === "ArrowUp"
                  ? index + 1
                  : e.key === "ArrowLeft" || e.key === "ArrowDown"
                    ? index - 1
                    : e.key === "Home"
                      ? 0
                      : e.key === "End"
                        ? snapshots.length - 1
                        : null;
              if (next === null) return;
              e.preventDefault();
              onSelect(
                snapshots[Math.max(0, Math.min(snapshots.length - 1, next))],
              );
            }}
          />
          <div className="pulse-timeline__ticks" aria-hidden="true">
            {snapshots.map((item) => (
              <i
                key={snapshotKey(item)}
                style={{
                  left: `${end === start ? 50 : ((Date.parse(item.snapshotTs) - start) / (end - start)) * 100}%`,
                }}
              />
            ))}
          </div>
          <div className="pulse-timeline__labels">
            <span>{kstTime(snapshots[0].snapshotTs)}</span>
            <span>{kstTime(snapshots.at(-1).snapshotTs)}</span>
          </div>
        </div>
        <button
          className="wp-icon-button"
          aria-label="다음 시점"
          disabled={index >= snapshots.length - 1}
          onClick={() => onSelect(snapshots[index + 1])}
        >
          <ChevronRight size={18} />
        </button>
      </div>
      <p className="wp-muted wp-small">
        저장된 {snapshots.length}개 시점 · 간격은 실제 시간 차이를 나타냅니다.
      </p>
    </section>
  );
}
