// The one transport for run progress. Swapping SSE for another transport later touches only
// this file. The backend stream is progress-only: `progress` lines, then a single terminal
// `done`/`failed`/`cancelled` poke, after which the server closes the stream (so we close
// too); a dropped connection mid-run auto-reconnects and resumes via Last-Event-ID with no
// duplicated lines.

export interface RunEvent {
  event: "progress" | "done" | "failed" | "cancelled";
  data: string;
}

/** Stream a run's events to `onEvent`; returns a cancel function. Closes itself on terminal. */
export function streamRun(runId: string, onEvent: (e: RunEvent) => void): () => void {
  const source = new EventSource(`/api/runs/${encodeURIComponent(runId)}/events`);
  const handle = (event: RunEvent["event"]) => (ev: MessageEvent) => {
    onEvent({ event, data: ev.data });
    if (event !== "progress") source.close();
  };
  source.addEventListener("progress", handle("progress"));
  source.addEventListener("done", handle("done"));
  source.addEventListener("failed", handle("failed"));
  source.addEventListener("cancelled", handle("cancelled"));
  return () => source.close();
}
