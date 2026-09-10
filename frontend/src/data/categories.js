// Issue topics are independent of stock sectors and industries.
export const issueCategories = [
  { id: "politics", label: "정치", color: "#d5a7bc" },
  { id: "world", label: "국제", color: "#edb778" },
  { id: "society", label: "사회", color: "#83bcb9" },
  { id: "economy", label: "경제", color: "#dbbd80" },
  { id: "technology", label: "기술", color: "#96ade7" },
  { id: "science", label: "과학", color: "#b09cd4" },
  { id: "culture", label: "문화", color: "#e5a1ac" },
  { id: "sports", label: "스포츠", color: "#9bc9ab" },
  { id: "environment", label: "환경", color: "#a6bd8c" },
  { id: "other", label: "기타", color: "#acbbc2" },
];
export const getIssueCategory = (id) =>
  issueCategories.find((item) => item.id === id) || issueCategories.at(-1);
