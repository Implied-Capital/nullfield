# Designing a useful experiment

Use this guidance when a study needs an empirical plan, when a result suggests
a new variant, or when deciding whether more work can change the decision.
The user supplies the objective and constraints; choose methods in proportion
to the uncertainty and consequences.

## Specify the decision before the machinery

Write what the experiment could change: a belief, a measurement, a candidate
selection, or an implementation decision. State the population, horizon, unit
of analysis, outcome, and comparison. Name the smallest improvement or failure
that matters for that decision, where a defensible value is available. Do not
invent economic tolerances or risk limits for the user.

Distinguish a diagnostic question from a performance claim. A small pilot can
expose an accounting error or a missing data channel without estimating a
strategy's expected return. Label a pilot's selection and limitations so its
results are not later reused as population estimates.

Start with a simple baseline that represents the existing decision or the
absence of the proposed ingredient. Compare incremental value against that
baseline, including its costs and exposures. A complicated candidate beating
an artificially weak benchmark answers little.

## Make explanations compete

For a proposed relationship, record the mechanism, observable implications,
and plausible alternatives. Alternatives can include measurement noise,
selection, ordinary risk exposure, implementation error, or a genuine change
in the environment. Choose a test whose possible outcomes separate them.

Use rough arithmetic to reject impossible magnitudes, check units, and decide
what deserves computation. Replace approximations with the relevant accounting
before using them to support an economic claim. Inspect a few complete cases
early instead of investing in a large pipeline around an unverified label.

When a result conflicts with the hypothesis, trace the evidence from raw input
through the decision and outcome. Fix a demonstrated defect, then rerun the
affected comparisons. If the calculation is correct, revise the explanation.
Do not keep modifying code until it produces the expected sign.

## Keep comparisons interpretable

Freeze data preparation, sample eligibility, outcome construction, and baseline
configuration while testing a particular ingredient. Use matched observations
and paired comparisons when possible. Record any changes in coverage,
deployment, costs, or constraints alongside the metric difference.

Separate an experiment that holds selection or exposure constant to isolate
a mechanism from a full policy comparison in which those quantities may
legitimately change. Both can be useful. Label which question each answers;
holding every downstream consequence fixed can also remove the effect of
interest. If several components change together, attribute the result to the
package until an ablation distinguishes their contributions.

## Treat evaluation exposure as durable history

Before looking at evaluation results, record candidate variants, the primary
comparison, metrics, exclusions, uncertainty method, and stopping or escalation
rule. Freeze the plan and the executable configuration. Record technical repairs
and substantive amendments separately, including what results had been seen.

Track exposure to evaluation data across studies, collaborators, and notebook
history. Relabeling dates, starting a new session, or choosing a new split does
not restore untouched data. Previously inspected history can support useful
validation, but label it as such. A hypothesis suggested by data inspection
begins as exploratory, whether the observed pattern is favorable, unfavorable,
expected, or surprising. Separate the evidence that generated the hypothesis
from the evidence used to test its generalization.

Fit every learned transformation using information available at the decision
time: preprocessing, normalization, feature selection, imputations, groupings,
and risk estimates as well as the final predictor. Training labels must have
finished becoming observable before the forecast. A row with an earlier start
date can still contain a later outcome. Choose split gaps from the actual
information and outcome horizons rather than a conventional constant.

Record the number and nature of variants tried, including abandoned ones.
For confirmatory claims, choose a treatment of multiple comparisons or a
prospective evaluation appropriate to the search. Do not report the winner's
unadjusted uncertainty as if the winner had been specified in advance.

Overfitting includes the research process itself. Choices of sample, horizon,
metric, exclusions, subgroup, and narrative can adapt to observed outcomes even
when the final model has few parameters. Repeatedly inspecting a validation
period and revising the design turns that period into development data.
Treat a small apparent improvement after extensive search with particular
skepticism; simplicity alone does not undo the search that selected it.

## Spend complexity and compute deliberately

Audit measurement first, test the core relationship with a simple comparison,
and reserve expensive portfolio simulations or model calls for questions that
need them. Verify that each stage's measurement can actually detect the
proposed effect. A first-stage proxy must not reject candidates solely because
it cannot represent their intended economics.

Inspect parameter response curves, not just their best point. Broad stable
regions are more reassuring than a narrow peak. A best point at a grid edge
may mean an unresolved limit or a misleading parameterization; any expanded
search remains development. Avoid adding a special rule for each surprising
historical cell. Check whether apparent heterogeneity survives time periods,
influential observations, and uncertainty before fitting to it.

Decide in advance what evidence warrants the next expense. After the result,
continue with a named unresolved question, stop with a supported conclusion,
or stop as inconclusive when the available data or budget cannot resolve it.
An inconclusive result is not a request to tune until significance appears.
Leave unresolved contradictions visible when stopping; do not promote a
result whose interpretation still depends on them.
