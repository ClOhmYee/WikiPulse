export function wikipediaUrl(article) {
  return `https://en.wikipedia.org/wiki/${encodeURIComponent(article.title.replaceAll(" ", "_"))}`;
}
