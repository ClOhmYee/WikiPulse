import { Network, Compass, Layers3, Bookmark, UserRound } from "lucide-react";
export const NAV_ITEMS = [
  { href: "#/pulse", label: "Pulse Map", icon: Network, key: "pulse" },
  { href: "#/issues", label: "이슈 탐색", icon: Compass, key: "issues" },
  { href: "#/stocks", label: "종목 탐색", icon: Layers3, key: "stocks" },
  { href: "#/saved", label: "보관함", icon: Bookmark, key: "saved" },
  { href: "#/mypage", label: "마이페이지", icon: UserRound, key: "mypage" },
];
