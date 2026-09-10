import { ArrowRight } from "lucide-react";
import { wikipediaUrl } from "../../lib/wiki";
export function ArticleNetwork({ articles = [], selectedId, onSelect }) {
  return (
    <div className="wp-article-network">
      <svg
        viewBox="0 0 560 230"
        role="img"
        aria-label="클러스터에 포함된 문서 구성"
      >
        {articles.slice(1).map((article, i) => {
          const angle = (i / Math.max(1, articles.length - 1)) * Math.PI * 2;
          return (
            <line
              key={article.id}
              x1="280"
              y1="110"
              x2={280 + Math.cos(angle) * 170}
              y2={110 + Math.sin(angle) * 78}
              stroke="#416565"
              strokeWidth="1"
            />
          );
        })}
        {articles.map((article, i) => {
          const angle =
            ((i - 1) / Math.max(1, articles.length - 1)) * Math.PI * 2;
          const x = i === 0 ? 280 : 280 + Math.cos(angle) * 170;
          const y = i === 0 ? 110 : 110 + Math.sin(angle) * 78;
          return (
            <g key={article.id}>
              <circle
                cx={x}
                cy={y}
                r={i === 0 ? 19 : 8}
                fill={selectedId === article.id ? "#dbb057" : "#86c9c4"}
                fillOpacity={i === 0 ? ".2" : ".8"}
                stroke="#86c9c4"
              />
              <text
                x={x}
                y={y + (i === 0 ? 39 : 24)}
                textAnchor="middle"
                fill="#dce7e8"
                fontSize="12"
              >
                {article.name}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="wp-article-network__links">
        {articles.map((article) =>
          onSelect ? (
            <button
              key={article.id}
              className="wp-chip"
              data-active={selectedId === article.id}
              onClick={() => onSelect(article.id)}
            >
              {article.name}
              <ArrowRight size={12} />
            </button>
          ) : (
            <a
              key={article.id}
              className="wp-chip"
              href={wikipediaUrl(article)}
              target="_blank"
              rel="noreferrer"
              aria-label={`${article.name} 위키백과 원문 (새 탭)`}
            >
              {article.name}
              <ArrowRight size={12} />
            </a>
          ),
        )}
      </div>
      <p className="wp-muted wp-small">
        클러스터에 포함된 문서 구성입니다. 선은 소속을 표현하며, 문서 쌍의 관계
        근거는 펄스맵에서 확인하세요.
      </p>
    </div>
  );
}
