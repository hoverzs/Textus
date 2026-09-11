# Greek Analysis v2 — Phase 2B.1: Full-Corpus Completion

**Scope:** extend the Phase 2B regression-book syntax store to all 27 NT
books; precisely categorize the ~3.31% alignment residual so a future AI
layer can fail closed rather than guess; report full-corpus syntax-
grounding coverage; harden MACULA source provenance; prove rebuild
reproducibility. **Alignment algorithm unchanged. No Gemini. No
production Supabase. Hebrew Analysis v2 untouched. No artificial push
toward 100% alignment.**
**Branch:** `greek-analysis-v2-audit` · **Base:** `3e50f26` (Phase 2B)
**Prior phases:** [`greek_analysis_v2_inventory.md`](greek_analysis_v2_inventory.md) ·
[`greek_analysis_v2_phase2a_foundation.md`](greek_analysis_v2_phase2a_foundation.md) ·
[`greek_analysis_v2_phase2b_syntax.md`](greek_analysis_v2_phase2b_syntax.md)

---

## 1. Complete phrase/clause coverage — all 27 books

Downloaded the remaining 18 books' lowfat XML (Acts, 2 Corinthians,
Galatians, Ephesians, Colossians, 1–2 Thessalonians, 2 Timothy, Titus,
Philemon, Hebrews, James, 1 Peter, 1–3 John, Jude, Revelation —
45.8 MB) alongside the 9 already fetched in Phase 2B. Same pipeline, same
schema, same parser — `LOWFAT_BOOK_FILES` in
`scripts/build_greek_syntax_store.py` extended from 9 to all 27 entries;
no other code changed.

### 1.1 Final normalized store counts (rebuilt from scratch)

| Entity | Count | Scope |
|---|---|---|
| Books | 27 | Full NT |
| TAGNT verses | 7,958 | Full NT |
| TAGNT tokens | 142,096 | Full NT |
| MACULA source nodes | 137,741 | Full NT |
| **Phrases** (`np`/`pp`/`vp`/`adjp`/`advp`) | 47,613 | **Full NT — was 9 books in Phase 2B** |
| **Clauses** (`cl`) | 43,835 | **Full NT — was 9 books in Phase 2B** |
| Total phrase+clause groups | 91,448 | Full NT |
| Syntax membership rows (group×token pairs) | 637,610 | Full NT |
| Semantic role assignments | 41,767 (post-sentinel-filter) | Full NT (was already full-corpus in 2B) |
| Coreference links | 38,585 | Full NT (was already full-corpus in 2B) |
| Distinct verses with phrase/clause data | 7,935 / 7,958 (99.7%) | Full NT |

No dedicated `participants` table exists — MACULA's participant-tracking
data is exactly what `coreference_links`' `"referent"` link type already
captures (a pronoun's antecedent token(s)); a separate table would
duplicate it under a different name, so none was added (task §1: "If
MACULA Greek lacks one of these categories, do not synthesize it" — this
one is not lacking, just already represented). No dedicated `syntax_edges`
table beyond `semantic_role_assignments` — MACULA's `frame` column *is*
the edge data (predicate→argument, role-labeled); a redundant edge table
would carry the same 41,767 pairs under a different name.

**Store size: 70,647,808 bytes (~67.4 MB)**, up from Phase 2B's ~58 MB —
+18 books of phrase/clause data added only ~10 MB, since the bulk of the
store (source nodes, alignments, roles, coreference) was already
full-corpus in Phase 2B.

No linguistic interpretation or schema changed — `bible_engine/
greek_syntax_sqlite.py`, `bible_engine/macula_greek_parser.py`,
`bible_engine/greek_token_alignment.py` are byte-identical to Phase 2B.

---

## 2. Full unresolved audit — every token categorized

`scripts/audit_greek_alignment_unresolved.py`. Alignment was **not**
altered to chase a better headline number — the same 96.69% resolved rate
from Phase 2B stands. What changed is precision of explanation for the
3.31% (4,704 tokens) that are not `EXACT`/`COMPOSITE`/`VALIDATED_FALLBACK`:

```
textual_variant_edition_difference     3,055  (64.94%)  — edition_flags predict absence from SBLGNT
candidate_claimed_by_another_tagnt_token 501  (10.65%)  — see §2.1
morphology_incompatible_candidate        481  (10.23%)  — same lemma+Strong exists, case/number disagrees
genuinely_ambiguous_duplicate            370  ( 7.87%)  — 2+ identical-surface MACULA candidates in the verse
macula_missing_node                      128  ( 2.72%)  — no surface or lemma candidate anywhere in the verse
tokenization_segmentation_difference      96  ( 2.04%)  — verse token counts differ by 2+
macula_missing_verse                      59  ( 1.25%)  — the verse has zero MACULA tokens at all
other_unexplained                         14  ( 0.30%)  — see §2.2
```

**Zero unexplained "unknown" bucket at scale** — `other_unexplained` is
0.30% of unresolved tokens, 0.01% of the full 142,096-token corpus.

### 2.1 The largest new category: a genuine limitation, precisely named

`candidate_claimed_by_another_tagnt_token` (10.65% of unresolved) is a
real, previously-uncounted-separately case this audit specifically
isolated: a morphology-*compatible* MACULA candidate for the unresolved
token genuinely exists in the verse, but it was already consumed by a
**different** TAGNT token's alignment (almost always a repeated common
word — καί, δέ, the article — where TAGNT has one more occurrence than
MACULA in that verse). This is a real property of greedy single-pass
consumption, not a data error; adding it as its own category (rather than
letting it fall into the former `other_unexplained` catch-all) dropped
that catch-all from 5.55% to 0.30% of unresolved tokens — the single most
useful finding of this phase's audit work.

### 2.2 The final 14 "other_unexplained" tokens — inspected, not just counted

All 14 are short function/adverb words (ἃ, ὅ, τυπικῶς, μήτι, ἱνατί,
οὕτως, ἰδεῖν, οὐκέτι, …) where TAGNT and MACULA cite the *lemma* itself
differently for a compound or crasis form (e.g. TAGNT's combined-paradigm
citation `"ὅς, ἥ"` vs MACULA's single-form `"ὅς"`; TAGNT lemmatizing
`ἱνατί` under its component `ἵνα` vs MACULA treating it as its own
citation form). This is a **lemma-citation-convention difference**
between the two sources, not a genuine data gap — noted here rather than
promoted to its own formal detector rule, since 14 tokens (0.01% of the
corpus) does not warrant one per the "don't chase the final tiny fraction"
instruction.

### 2.3 A sanity check this audit itself validates

`textual_variant_edition_difference` — the category built directly on
Phase 2B's central empirical finding (edition_flags predicting SBLGNT
absence) — accounts for **65% of all unresolved tokens corpus-wide**, not
just the one Jn 3:16 example it was originally validated against. This is
locked in as a test
(`test_textual_variant_edition_difference_is_the_dominant_category`).

---

## 3. Safe fallback behavior — proven corpus-wide

`tests/test_greek_syntax_fail_closed.py` (7 tests, all passing):

- Every `UNRESOLVED_*` row in the full 27-book store carries
  `macula_xml_id IS NULL` — checked as a single aggregate query across
  all 142,096 rows, not sampled.
- **No verse containing any unresolved token is ever reported
  `FULLY_GROUNDED_SYNTAX`** — checked exhaustively across all 7,958
  verses (`test_a_verse_with_any_unresolved_token_is_never_reported_
  fully_grounded`), not just spot-checked.
- An unresolved token (Jn 3:16's "αὐτοῦ") never appears inside any
  phrase/clause's mapped token membership, end-to-end through the real
  bundle builder.
- An unresolved token's own Phase 2A morphology and lexical sense are
  completely unaffected — still `fully_decoded`, still has its Hungarian
  gloss, still fully displayable.
- Attaching syntax never drops or duplicates a token — the enriched
  bundle's token list is identical to the bare Phase 2A bundle's.
- A missing/nonexistent syntax store degrades every verse to
  `NO_GROUNDED_SYNTAX` with a fully intact, displayable Phase 2A bundle —
  no exception, no partial state.

**No mechanism exists anywhere in this codebase for AI to "resolve" an
alignment gap** — `bible_engine/greek_token_alignment.py` and
`bible_engine/greek_syntax_service.py` have zero AI/network imports
(verified by the existing Phase 2A/2B static-import tests, unchanged), and
an unresolved token's `macula_xml_id` being `NULL` is a structural fact a
future prompt-builder can check before ever presenting syntax data for
that token.

---

## 4. Full-corpus syntax-grounding status

`scripts/report_greek_syntax_grounding.py`, all 7,958 verses, all 27
books:

```
FULLY_GROUNDED_SYNTAX      5,525  (69.43%)
PARTIALLY_GROUNDED_SYNTAX  2,410  (30.28%)
NO_GROUNDED_SYNTAX            23  ( 0.29%)
```

Book-level (selected — full table in
`data/generated/greek_syntax_grounding_report.json`, committed):

| Book | Fully | Partially | None | Total |
|---|---|---|---|---|
| MAT | 772 | 296 | 3 | 1,071 |
| JHN | 590 | 288 | 1 | 879 |
| LUK | 770 | 379 | 2 | 1,151 |
| ACT | 686 | 316 | 5 | 1,007 |
| ROM | 344 | 85 | 4 | 433 |
| REV | 214 | 191 | 0 | 405 |
| 3JN | 13 | 2 | 0 | 15 |

**Every one of the 27 books has at least some `FULLY_GROUNDED_SYNTAX`
verses** (locked in as a test) — phrase/clause ingestion genuinely
succeeded everywhere, not just in books that already had it from Phase
2B. This distribution — not the raw 96.69% token-alignment number — is
the number that matters for production readiness, per instruction, since
it reflects what a future contextual-AI feature can actually rely on
verse-by-verse.

---

## 5. MACULA source pinning — hardened

| | Value |
|---|---|
| Repository | `Clear-Bible/macula-greek` |
| Commit | **`8423afe47b9e8f24b7772e808af45c7159a6fe7e`** (confirmed via the GitHub API immediately before this phase's fetch; matches the repo's own `pushed_at` of 2026-07-07 — unchanged since Phase 2B, confirming Phase 2B's files were already from this exact commit even though that phase recorded only the date, not the hash) |
| License | CC BY 4.0 (Biblica, Inc) |
| Representation | SBLGNT variant, `tsv` (flat, full corpus) + `lowfat` (per-book XML, now all 27 books) |
| Acquisition date | 2026-09-11 (all 27 lowfat files + the flat TSV re-verified/fetched in this phase) |

**SHA-256 for every source file actually used**, computed directly
against the fetched bytes (28 files: the flat TSV + all 27 lowfat XML):

```
sblgnt.tsv          7f71504fdee8659bdd9f85342e4103d645864c2851b8205915bb298f0c004cc5
matthew.xml         83082bb2a094f06a4f9fd03e1f5a4b2af3977622a5c705ab65ab15ba74986de5
mark.xml            1906a855c55c00c4048de8d919caa81a35ebb7726a82b9031830e3dd9c266db8
luke.xml            10efdbb0415c1020cc288e25496496683c54ec884eb1cdee3f0ea47a0409e81b
john.xml            071d44e5a0e6c4b9c7e65944d924aed47d2b53c1774ed3ea9043b2651057715c
acts.xml            8b3093174e5cdf8d6846c316e1dc76e4dfd9d3599d6044b3419d692bcd5df37d
romans.xml          b4553cdfab04484617196657a82d596fb135ac82b252b0b55e0a3655513b7134
1corinthians.xml    701972e038bfb04c262a59e27ac73b9948800c6b67ac17e09cf3238dd41ecba2
2corinthians.xml    b675686f0a69744be1ff4057994860ee59c923fbd662bf2435841cf93ea71522
galatians.xml       33b390ff9f22fda1d7d27b9d234bc7f7cdd111efff9e72398da763cfce3b772b
ephesians.xml       0ad9968729285b856f5a8b0e51a3845a7d7256ab03abe31a47b827bf3b078824
philippians.xml     59d5843599152524b66b43ece2364b91b8155c92fadd832860086e71066f5daa
colossians.xml      10646a85185273b4df4d8e2f9019ca5748cced50fbe3348d5fffb0dd83ae0035
1thessalonians.xml  71baa51b9f4e90d63cef7a7dba05c31d08359ce7349f03afaa7745ffab12a467
2thessalonians.xml  d4546f7b670aa74bdc171497ea97f44c3b59fb89b5d2d529b1c6791d77018186
1timothy.xml        968be311bf38e20dbb74ca56f78bd81fe3490066aec524ed328b0c45f057c86b
2timothy.xml        ac85240a120687404dc192fed630b81ddf906a5aa9b3e27d465fce66c9d3ff2d
titus.xml           7a9af3c04636e2d558b06e7685a289cdd7982f920a946f96417e252e3fc8f708
philemon.xml        3782b340f3946192829fe07c229c2201390790bef2536d0223180f28bfaa756d
hebrews.xml         d993eed41dc40e2b920021735853499ddaa136b5a373c7be294a87cf383fe077
james.xml           b65a8516c3f263ad907ba3c6061ca9b524ced71ae7c2cbc753ba58e4a2cac6ef
1peter.xml          5884b7c028e716535ac6a23b454cd23b19dbcc9519416f2f7f128f38de978cd2
2peter.xml          d382f7cf9151419ce68cf8250a33436b5aba09ea6109b3bbf202271a0a1a99fc
1john.xml           cd7e151003667ceaec07b2276b2a75f8dbc6f2c57d5e5e5f09149ceffdf86b5e
2john.xml           de822aa64dc6374ba1a0920fe85e44639b26d6a74e671c49b167334c17291a47
3john.xml           bf5737c05c54083f315d777e7b8f0056c893fff8632a82d6186258872b07f579
jude.xml            096aaad13159b9354399e640344c07f4ba52ea28e14e26db4d17c4050ee63e80
revelation.xml      21d60a5eefce0b30a0c9d9426b07faa659a2a59953cdabb11b84964068715df5
```

This resolves Phase 2B's blocker #2 ("MACULA source is not checksum-
pinned") in full. Raw source still **not vendored** (66.5 MB combined) —
these checksums are sufficient for anyone to re-fetch
`https://raw.githubusercontent.com/Clear-Bible/macula-greek/8423afe.../SBLGNT/{tsv,lowfat}/...`
and verify byte-identical input before rebuilding.

---

## 6. Rebuild reproducibility — proven, not assumed

The full 27-book store was built **twice**, independently, from the same
checksummed source files, and compared at the content level (every row of
all 5 tables, in a stable order, hashed together):

```
run 1 SHA-256: 0569262feb4afba99fb0ae04a10f8b755e0e20a6942d48c61ecaa631e7e8d391
run 2 SHA-256: 0569262feb4afba99fb0ae04a10f8b755e0e20a6942d48c61ecaa631e7e8d391
IDENTICAL: True

macula_source_nodes        137,741 == 137,741
token_alignments           142,096 == 142,096
macula_groups                91,448 == 91,448
semantic_role_assignments    41,767 == 41,767
coreference_links            38,585 == 38,585
```

Byte-for-byte identical content across two independent runs — the
alignment algorithm and store builder are fully deterministic (no
`set`-based ordering, no timestamp-dependent fields, no non-deterministic
dict iteration affecting output — the query-time `ORDER BY rowid` used for
this comparison reflects the builder's own consistent insertion order).

---

## 7. Full-corpus invariants — 27 books, not 9

`tests/test_greek_syntax_invariants.py`'s 12 corpus-wide checks (already
written generically in Phase 2B to query the whole store — no changes
needed, they automatically covered all 27 books the moment the store was
rebuilt) — **all still pass** against the 637,610-row full-corpus
membership set:

- No cross-token attachment leakage (no relation via coincidental id
  equality) — checked against all 91,448 groups and 41,767 role
  assignments, not just the 9-book subset.
- Cross-verse sentence structures (§4 of the Phase 2B doc) — re-verified
  at 27-book scale: still zero cross-*book* or distant-chapter violations.
- Malformed upstream references quarantined — the same 4 Luke-1:54-style
  out-of-range frame arguments and 1,891 `"n00000000000"` implicit-
  argument sentinels, filtered identically.
- Unresolved alignment receives no unsupported syntax — extended this
  phase into its own dedicated fail-closed test file (§3 above).
- Phase 2A morphology remains unchanged — verified by
  `test_attach_syntax_never_changes_phase_2a_token_morphology_fields`
  (Phase 2B, re-run unchanged this phase) plus the fact that
  `bible_engine/greek_analysis_service.py`'s morphology-decoding code path
  was not touched at all in this phase (only `LOWFAT_BOOK_FILES` in the
  build script changed).

---

## 8. Performance at full-corpus scale

```
1 verse (Rev 21:1, a book newly in scope this phase):  ~56 ms
10 regression verses (sequential, separate calls):     ~555 ms (~55 ms/verse)
1 chapter (John 3, 36 verses, ONE call):                ~104 ms (~2.9 ms/verse)
1 whole book (Galatians, 149 verses, 6 chapter calls):  ~1,107 ms (~7.4 ms/verse)
```

**Unchanged from Phase 2B's per-verse-vs-batched finding** — the ~67 MB
store (up from ~58 MB) shows no measurable performance regression;
SQLite's indexing on `(book, chapter, verse)` scales as expected. The
Galatians whole-book measurement adds a data point between the two
extremes: 6 chapter-batched calls cost ~7.4 ms/verse, between single-verse
calls (~55 ms/verse) and single-chapter batching (~2.9 ms/verse) — **call
count, not corpus size, is the dominant cost**, reinforcing the same
conclusion for the future Supabase design: batch by chapter or larger, not
by verse, and never issue one request per verse.

---

## 9. Regression verses — unchanged as expected

All 15 Phase 2A/2B fixtures re-run against the full 27-book store produce
**identical** `syntax_grounding`, phrase/clause/pattern counts to Phase
2B's own report (all 15 were already within the original 9-book scope —
this was the expected, verified outcome, not assumed). Locked in by the
existing `test_all_15_regression_verses_build_without_error` parametrized
test (unchanged, re-run against the new store) plus a direct diff of this
phase's printed output against the Phase 2B doc's own table.

---

## 10. Tests

New this phase:

| File | Tests |
|---|---|
| `tests/test_greek_syntax_fail_closed.py` | 7 |
| `tests/test_greek_alignment_unresolved_audit.py` | 7 |

Every existing Phase 2A/2B test file re-run unchanged against the full
27-book store — no test needed modification, since they were already
written against the store generically (not hardcoded to 9 books).

```
$ pytest tests/test_greek_*.py tests/test_tagnt_*.py tests/test_tbesg_*.py \
         tests/test_lexicon_*.py tests/test_morphology_hu.py \
         tests/test_nt_lexicon_coverage.py tests/test_missing_tagnt_strong_audit.py \
         tests/test_original_language_*.py tests/test_audit_greek_lexicon_quality.py
486 passed, 6 skipped in 64.87s
```

The 6 skips are the same pre-existing, environmental ones noted in every
prior phase report (commentary database; RÚF licensed text) — unrelated.

---

## 11. Remaining blockers before Phase 2C

None block starting Phase 2C. All prior phases' blockers are now resolved
or intentionally deferred as noted:

- ~~Phrase/clause coverage limited to 9 books~~ — **resolved this phase**
  (all 27 books).
- ~~MACULA source not checksum-pinned~~ — **resolved this phase** (§5).
- **`greek_syntax_dev.sqlite3` (~67 MB) still not committed** — same
  deliberate, conservative default as Phase 2B; now proven fully
  reproducible (§6) and checksummed at the source level (§5), so the
  repository owner has everything needed to decide either way. This
  remains the one open **decision** (not blocker) carried forward.
- **1.16% of tokens remain in the `UNRESOLVED_OTHER` umbrella status**
  (though now precisely sub-categorized, §2) — acceptable per instruction;
  a future AI layer can and should check alignment status before
  presenting syntax facts for any token, which this phase's fail-closed
  tests (§3) prove is a safe, reliable signal to gate on.
- **Coordinated-structure and preposition+case detectors** still degrade
  to token-adjacency-only reasoning for verses without phrase/clause data
  — now only 0.3% of verses (23 of 7,958, §4) instead of Phase 2B's larger
  18-book gap, so this is now a genuinely minor residual.

---

## 12. Conclusion

**READY FOR PHASE 2C — SUPABASE + GROUNDED CONTEXTUAL ANALYSIS**

The syntax layer is now a genuine full-NT production candidate: 27/27
books covered, 99.71% of verses carry at least partial syntax grounding,
69.43% are fully grounded, the alignment residual is categorized down to a
0.01%-of-corpus genuinely-unexplained remainder, fail-closed behavior for
unresolved tokens is proven (not assumed) across the whole corpus, the
store rebuilds byte-identically from a fully checksummed source, and the
one remaining open item (whether to commit the ~67 MB store) is a
repository-policy decision, not a data-quality or correctness gap. Phase
2C's Supabase design should treat §8's chapter-batching finding as a hard
design constraint from its first schema draft, not an afterthought.
