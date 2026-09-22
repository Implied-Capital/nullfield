# Validating the measurement before the conclusion

Use the sections relevant to the claim. Work from inputs toward the final
decision, identifying which layers have evidence and which remain provisional.

## Data, availability, and selection

Define observation keys, units, time zones, event time, publication time, and
the time the information was actually available to the researcher. Audit
duplicates, revisions, stale observations, joins, and changes in data coverage.
For historical tests, reconstruct the eligible population as of each decision,
including discontinued entities and changes in identity or instrument terms
where relevant. A current universe is not automatically a historical census.

Separate eligibility information available at entry from the later ability to
measure an outcome. Missing outcomes and failed calculations may be associated
with large moves or difficult cases. Do not silently discard them, replace them
with zero, or remove extreme realized moves under a retrospective quality rule.
Verify suspected errors independently where possible. Otherwise report missing
coverage and how selection limits the estimand; use defensible bounds or
sensitivities rather than certifying the remaining sample as unbiased.

Keep a funnel of counts and exclusion reasons. Show whether failures cluster
by time, entity, data source, or outcome-related conditions. When filters change,
report both common-sample and coverage effects where useful. A larger reported
return after filtering may be a change of population rather than a better rule.

## Visual and numerical checks complement each other

Plot distributions, time histories, relationships, and conditional behavior
that can reveal errors hidden by averages. Examine both typical observations
and influential extremes. Show sample counts alongside binned relationships;
changes in composition can mimic a changing effect.

Use accounting identities, dimensional checks, hand-worked cases, and matched
implementations where available. Independently reconstruct critical values
from underlying inputs. Two scripts calling the same flawed helper do not
provide independent validation. Review consequential code before interpreting
an anomaly as grounds for a new research direction.

## Outcomes must represent the claimed economics

Describe whether the outcome is a feature change, a theoretical payoff,
a realized cash flow, or a marked position. For monetary results, specify
position units, inventory changes, financing, cash flows, costs, and the return
denominator. Reconcile constituent amounts with totals over the relevant path.

Normalization can introduce a hidden policy. Dividing each day's change by a
varying exposure is not necessarily the return of a position that could have
been held. Rebalancing to maintain an exposure requires trades and can change
both tails and costs. A proxy may remain useful for diagnosis while failing
to measure executable profits.

Validate an important economic claim using an independently constructed
cash-flow or payoff calculation early. Stress tests on a shared approximation
only test the channels that approximation contains. Record which effects are
omitted instead of treating a long robustness battery as proof of completeness.

## Prediction quality has several meanings

Check the quantity the downstream decision consumes. Rank ordering can help
selection without calibrating the magnitude used for sizing or utility.
Calibration can look satisfactory in aggregate while failing where a policy
actually acts. Evaluate that region, its support, and its stability, while
labeling subgroups discovered from the same outcomes as exploratory.

Distinguish mean payoff, median, win rate, dispersion, and loss severity.
An improved typical outcome can coexist with a worse expectation when rare
losses grow. Show the full distribution and economically relevant tails for
asymmetric payoffs. Those patterns raise alternative explanations, including
risk compensation; their shape alone does not identify the explanation.

Break results down by prespecified periods and exposures, and inspect which
observations drive the total. Removing influential events is a sensitivity
analysis, not permission to erase valid losses from the primary result. Patterns
found through these inspections can motivate new hypotheses. To claim they
generalize, evaluate them using evidence that did not shape their formulation
or selection. A convincing explanation of the inspected observations is not
independent validation.

## Executability and mark noise

Trace how a hypothetical decision becomes an actual fill. Include spread,
fees, latency, liquidity, partial or missing fills, financing, and market impact
when material. Use observed execution evidence where available and explicit
assumptions elsewhere. A theoretical or displayed price alone is not a fill.

Check whether signal construction and outcome measurement share a noisy mark.
Selection on an unusually favorable quote can create apparent reversal without
an attainable profit. Alternative marks, delayed decisions, and realized
execution comparisons can help distinguish explanations, but each changes
information or opportunity. Delayed entry losing performance can reflect real
signal decay as well as an artifact; do not treat it as a definitive detector.

Evaluate fills jointly with subsequent outcomes. High fill rates alone do not
exclude adverse selection. Report how execution cost assumptions interact with
selection, and separate uncertainty about costs from uncertainty about the
predictive relationship.

## Guard against overtrading

Evaluate the incremental decision to trade. A predictive signal can exist while
its expected benefit is too small or uncertain to justify another transaction.
Compare the proposed policy with retaining the current position, taking no
position, or trading less frequently where those alternatives are consistent
with the project's objective and risk limits. Include entry, exit, and any
intermediate adjustment costs over the full path.

Report turnover, gross benefit, cost drag, and net results together. Test
sensitivity to plausible execution costs and forecast errors. Separate gains
from better decisions from changes in exposure or risk. Do not respond to an
attractive gross backtest by assuming that more frequent reactions improve the
net result, or invent a finely tuned trading threshold from the same outcomes.
Additional activity needs evidence of incremental economic value or necessary
risk control; caution about turnover does not override required risk reductions.

## Dependence, uncertainty, and controls

Identify the independent economic units before choosing a standard error or
resampling method. Repeated observations, overlapping outcomes, shared entities,
and common shocks can make row count a poor measure of information. Preserve
relevant grouping and temporal structure. Paired comparisons should retain the
same draws for candidate and baseline.

Choose clustering, blocks, or an explicit dependence model from the data's
structure. Show sensitivity to reasonable choices when the conclusion depends
on them. Preserve elapsed calendar gaps when studying sparse episodes; treating
them as consecutive observations changes the dependence being estimated.
No single resampling recipe resolves every kind of dependence.

Report effect sizes and intervals with the number of independent groups and
the interpretation of the interval. Distinguish uncertainty conditional on a
fixed fitted model from uncertainty in the fitting and selection process.
Refit within evaluation or resampling when that process is part of the claim.

For a new detector or statistical procedure, use controls with known outcomes
to test false positives and sensitivity under plausible failure mechanisms.
A control must exercise the actual channel being evaluated. Detecting a
directly injected number does not establish sensitivity to every indirect
information channel. Report power against a meaningful effect where feasible.
Failure to reject, no observed errors, or a degenerate bootstrap interval does
not establish an exact absence of risk or effect.

## From a component to a portfolio

Validate inputs, features, individual outcomes, decision cohorts, and the full
calendar portfolio at the level needed for the claim. Results at one level do
not automatically establish the next. Attributing a full outcome to its entry
date can diagnose selection; it does not supply daily returns for a book with
overlapping positions.

Reconstruct the actual account with simultaneous holdings, shared capital,
financing, concentration limits, costs, and discrete trade sizes where relevant.
Combining return streams from separately feasible simulations need not produce
a jointly feasible account. Constraints change future selection and performance;
measure the combined policy under shared constraints before claiming feasibility.

Separate retrospective comparison normalizations from sizing rules that could
have run at the time. Scaling with a full-period maximum or future volatility
is descriptive unless replaced by a causal policy and evaluated again.
