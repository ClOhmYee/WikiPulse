import { SearchX } from "lucide-react";
export function EmptyState({
  title = "검색 결과가 없습니다",
  description = "다른 검색어나 필터로 다시 탐색해 보세요.",
  action,
}) {
  return (
    <div className="wp-empty">
      <SearchX size={30} strokeWidth={1.3} />
      <h2>{title}</h2>
      <p>{description}</p>
      {action}
    </div>
  );
}
