export function wikipediaUrl(article) {
  const language = /^[a-z-]+wiki$/.test(article.wiki || "")
    ? article.wiki.slice(0, -4)
    : "en";
  return `https://${language}.wikipedia.org/wiki/${encodeURIComponent(article.title.replaceAll(" ", "_"))}`;
}
