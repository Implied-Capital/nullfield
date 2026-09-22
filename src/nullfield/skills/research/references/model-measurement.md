# Language models as historical measurement tools

Use this reference when historical data is extracted, selected, labeled,
summarized, or judged by a language model. The research agent's ability to
operate tools and its validity as an empirical measurement instrument are
separate questions.

## Define the information boundary

Specify what the model is meant to know at each historical decision. Inventory
the supplied documents, retrieval results, tools, instructions, memories, and
other context that can influence its response. Record source availability,
transformations, prompts, model and client identifiers, and relevant settings.
A provider's model name does not necessarily identify immutable weights.

Disabling retrieval or asking the model to ignore later events does not erase
knowledge in its parameters. A claimed training cutoff alone does not certify
an uncontaminated evaluation. Treat model-based historical measurements as
requiring evidence about their validity, even when the task is called extraction.

## Correct quotations do not settle the question

Check that a cited passage supports the asserted fact, state, and date. An exact
quotation can accompany an unsupported claim. Missing information should remain
missing rather than be filled from recollection or a forced answer schema.

Even fully supported statements can be selected or emphasized using later
knowledge. Audit both factual fidelity and the choice of evidence. Record
omissions, abstentions, and coverage alongside error rates; an empty answer
cannot demonstrate a useful and accurate measurement system.

Choose fixed, source-grounded questions where they fit the research objective,
but test them. A fixed checklist can still omit relevant information or admit
contamination. It is a design choice, not a guarantee of historical validity.

## Test the actual failure channel

Construct controls for unsupported claims, misleading citations, changed
historical states, and outcome-informed selection when those are relevant.
Separate technical formatting checks from tests of semantic validity and
downstream usefulness. An automated substring check cannot establish entailment;
a second model's agreement is not independent human ground truth.

Identity masking and counterfactual changes can reveal sensitivity, but they
can also remove legitimate information, leave clues, or create inconsistent
examples. State what an intervention identifies and what alternative explanations
remain. Supplying artificial later information measures susceptibility to that
information; it does not estimate the prevalence of naturally memorized outcomes.

If a statistical learner measures information in extracted outputs, keep all
variants and repetitions of the same underlying case or related family in the
same evaluation group. Fit preprocessing on training data only. Prevent answer
keys, condition labels, ordering, and run metadata from becoming unintended
predictors. Include appropriate negative and positive controls.

Repetitions characterize model variability; they do not create new independent
historical cases. Report failed or missing responses and their denominators.
Choose retry rules before collection; technical retries retain their original
records, and undesired substantive answers are observations rather than errors
to rerun away. Preserve versions when repairing a scorer after collection.

## Keep the claim narrow

Separate collection completeness, deterministic checks, reviewed semantic
accuracy, selection effects, and economic usefulness. Report the actual review
status and uncertainty. Synthetic controls establish performance on constructed
cases; historical checks establish evidence within their sampling frame.
Neither certifies every future use.

Prefer prospective evaluation when it can resolve historical ambiguity. When
it cannot yet do so, retain the limitation in the project notebook and in any
downstream finding instead of converting an untested assumption into a fact.
