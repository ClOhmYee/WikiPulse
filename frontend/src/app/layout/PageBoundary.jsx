import { Component } from "react";
import { EmptyState } from "../../components/ui/EmptyState";
export class PageBoundary extends Component {
  state = { error: false };
  static getDerivedStateFromError() {
    return { error: true };
  }
  render() {
    return this.state.error ? (
      <EmptyState
        title="화면을 불러오지 못했습니다"
        description="새로고침한 뒤 다시 시도해 주세요."
        action={
          <button
            className="wp-button"
            onClick={() => window.location.reload()}
          >
            새로고침
          </button>
        }
      />
    ) : (
      this.props.children
    );
  }
}

export function PageSkeleton() {
  return (
    <div
      className="wp-page wp-loading"
      role="status"
      aria-label="화면 불러오는 중"
    >
      <span className="wp-skeleton wp-skeleton--heading" />
      <span className="wp-skeleton wp-skeleton--line" />
      <span className="wp-skeleton wp-skeleton--panel" />
      <span className="wp-skeleton wp-skeleton--line" />
      <span className="sr-only">화면을 불러오고 있습니다.</span>
    </div>
  );
}
