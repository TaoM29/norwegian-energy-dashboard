"use client";

export function StudyError({ message, missing, onRetry }: {
  message: string;
  missing: boolean;
  onRetry: () => void;
}) {
  return <div className="study-error" role={missing ? "status" : "alert"}>
    <div>
      <h3>{missing ? "This study hasn’t been published yet" : "Couldn’t load this study"}</h3>
      <p>{missing ? "The published dataset does not include these results. You can still explore energy and weather observations." : message}</p>
    </div>
    {missing ? <a href="/explore">Explore available data →</a> : <button type="button" onClick={onRetry}>Retry</button>}
  </div>;
}
