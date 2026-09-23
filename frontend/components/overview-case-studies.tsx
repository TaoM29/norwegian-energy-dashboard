import { ArrowRight } from "lucide-react";
import styles from "./overview-insights.module.css";

export function OverviewCaseStudies() {
  return (
    <section className={styles.studies} aria-labelledby="case-studies-title">
      <div className={styles.sectionHeading}>
        <div>
          <h2 id="case-studies-title">Recorded findings</h2>
          <p>
            Recorded examples from the September 2026 validation snapshots,
            independent of current filters and synthetic fixtures.
          </p>
        </div>
        <a href="/methods">
          Methods & evidence <ArrowRight size={14} />
        </a>
      </div>
      <div className={styles.studyGrid}>
        <article className={styles.study}>
          <span className={styles.studyScope}>
            01 · NO1 · January–December 2025
          </span>
          <h3>Did Eastern Norway generate as much as it used?</h3>
          <div className={styles.finding}>
            19.72 vs 32.42 <small>TWh</small>
          </div>
          <p className={styles.limit}>
            Production / consumption · complete coverage.
          </p>
          <a href="/?area=NO1&start=2025-01-01&end=2025-12-31">
            Compare the year’s daily curves <ArrowRight size={15} />
          </a>
          <details>
            <summary>Evidence</summary>
            <p>
              Totals sum disjoint base groups over complete UTC days. The balance does not measure imports or exports.
            </p>
            <a href="https://github.com/TaoM29/norwegian-energy-dashboard/blob/main/docs/PHASE2_VALIDATION.md">
              Read the recorded numerical check
            </a>
          </details>
        </article>
        <article className={styles.study}>
          <span className={styles.studyScope}>
            02 · NO1–NO5 · 19 matched area-days
          </span>
          <h3>Can a model improve on repeating last week?</h3>
          <div className={styles.finding}>
            29.96% <small>lower MAE</small>
          </div>
          <p>
            Gradient boosting’s hourly demand error was 61,991.89 kWh, compared
            with 88,508.58 kWh for the weekly baseline.
          </p>
          <p className={styles.limit}>
            This small holdout does not establish broad superiority. Its nominal
            80% intervals covered only 61.6% of outcomes.
          </p>
          <a href="/forecasts?result=phase4-household-24h">
            Inspect errors and interval coverage <ArrowRight size={15} />
          </a>
          <details>
            <summary>Evidence</summary>
            <p>
              Models share the same successful origins. Ridge’s MAE was 1.71% worse than the baseline.
            </p>
            <a href="https://github.com/TaoM29/norwegian-energy-dashboard/blob/main/docs/PHASE4_VALIDATION.md">
              Read the frozen evaluation protocol
            </a>
          </details>
        </article>
        <article className={styles.study}>
          <span className={styles.studyScope}>
            03 · Bergen weather point · July 2024–June 2025
          </span>
          <h3>What can a snow-transport model tell us?</h3>
          <div className={styles.finding}>
            44.7 <small>tonnes per metre</small>
          </div>
          <p>
            The recorded Tabler calculation estimated snowfall-controlled
            transport at 60.3913° N, 5.3221° E and an indicative 2.13 m Wyoming
            fence height.
          </p>
          <p className={styles.limit}>
            A weather-point model illustration, not a site-specific engineering
            design. Location and model assumptions affect the result.
          </p>
          <a href="/regional?mode=snow&lat=60.3913&lon=5.3221&seasonStart=2024&seasonEnd=2024&T=3000&F=30000&theta=0.5&fenceType=Wyoming">
            Inspect the season and assumptions <ArrowRight size={15} />
          </a>
          <details>
            <summary>Evidence</summary>
            <p>
              The recorded run used 3,000 m transport distance, 30,000 m fetch
              and a relocation coefficient of 0.5.
            </p>
            <a href="https://github.com/TaoM29/norwegian-energy-dashboard/blob/main/docs/PHASE3_VALIDATION.md">
              Read the point-model validation
            </a>
          </details>
        </article>
      </div>
    </section>
  );
}
