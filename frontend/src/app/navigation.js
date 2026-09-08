import { Network, Compass, Layers3, Bookmark } from "lucide-react";
export const NAV_ITEMS = [
  { href: "#/pulse", label: "Pulse Map", icon: Network, key: "pulse" },
  { href: "#/explore", label: "사건 탐색", icon: Compass, key: "explore" },
  { href: "#/stocks", label: "종목 탐색", icon: Layers3, key: "stocks" },
  { href: "#/saved", label: "보관함", icon: Bookmark, key: "saved" },
];
