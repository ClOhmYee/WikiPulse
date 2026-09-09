export function normalizeRoute(raw = "/") {
  try {
    const separator = raw.indexOf("?");
    const query = separator < 0 ? "" : raw.slice(separator);
    let pathname = decodeURIComponent(
      separator < 0 ? raw : raw.slice(0, separator),
    );
    pathname = pathname.replace(/\/+$/, "") || "/";
    pathname = pathname.replace(
      /^\/stocks\/([^/]+)$/,
      (_, ticker) => `/stocks/${ticker.toUpperCase()}`,
    );
    return `${pathname}${query}`;
  } catch {
    return "/not-found";
  }
}

export function readRoute() {
  const raw = window.location.hash.slice(1) || "/";
  const route = normalizeRoute(raw);
  // Preserve query bytes and replace, rather than add, a history entry.
  const separator = route.indexOf("?");
  const pathname = separator < 0 ? route : route.slice(0, separator);
  const query = separator < 0 ? "" : route.slice(separator);
  const canonical =
    pathname.split("/").map(encodeURIComponent).join("/") + query;
  if (window.location.hash && raw !== canonical) {
    window.history.replaceState(window.history.state, "", `#${canonical}`);
  }
  return route;
}
