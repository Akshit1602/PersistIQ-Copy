/**
 * Knowledge Archive — Manual, SOP, and Glossary content.
 * Real definitions of every statistical/technical term actually used
 * elsewhere in this platform, so a user can look up "what does SMD mean"
 * without leaving the app.
 */

export interface GlossaryTerm {
  term: string
  definition: string
  category: 'Matching & Balance' | 'Causal Inference' | 'Power & Statistics' | 'Store Operations' | 'Financial'
}

export const GLOSSARY_TERMS: GlossaryTerm[] = [
  { term: 'SMD (Standardized Mean Difference)', category: 'Matching & Balance',
    definition: 'Measures how different two groups are on a given attribute, in standard-deviation units. Below 0.10 is considered well-balanced — the test and control groups look statistically similar on that attribute before the experiment starts.' },
  { term: 'RMSPE (Root Mean Squared Prediction Error)', category: 'Matching & Balance',
    definition: 'Checks how closely a control group\u2019s historical sales curve tracks the test group\u2019s, before treatment. A low RMSPE means the two groups were already moving together — a prerequisite for trusting the causal estimate after treatment.' },
  { term: 'Placebo-in-Time (A/A Test)', category: 'Matching & Balance',
    definition: 'Simulates the experiment on historical data where nothing actually changed, to confirm the method doesn\u2019t falsely detect an effect. A high false-positive rate here means the test design itself is unreliable.' },
  { term: 'D_composite (Composite Distance Score)', category: 'Matching & Balance',
    definition: 'A weighted blend of DTW (curve shape), Mahalanobis distance (structural attributes), and spatial trade-area risk, used to find the best-matched control store for each test store.' },
  { term: 'DTW (Dynamic Time Warping)', category: 'Matching & Balance',
    definition: 'Matches stores by how similarly their sales move over time, even if one store\u2019s pattern is slightly shifted or stretched relative to the other.' },
  { term: 'G.O.L.D. Tier', category: 'Store Operations',
    definition: 'A quarterly operational-quality rating (Tier 1-3) used as a matching covariate. Pre-treatment G.O.L.D. tier is a confounder to match on; post-treatment G.O.L.D. tier is an outcome, never used for matching.' },
  { term: 'SDID (Synthetic Difference-in-Differences)', category: 'Causal Inference',
    definition: 'The default estimator for matched-pair pilots. Combines synthetic control weighting with difference-in-differences to isolate the true causal effect of the initiative.' },
  { term: "Staggered DiD (Callaway & Sant'Anna)", category: 'Causal Inference',
    definition: 'A difference-in-differences estimator built for multi-wave rollouts, where different stores go live at different times. Avoids bias that a single static DiD estimator would introduce with staggered adoption.' },
  { term: 'DML (Double / Debiased Machine Learning)', category: 'Causal Inference',
    definition: 'Uses machine learning to partial out the noise from other overlapping initiatives running in the same stores at the same time, without needing to drop any stores from the sample.' },
  { term: 'ITS (Interrupted Time Series)', category: 'Causal Inference',
    definition: 'Used for 100% fleet-wide rollouts where there\u2019s no control group left. Compares the post-launch trend to the pre-launch trend on the same stores.' },
  { term: "Simpson's Paradox", category: 'Causal Inference',
    definition: 'An "aggregate trap" where the overall result looks positive, but specific subgroups (e.g. rural small-format stores) are actually negative — hiding a problem that a fleet-wide rollout would inherit.' },
  { term: 'MDE (Minimum Detectable Effect)', category: 'Power & Statistics',
    definition: 'The smallest lift your current sample size can reliably detect. If your target lift is below the MDE, the experiment doesn\u2019t have enough stores to prove it worked even if it did.' },
  { term: 'CUPED', category: 'Power & Statistics',
    definition: 'Uses pre-experiment store performance as a covariate to shrink baseline variance, lowering the MDE without adding more stores to the test.' },
  { term: 'Alpha (\u03B1) / Significance Level', category: 'Power & Statistics',
    definition: 'The false-positive rate you\u2019re willing to accept. \u03B1 = 0.05 means a 5% chance of concluding there\u2019s an effect when there really isn\u2019t one.' },
  { term: 'Beta (\u03B2) / Statistical Power', category: 'Power & Statistics',
    definition: 'Power (1 - \u03B2) is the probability of detecting a real effect if one exists. 80% power means you\u2019ll catch a true effect 4 times out of 5.' },
  { term: 'mSPRT (mixture Sequential Probability Ratio Test)', category: 'Power & Statistics',
    definition: 'Lets you check results weekly while the test is running without inflating the false-positive rate — "always-valid" significance testing, unlike a fixed-horizon test.' },
  { term: 'BSTS (Bayesian Structural Time Series)', category: 'Power & Statistics',
    definition: 'A Bayesian model used to build credible intervals around in-flight results, providing anytime-valid confidence bounds as new weekly data arrives.' },
  { term: 'Futility Stopping', category: 'Power & Statistics',
    definition: 'Ends a test early if the probability of ever reaching the target effect has dropped too low — saves time and stores rather than running out a test that\u2019s already failed.' },
  { term: 'iROAS (incremental Return on Ad/Initiative Spend)', category: 'Financial',
    definition: 'Net incremental margin generated per dollar spent on the initiative. An iROAS of 3.0x means every $1 spent returned $3 in net margin.' },
  { term: 'Money Waterfall', category: 'Financial',
    definition: 'The bridge from gross incremental revenue down to final net margin: + cross-category halo, - cannibalization, - COGS, - operational cost. Shows exactly where the value came from and where it was spent.' },
  { term: 'Cross-Category Halo', category: 'Financial',
    definition: 'Extra sales in categories other than the one targeted by the initiative, caused indirectly by the same customer visit or store change.' },
  { term: 'Category Cannibalization', category: 'Financial',
    definition: 'Sales that moved from an adjacent category into the targeted one, rather than being genuinely new — a cost that must be subtracted from gross lift to get the real net effect.' },
  { term: 'OOS Rate (Out-of-Stock Rate)', category: 'Store Operations',
    definition: 'The percentage of time a SKU is unavailable on shelf. Tracked as a guardrail so an initiative can\u2019t "win" by starving inventory.' },
  { term: 'Volume Decile', category: 'Store Operations',
    definition: 'A 1-10 ranking of a store\u2019s baseline sales volume relative to the fleet, used to stratify matching so high- and low-volume stores aren\u2019t blended together.' },
]

export const GLOSSARY_CATEGORIES = [
  'Matching & Balance',
  'Causal Inference',
  'Power & Statistics',
  'Store Operations',
  'Financial',
] as const

export interface ManualSection {
  title: string
  content: string
}

export const MANUAL_SECTIONS: ManualSection[] = [
  { title: '1. Hypothesis', content: 'Define the initiative, its domain (Labor & Staffing, Store Format & Remodel, Merchandising & Assortment, or Pricing & Promo), and the exact dosage of intervention. Run the Shadow Initiative Check to confirm nothing undocumented is already affecting your baseline.' },
  { title: '2. Opportunity Sizing', content: 'Estimate the financial opportunity: expected lift, store-native halo and promotional costs, and the customer visit lag window. This produces the Target Expected Lift used later in Power Calculator.' },
  { title: '3. Rollout & Store Targeting', content: 'Define which stores receive the initiative (partial or fleet-wide), their characteristics, and the deployment wave schedule. Then run AI-Assisted Twin Matching (or another algorithm) to find a statistically valid control panel.' },
  { title: '4. Metrics', content: 'Select your Primary KPI, Secondary KPIs, and the mandatory Guardrail metric. Guardrails protect against unintended operational harm (e.g. checkout wait time, labor overtime) even if the primary KPI improves.' },
  { title: '5. Power Calculator', content: 'Confirm the matched cohort can actually detect your target lift. Apply CUPED to reduce variance if needed, then run the Pre-Flight A/A Test as a final sanity check before launch.' },
  { title: '6. Review & Concurrency', content: 'Check for other initiatives overlapping your test cohort, choose a conflict-resolution strategy, and sign off. This freezes the design with a cryptographic hash so it can\u2019t be silently altered after the fact.' },
  { title: 'Monitoring (in-flight)', content: 'Once launched, track POS feed health, use anytime-valid statistical bounds to safely check results weekly, and watch the driver-decomposed lift trajectory (Traffic \u00D7 CVR \u00D7 UPT \u00D7 AUR).' },
  { title: 'Causal Inference & ROI (readout)', content: 'After the flight concludes, run the Causal Inference Engine for the final lift estimate, Forecasting for multi-horizon projections, ROI Synthesis for the full P&L waterfall, and check for Simpson\u2019s Paradox before recommending a fleet-wide rollout.' },
]

export interface SopEntry {
  title: string
  steps: string[]
}

export const SOP_ENTRIES: SopEntry[] = [
  {
    title: 'Launching a New Store Experiment',
    steps: [
      'Complete Hypothesis, Sizing, Rollout, Metrics, and Power Calculator in order — each step\u2019s output feeds the next.',
      'Do not proceed past Power Calculator if the viability banner reads "UNDERPOWERED" — increase store count or enable CUPED first.',
      'Resolve any detected collisions in Review & Concurrency before signing off — Double/Debiased ML is the recommended default.',
      'Deploy only after the design hash has been generated — this is your immutable pre-registration record.',
    ],
  },
  {
    title: 'Responding to a Futility Alert',
    steps: [
      'If Monitoring shows a Futility Alert, do not restart or extend the test without documenting why.',
      'Check the Causal Inference Engine\u2019s current estimate before deciding to stop early.',
      'Log the decision (continue vs. stop) in the experiment notes for the Learnings Repository.',
    ],
  },
  {
    title: 'Interpreting a Simpson\u2019s Paradox Alert',
    steps: [
      'Never approve a fleet-wide rollout when a Simpson\u2019s Paradox alert is active without reviewing the flagged subgroup.',
      'Consider a targeted rollout excluding the negative subgroup rather than an all-or-nothing decision.',
      'Re-run the subgroup scan after any targeting changes to confirm the paradox has cleared.',
    ],
  },
]
