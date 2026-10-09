# Recommendation Quality Evaluation

## Method
- Dataset: active Indian movie model, 48,599 records; no model or dataset artifacts were rebuilt.
- Model A and Model B were called through the existing Flask test client. Model B used deterministic fallback parsing; Gemini and OMDb were disabled for reproducibility.
- Explicit filters were checked against returned dataset genre, language, year, and runtime fields. Mood/audience are soft ranking hints, not hard constraints.
- No ground-truth labels were available. Results below are qualitative; no accuracy, precision, or recall is claimed.

## Model A

| Case | Status / count | Top five recommendations | Finding |
|---|---:|---|---|
| Exact title: `3 Idiots` | 200 / 5 | Idiots; 4 Idiots; Ummeed; Khandaani Shafakhana; Pestonjee | Query resolves and returns five unique neighbors. |
| Case-insensitive: `3 idiots` | 200 / 5 | Idiots; 4 Idiots; Ummeed; Khandaani Shafakhana; Pestonjee | Same result order as exact casing. |
| Partial title: `3 Idi` | 200 / 5 | Idiots; 4 Idiots; Ummeed; Khandaani Shafakhana; Pestonjee | Prefix lookup resolves to the same source title. |
| Indian source: `RRR` | 200 / 5 | NGK; Pithamagan; Agaram; Agarram; Thirupaachi | Source title excluded; recommendations are returned. |
| Non-Indian source: `Iron Man` | 200 / 5 | Superman; Ra.One; Vikram; Shani; Roar: Tigers of the Sundarbans | Works on a non-Indian title represented in the active dataset; superhero/action signal is plausible, but relevance is not label-verified. |
| Unknown title | 404 / 0 | None | Controlled not-found response. |
| Duplicate source title: `RRR` | 200 / 8 | NGK; Pithamagan; Agaram; Agarram; Thirupaachi (plus three) | Dataset has two `RRR` rows; neither source nor duplicate recommendation appears. Duplicate count: 0. |
| Missing metadata: `#Love` | 200 / details | Not applicable | Dataset/OMDb fallback returned details without crashing; nullable fields remain representable. |
| Repeated `RRR` query | 200 / 5 each | Same as `RRR` above | Responses were identical across repeated calls. |

Model A relevance caveat: TF-IDF/nearest-neighbor operation is verified, but some lexical neighbors can be weak semantic matches (for example, “Raiders of the Rail Road” appears for an Indiana Jones source). There is no labeled relevance set to quantify this.

## Model B

`Genre`, `language`, `year`, and `duration` show compliance with parsed explicit constraints. Soft-hint counts mean the top five intersect at least one mood/audience genre hint; they do not indicate ground-truth suitability. Duplicate and private-field columns count results across the full response.

| Query | Parsed intent (non-default fields) | Count | Explicit constraint checks | Top-five soft-hint matches | Duplicates / metadata-gap rows / private fields | Top five results | Qualitative finding |
|---|---|---:|---|---:|---|---|---|
| Feel-good movie to watch alone | `mood=feel_good`, `audience=solo` | 10 | No hard genre/language/year/duration constraint | 5/5 | 0 / 2 / 0 | Heerak Rajar Deshe; Sagara Sangamam; Suno Chanda; Diyar-e-Dil; Kumbalangi Nights | Good feel-good genre signals. Solo is soft and does not make all results thriller/action-oriented; no ground truth for solo preference. |
| Family-friendly Indian comedy | `genres=comedy,family`; `audience=family`; 16 dataset-supported Indian languages | 10 | Genre PASS; language PASS | 5/5 | 0 / 0 / 0 | Heerak Rajar Deshe; Anbe Sivam; Goopy Gyne Bagha Byne; Chithram; Ananthu v/s Nusrath | All returned items match comedy or family genre and at least one inferred Indian language. “Indian” expands to a broad language set by design. |
| Suspense thriller | `genre=thriller`; `mood=intense` | 10 | Genre PASS | 5/5 | 0 / 0 / 0 | Mirror Game; Raatchasan; Aaranya Kaandam; Thani Oruvan; Theeran Adhigaram Ondru | Returned genres and tone hints align with the request. |
| Short movie for tonight | `duration=short` | 10 | Runtime PASS (<120 minutes) | N/A | 0 / 0 / 0 | Coke Studio; Alpha Bravo Charlie; The Legend of Hanuman; Aloko Udapadi; Oggatonama | Includes short-form/series records as well as films; dataset has no separate media-format constraint. |
| Emotional romantic movie | `mood=romantic` | 10 | No hard genre/language/year/duration constraint | 5/5 | 0 / 0 / 0 | Sagara Sangamam; Sankarabharanam; Pyaasa; Guide; Alai Payuthey | Romance signals are present. The single-value mood schema retains romantic and does not separately encode “emotional.” |
| Science-fiction adventure | `genres=adventure,fantasy,action` | 10 | Genre-hint filter PASS | N/A | 0 / 2 / 0 | Uncharted 2: Among Thieves; Alpha Bravo Charlie; Dhuwan; Kireedam; Dipu Number 2 | Dataset has no controlled science-fiction genre; science fiction maps to available genre proxies, so sci-fi semantics cannot be guaranteed. |
| Telugu action movie | `genre=action`; `language=telugu`; `mood=intense` | 10 | Genre PASS; language PASS | 5/5 | 0 / 0 / 0 | Pokiri; Rakshasudu; Dhruva; Dream; Gaganam | Explicit genre and language constraints hold. |
| Hindi romantic movie | `language=hindi`; `mood=romantic` | 9 | Language PASS | 5/5 | 0 / 0 / 0 | Pyaasa; Guide; Ijaazat; Gully Boy; Amar Prem | Returns nine rather than ten available candidates; all satisfy Hindi and top results carry romance signals. |
| Movie between 2010 and 2020 | `year_from=2010`; `year_to=2020` | 10 | Year PASS, inclusive | N/A | 0 / 1 / 0 | Mirror Game; Aloko Udapadi; Pichhodu; Natsamrat; C/o Kancharapalem | Year bounds hold. One result has one or more unavailable display metadata fields. |
| Short Hindi comedy | `genre=comedy`; `language=hindi`; `duration=short` | 10 | Genre PASS; language PASS; runtime PASS (<120 minutes) | N/A | 0 / 0 / 0 | Yeh Suhaagraat Impossible; Ankhon Dekhi; I Am Kalam; Rainbow; Stanley Ka Dabba | Evaluation exposed missing duration parsing for this phrasing; fixed and regression-tested. |
| Family-friendly Telugu movie | `genre=family`; `language=telugu`; `audience=family` | 10 | Genre PASS; language PASS | 5/5 | 0 / 3 / 0 | Missamma; Lava Kusa; The Jungle Book; Little Soldiers; Devadasu | Explicit genre/language hold. Three result rows have incomplete optional metadata. |
| Feel-good movie released after 2015 | `mood=feel_good`; `year_from=2016` | 10 | Year PASS, strictly after 2015 | 5/5 | 0 / 1 / 0 | Suno Chanda; Kumbalangi Nights; Ananthu v/s Nusrath; Pashupati Prasad; Pelli Choopulu | Evaluation exposed inclusive handling of “after”; fixed, including merge over partial Gemini intent, and regression-tested. |

## Evaluation Fixes
- Recognize “short” duration when paired with explicit genre/language terms, including “short Hindi comedy.”
- Interpret “after N” as year $N+1$; preserve explicit year bounds when Gemini omits them.
- Recognize `science-fiction` as well as `science fiction`, `sci-fi`, and `scifi`.
- The family-comedy compliance check was rerun against all ten rows; it passes. The initial false flag came from the evaluation predicate, not the recommender.
