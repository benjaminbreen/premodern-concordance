# Pilot Prototype Notes

This is a draft, minimal prototype to generate preliminary results for a proposal.

## What is included
- `test_pairs.csv`: 54 entity pairs with link types and notes.
- `run_embeddings.py`: embedding baseline with summary metrics.
- `run_llm_review.py`: optional LLM review for uncertain pairs.

## Quick Start

```bash
cd "/Users/benjaminbreen/code/Premodern Concordance"
python3 -m venv .venv
source .venv/bin/activate
pip install -r pilot/requirements.txt

# Run embedding baseline
python pilot/run_embeddings.py --pairs pilot/test_pairs.csv

# (Optional) Run LLM review on uncertain pairs
# First add your API key to pilot/.env.local
python pilot/run_llm_review.py --results pilot/embedding_results.csv
```

## Preliminary Results (Feb 2026)

### Model Comparison

We tested multiple embedding models to find the best baseline:

| Model | Precision | Recall | F1 | Same_Referent Recall@0.7 |
|-------|-----------|--------|-----|--------------------------|
| **BGE-M3** | 1.000 | 0.255 | 0.407 | 10.0% |
| Arctic-Embed-L-v2 | 0.929 | 0.277 | 0.426 | 10.0% |
| Paraphrase-mMPNet | 0.909 | 0.213 | 0.345 | 15.0% |
| mE5-Large-Instruct | 0.870 | 1.000 | 0.931 | 100.0% ⚠️ |

**⚠️ mE5-Large-Instruct caveat:** This model gives everything high similarity scores (hard negatives avg 0.897, same as matches). It has no discriminative power—100% recall is meaningless if you can't distinguish matches from non-matches.

**Why BGE-M3 wins:** It maintains the best separation between matches and non-matches:

| Model | Same_Referent Avg | Hard_Negative Avg | Gap |
|-------|-------------------|-------------------|-----|
| BGE-M3 | 0.513 | 0.463 | **+0.050** |
| Arctic-Embed-L-v2 | 0.435 | 0.397 | +0.038 |
| mE5-Large-Instruct | 0.896 | 0.897 | -0.001 |

This validates the proposal's thesis: off-the-shelf embeddings either miss cross-lingual matches (BGE-M3) or can't distinguish matches from non-matches (mE5). **Fine-tuning is necessary.**

### Embedding Baseline (BGE-M3, threshold 0.7)

| Metric | Value |
|--------|-------|
| Precision | 1.000 |
| Recall | 0.250 |
| F1 | 0.400 |

**By link type:**

| Type | Avg Similarity | Recall@0.7 | Recall@0.5 |
|------|----------------|------------|------------|
| orthographic_variant | 0.777 | 70% | 100% |
| derivation | 0.621 | 33% | 100% |
| contested_identity | 0.546 | 14% | 43% |
| same_referent | 0.509 | **9.5%** | 38% |
| conceptual_overlap | 0.493 | 14% | 29% |
| hard_negative | 0.469 | 0% | 17% |

**Key observations:**
- Orthographic variants work well (dodo/doudo = 0.84, theriaca/theriac = 0.87)
- Cross-lingual same_referent is hard (dodo/walghvogel = 0.37, ginseng/ren shen = 0.49)
- Hard negatives overlap with same_referent scores — model can't distinguish "different things" from "same thing, different language"

### LLM Review (Gemini 2.5 Flash)

28 pairs in the uncertain band (similarity 0.4–0.7) were sent to Gemini for evaluation.

**Results:**
- 21 pairs correctly identified as MATCH
- 7 pairs correctly identified as NO MATCH
- LLM caught all cross-lingual same_referent pairs the embedding model missed
- LLM correctly identified contested cases (dodo vs solitaire = different species)
- LLM corrected one label error (sea cow/manati are different species, not same_referent)

**Combined pipeline performance:**

| Stage | Recall on true matches |
|-------|------------------------|
| Embedding only (threshold 0.7) | ~25% |
| Embedding + LLM review | ~85% |

### Notable LLM Reasoning Examples

**penguin / great auk** (contested_identity):
> "In the 17th century, the English term 'penguin' was commonly used to refer to the Great Auk (*Pinguinus impennis*), a large, flightless bird of the North Atlantic. The name was later transferred to the Southern Hemisphere birds we call penguins today."

**unicorn horn / narwhal tusk** (conceptual_overlap → same_referent):
> "In the 1600s, what was commonly known and traded as 'unicorn horn' was almost exclusively the tusk of the narwhal. The true zoological origin of these 'horns' as coming from a marine mammal was not widely understood."

**sea cow / manati** (corrected from same_referent to NO MATCH):
> "Steller's 'sea cow' specifically refers to *Hydrodamalis gigas*, an extinct sirenian species discovered in the Bering Sea. Oviedo's 'manati' refers to species of *Trichechus* (manatees), which are a different genus."

## Caveats
- Many sources in `test_pairs.csv` are still vague ("1600s", "early modern") and need specific citations.
- Link types should be refined based on LLM feedback (e.g., sea cow/manati label was incorrect).
- The 54-pair test set is small; results may not generalize.

## Fine-Tuning Results (Feb 2026)

### Methodology

We fine-tuned BGE-M3 on our expanded dataset of 265 entity pairs using contrastive learning with CosineSimilarityLoss.

**Critical:** We used a proper train/test split to avoid overfitting:
- 75% of pairs (199) used for training
- 25% of pairs (66) held out for evaluation (never seen during training)
- Stratified split to ensure each link type is represented in both sets

**Training configuration:**
- Base model: BAAI/bge-m3
- Platform: Google Colab free GPU (T4)
- Epochs: 10
- Batch size: 16
- Learning rate: 2e-5
- Data augmentation: swapped pairs (term_b, term_a) added to training set

### Overall Metrics (threshold=0.7)

| Model | Precision | Recall | F1 |
|-------|-----------|--------|-----|
| Original BGE-M3 | 1.000 | 0.246 | 0.395 |
| **Fine-tuned** | 0.750 | 0.789 | 0.769 |

The fine-tuned model trades some precision for dramatically improved recall, resulting in a much higher F1 score.

### Per Link-Type Results

| Link Type | Original Avg Sim | Fine-tuned Avg Sim | Delta | Original Recall@0.7 | Fine-tuned Recall@0.7 |
|-----------|------------------|--------------------|---------|--------------------|----------------------|
| same_referent | 0.522 | 0.763 | **+0.241** | 13.3% | 68.9% |
| orthographic_variant | 0.791 | 0.841 | +0.050 | 77.8% | 100% |
| derivation | 0.604 | 0.798 | +0.194 | 0% | 100% |
| contested_identity | 0.558 | 0.726 | +0.168 | 25.0% | 75.0% |
| conceptual_overlap | 0.530 | 0.770 | +0.240 | 20.0% | 80.0% |
| hard_negative | 0.476 | 0.657 | +0.181 ⚠️ | 0% | 25.0% ⚠️ |

### Biggest Improvements (Cross-Lingual Matches)

These pairs show the fine-tuning working as intended—dramatically improving cross-lingual same_referent detection:

| Pair | Link Type | Original | Fine-tuned | Delta |
|------|-----------|----------|------------|-------|
| Spiessglas / antimony | same_referent | 0.299 | 0.972 | **+0.673** |
| ginseng / ren shen | same_referent | 0.496 | 0.900 | **+0.404** |
| clove / kruidnagel | same_referent | 0.362 | 0.758 | +0.396 |
| tutty / tutia | same_referent | 0.440 | 0.808 | +0.368 |
| cinchona / quinquina | same_referent | 0.502 | 0.869 | +0.367 |
| rhubarb / ruibarbo | same_referent | 0.502 | 0.848 | +0.346 |
| sal ammoniac / sal armoniac | orthographic_variant | 0.616 | 0.950 | +0.334 |
| camphor / kāfūr | same_referent | 0.501 | 0.814 | +0.313 |
| antimony / stibium | same_referent | 0.509 | 0.820 | +0.311 |

### Failure Cases

**Hard negatives pushed together (false positives):**

| Pair | Original | Fine-tuned | Problem |
|------|----------|------------|---------|
| musk / civet | 0.509 | 0.775 | Different substances incorrectly marked as similar |
| phoenix / salamander | 0.431 | 0.701 | Mythical creatures grouped together |

**Same_referent pairs that got worse:**

| Pair | Original | Fine-tuned | Problem |
|------|----------|------------|---------|
| aurochs / urus | 0.793 | 0.701 | Already good match slightly degraded |
| clove / ding xiang | 0.419 | 0.444 | Chinese term not sufficiently improved |

### Hard Negative Separation

| Metric | Original | Fine-tuned |
|--------|----------|------------|
| same_referent avg | 0.522 | 0.763 |
| hard_negative avg | 0.476 | 0.657 |
| **Gap** | 0.046 | 0.106 |

The fine-tuned model improved separation by +0.060, but hard negatives were also pushed upward (from 0.476 to 0.657), causing some false positives.

### Analysis

**What worked:**
- Cross-lingual same_referent pairs showed dramatic improvement (+0.2 to +0.7 delta)
- The model learned that terms in different languages/scripts can refer to the same entity
- Overall F1 nearly doubled (0.395 → 0.769)

**What didn't work:**
- Hard negatives were pushed together instead of apart (musk/civet, phoenix/salamander)
- Some already-good matches degraded slightly
- 25% of hard negatives now incorrectly score above 0.7

**Why this happened:**
With only 15 hard_negative pairs in the full dataset (~4 in test set), the model didn't see enough negative examples to learn proper separation. The contrastive loss successfully pulled positives together but lacked sufficient negative pressure.

### Recommendations for Full Implementation

1. **More hard negatives:** Expand hard_negative pairs to 50+ covering:
   - Similar-sounding but different substances (musk/civet, ambergris/amber)
   - Related but distinct species (manatee/dugong, llama/alpaca)
   - Conceptually similar but historically distinct terms

2. **Harder negatives:** Current hard negatives may be too semantically similar. Add truly distinct pairs that share only superficial features.

3. **Triplet loss:** Consider switching from CosineSimilarityLoss to TripletLoss or MultipleNegativesRankingLoss, which explicitly push negatives apart.

4. **More training data:** 265 pairs is minimal. Target 1000+ pairs for production fine-tuning.

5. **Domain-specific evaluation:** Create separate test sets for different domains (medicines, species, places) to identify where the model struggles.

## Next Steps
1. ~~Expand test set to 200+ pairs with verified citations.~~ ✓ Done (265 pairs)
2. ~~Add more extinction/species pairs (dodo examples performed well).~~ ✓ Done
3. ~~Fine-tune embedding model on annotated pairs to improve cross-lingual recall.~~ ✓ Done (proof of concept)
4. Parse LLM responses programmatically to compute formal accuracy metrics.
5. Test explanation correctness evaluation (do LLM-cited reasons match expert link types?).
6. **NEW:** Expand hard_negative training pairs to improve separation.
7. **NEW:** Experiment with TripletLoss or MultipleNegativesRankingLoss..
