export function CategoryTag({ category }) {
  const item = category;
  return (
    <span
      className="wp-category"
      style={{ "--category-color": item?.color || "#86c9c4" }}
    >
      <i />
      {item?.label || "미분류"}
    </span>
  );
}
