import { useEffect, useMemo, useState } from "react";
import { EmptyState } from "../../components/ui/EmptyState";
import {
  groupIssueSnapshots,
  parseJsonLines,
} from "../../data/historyPreview.js";
import HistoryPreviewExplore from "./HistoryPreviewExplore.jsx";
import HistoryPreviewDetail from "./HistoryPreviewDetail.jsx";
import "../explore/explore.css";
import "../../styles/details.css";
import "./issue-history-preview.css";

const DATA_ROOT = "/__local_issue_history_preview";

async function readLocalFile(name, signal) {
  const response = await globalThis.fetch(`${DATA_ROOT}/${name}.jsonl`, {
    signal,
  });
  if (!response.ok) throw new Error(`${name}.jsonl 추출본을 찾지 못했습니다.`);
  return parseJsonLines(await response.text());
}

export default function IssueHistoryPreviewPage({ pathname }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    Promise.all(
      ["metadata", "details", "reports"].map((name) =>
        readLocalFile(name, controller.signal),
      ),
    ).then(
      ([metadata, details, reports]) => setData({ metadata, details, reports }),
      (cause) => {
        if (!controller.signal.aborted) setError(cause.message);
      },
    );
    return () => controller.abort();
  }, []);

  const groups = useMemo(
    () => groupIssueSnapshots(data?.metadata || []),
    [data],
  );
  if (error)
    return (
      <div className="wp-page" role="alert">
        <h1>로컬 데이터를 불러오지 못했습니다</h1>
        <p>
          {error} `frontend/tmp/issue-history-preview/`의 추출본을 확인해
          주세요.
        </p>
      </div>
    );
  if (!data)
    return (
      <div className="wp-page" role="status">
        로컬 추출본을 읽는 중입니다.
      </div>
    );

  const selectedId = Number(pathname.split("/")[2]);
  if (selectedId) {
    const group = groups.find((item) => item.latestId === selectedId);
    return group ? (
      <HistoryPreviewDetail key={group.key} group={group} data={data} />
    ) : (
      <div className="wp-page">
        <EmptyState
          title="대표 문서를 찾을 수 없습니다"
          description="로컬 추출본에서 다시 선택해 주세요."
          action={
            <a className="wp-button" href="#/issue-history-preview">
              이슈 탐색으로
            </a>
          }
        />
      </div>
    );
  }
  return <HistoryPreviewExplore groups={groups} data={data} />;
}
