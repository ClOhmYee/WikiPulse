export function readRoute() {
  try {
    const raw = window.location.hash.slice(1) || "/";
    const separator = raw.indexOf("?");
    return separator < 0
      ? decodeURIComponent(raw)
      : `${decodeURIComponent(raw.slice(0, separator))}${raw.slice(separator)}`;
  } catch {
    return "/not-found";
  }
}
