"use client";

export function StudyError({ message, missing, onRetry }: {
  message: string;
  missing: boolean;
  onRetry: () => void;
}) {
  return <div className="study-error" role={missing ? "status" : "alert"}>
    <div>
      <h3>{missing ? "This study hasn’t been published yet" : "Couldn’t load this study"}</h3>
      {!missing && <p>{message}</p>}
    </div>
    {missing ? <a href="/explore">Explore available data →</a> : <button type="button" onClick={onRetry}>Retry</button>}
  </div>;
}
