# Tasks

## How to use this file

Each task is a self-contained unit of work that one person can own. Dependencies are listed explicitly — do not start a task until its dependencies are complete. Tasks within the same phase that share no dependencies can be worked on in parallel by different people.

Completion criteria are defined per task. A task is "done" when its criteria are met and another team member has reviewed the output.

---

## Phase 0: Foundation

Everything downstream depends on this phase. Complete it before starting any Phase 1 work.

### T1. Curriculum content authoring

**Owner:** Requires deep familiarity with the Language Transfer Spanish playlist.

**What:** Transcribe and analyze the Language Transfer Spanish episodes. Extract a structured curriculum as a JSON dataset.

**Output:** A JSON file (or set of files) containing ~80–120 concept nodes. Each node must include:
- Concept identifier and human-readable name
- Prerequisite concept IDs (edges in the DAG)
- The teaching strategy: the ordered sequence of Socratic micro-prompts the tutor uses to guide the student to derive the answer (not just state it)
- For each scaffold step: the prompt the tutor asks, and a list of acceptable answer variants (accounting for optional pronouns, accent variations, alternate phrasings)
- For each scaffold step: a difficulty rating (1–3) indicating construction complexity. This determines how long the system waits in silence before offering hints. A simple recall ("what does 'hablar' mean?") is 1; a multi-part construction ("how would you say 'I don't want to eat it'?") is 3.
- For each construction-challenge step (difficulty ≥ 2): a graduated hint sequence of 2–3 hints, from vague to specific. Example for "I speak Spanish" → hint 1: "Remember what happens to '-ar' verbs when it's 'I'?" → hint 2: "You know 'hablar' — what's the 'I' form?" → hint 3: "It starts with 'habl-'..." These fire in order when the student is silent, giving just enough scaffolding without revealing the answer.
- Revelation annotations: for scaffold steps where the student has just applied a generalizable pattern for the first time (e.g., "-tion → -ción", "-ly → -mente", "'-ar' verbs drop '-ar' and add '-o' for 'I'"), include a `revelation` field with: the pattern name, a description the tutor can use to make the pattern explicit ("Notice what you just did? You took an English word ending in '-tion' and turned it into '-ción.' You can do that with hundreds of words."), and a short-form reference for review encounters ("remember the '-tion' trick?"). Not every step has a revelation — only the moments where a new transferable rule clicks into place.
- Common error patterns for the concept (what students typically get wrong and why)
- Initial BKT parameters (learn rate, guess rate, slip rate, forget rate) — use published defaults, will be tuned later

**Scope for MVP:** The first 15–20 episodes, deeply authored. This covers approximately 2–3 weeks of daily use.

**Dependencies:** None. This is the first task.

**Completion criteria:** Another team member can read any concept node and understand exactly what the tutor should say, what the student should respond, what common errors look like, when and how long to hold silence, what hints to offer if the student is stuck, and where the tutor should name a generalizable pattern — without listening to the original episode.

**Estimated effort:** 4–6 days.

---

### T2. Data model and persistence layer

**Owner:** Backend developer.

**What:** Design the data schemas for curriculum nodes and student profiles. Implement a persistence layer with read/write operations.

**Output:**
- Schema definitions for: curriculum DAG nodes (from T1 structure), student profiles (cross-session state: BKT mastery posteriors per concept, error history, explanation preferences, last few teaching briefs).
- A persistence API with operations: load student profile, save student profile, load curriculum DAG, update concept mastery, append teaching brief.
- Seeded with the curriculum data from T1.

**Dependencies:** T1 (schema is shaped by the curriculum node structure).

**Completion criteria:** The persistence layer can round-trip all data types. A test script can create a student, load the curriculum, update mastery on a concept, store a teaching brief, and retrieve the updated state.

**Estimated effort:** 1–2 days.

---

## Phase 1: Parallel Tracks

Two independent tracks. Each track can be worked on simultaneously by different people. Both tracks depend on T1 and T2 being complete.

---

### Track A: Core Voice Loop

The minimum path from student speech to tutor response.

#### T3. Pattern matcher (Tier 1)

**Owner:** Backend developer.

**What:** Build the fuzzy string matching engine that compares STT transcripts against expected answers. Must handle: case normalization, accent mark stripping/matching, optional subject pronouns ("hablo" vs "yo hablo"), common STT transcription errors, and Levenshtein distance thresholds.

**Input:** A transcript string and a list of acceptable answer variants (from the curriculum node).

**Output:** One of three signals: `CLEAR_MATCH`, `CLEAR_MISS` (with a diff indicating what's wrong), or `AMBIGUOUS`.

**Dependencies:** T1 (needs the expected answer variants to test against).

**Completion criteria:** Given a test set of 50+ transcript/expected-answer pairs (including edge cases like missing accents, extra words, wrong tense), the matcher produces the correct signal ≥90% of the time. Runs in under 50ms.

**Estimated effort:** 2–3 days.

---

#### T4. Tutor agent prompt and personality

**Owner:** Prompt engineer / product lead.

**What:** Design the tutor agent's system prompt, personality, and few-shot examples. The tutor must embody the Language Transfer method: patient, Socratic, warm, and willing to sit in silence while the student thinks.

**Output:**
- A system prompt that defines the tutor's personality, pedagogical rules, and output format.
- Few-shot examples covering: correct answer (advance scaffold), incorrect answer (guide without revealing), partial answer (acknowledge what's right, probe what's wrong), student frustration (slow down, try a different explanation), student asking a meta-question ("can you repeat that?", "I don't understand"), concept boundary transitions, AMBIGUOUS evaluation (tutor receives raw transcript + expected answer and must assess correctness while responding naturally), revelation framing (tutor receives a `revelation_prompt` signal and names the pattern the student just used — must feel like genuine delight at the student's discovery, not a canned explanation; vary between brief asides and fuller celebrations depending on the pattern's scope), and post-silence hint recovery (tutor picks up naturally after the student has received 1–2 graduated hints from the filler engine's thinking pause, acknowledging the student's effort without making them feel slow: "Take your time — you're building something new here").
- A specification for the context format the orchestrator will inject per turn (so the prompt and orchestrator agree on the interface). This includes: how the teaching brief is injected, how AMBIGUOUS turns are flagged, how correctness streak / emotional calibration signals are formatted, how the `revelation_prompt` signal is passed (with the pattern description and whether this is a first encounter or review), and how the `thinking_pause_hints_given` count is communicated (so the tutor knows how much scaffolding the student has already received before the tutor's turn).

Test with hardcoded context (no orchestrator yet). The goal is to get the voice right in isolation.

**Dependencies:** T1 (needs curriculum examples to write realistic few-shot cases).

**Completion criteria:** Five people listen to 10 tutor responses across easy and hard scenarios (including AMBIGUOUS evaluation turns) and rate them as "feels like a human tutor" ≥80% of the time.

**Estimated effort:** 3–4 days (iterative — prompt tuning takes cycles).

---

#### T5. Filler engine

**Owner:** Any developer.

**What:** Build the filler audio system. Pre-generate 20–30 short filler phrases using the same TTS voice and model as the tutor agent. Cache them as audio files. Implement a state machine that selects the appropriate clip based on context.

**Output:**
- A script that generates filler clips via the TTS API using the tutor's voice. For non-lexical fillers ("hmm", "mhmm"), generate several prompt variations and hand-pick the most natural-sounding takes.
- Cached audio clips organized into three pools: affirmative ("Right...", "Good...", "Mhmm..."), thoughtful ("Hmm...", "Okay so...", "Let's see..."), and neutral ("Okay...", "So...").
- A Pipecat `FrameProcessor` that intercepts STT end-of-speech events and immediately pushes the selected cached filler audio frame to the output pipeline.
- The processor receives a signal from the pattern matcher indicating which pool to draw from (correct → affirmative, incorrect → thoughtful, ambiguous → thoughtful).
- On the slow path, the processor can fire a second filler after a configurable delay.
- A `THINKING_PAUSE` state that the orchestrator activates when a construction challenge has been posed. In this state, the filler engine suppresses immediate filler playback and enters a silence window (duration set by the scaffold step's difficulty rating: 5–7s for difficulty 2, 8–12s for difficulty 3). During the window, VAD continues listening — partial speech (false starts, mumbling, "um") resets the timer as a positive signal the student is constructing. If the window expires with no speech, the engine triggers graduated hints from the curriculum node's hint sequence (delivered via TTS, not cached clips) in order: first a gentle nudge, then a narrowing prompt, then a partial construction. After each hint, a shorter silence window opens before the next hint fires. The `THINKING_PAUSE` state is not entered for simple recall or confirmation turns (difficulty 1) — those use normal filler behavior.

**Dependencies:** T4 must have selected the TTS voice (so fillers match the tutor). Can otherwise start immediately when Phase 1 begins.

**Completion criteria:** Filler audio plays within 50ms of end-of-speech detection. Pool selection matches context correctly. The double-filler slow-path behavior works with configurable timing. Filler voice is indistinguishable from the tutor's voice. `THINKING_PAUSE` correctly suppresses fillers for construction challenges, detects partial speech via VAD and resets the timer, and fires graduated hints in sequence when silence exceeds the window. Normal filler behavior activates correctly for non-construction turns.

**Estimated effort:** 2–3 days.

---

#### T6. Streaming TTS integration

**Owner:** Backend developer with audio experience.

**What:** Integrate the TTS engine with sentence-boundary chunking. The LLM streams tokens; this component buffers them until a sentence boundary (period, question mark, exclamation mark, or comma + conjunction), then sends the complete clause to TTS for processing.

**Output:**
- A Pipecat `FrameProcessor` that sits between the tutor LLM output and the TTS service.
- Buffers LLM text tokens and detects sentence boundaries.
- Sends complete clauses to TTS, which begins audio generation while the LLM continues producing subsequent clauses.
- The first TTS audio chunk should begin playing while the LLM is still generating.

**Dependencies:** T4 (needs tutor LLM output to test chunking behavior).

**Completion criteria:** Measured latency from LLM first token to first TTS audio output is under 300ms. Prosody sounds natural (no mid-sentence cuts or awkward pauses at chunk boundaries).

**Estimated effort:** 2–3 days.

---

### Track B: Intelligence Layer

The components that make the tutor adaptive.

#### T7. Student model

**Owner:** Backend developer.

**What:** Implement the student model using Bayesian Knowledge Tracing (BKT) for mastery tracking, a sliding window for within-session patterns, and a trigger-based LLM "teaching brief" for pedagogical interpretation.

**Output:**
- BKT integration (via pyBKT or equivalent): per-concept mastery tracking that updates on each concept attempt (scaffold completion), not every turn. BKT models mastery as a hidden variable, accounting for guessing and slipping. Outputs a mastery posterior per concept. BKT's forgetting parameter handles mastery decay between sessions.
- A sliding window (pure code) tracking: recent streak length, error rate over the last N turns, and response latency trend. These feed into the orchestrator's emotional calibration logic (consecutive errors → ease off, consecutive correct → push harder).
- A trigger-based teaching brief: an LLM call (Gemini Flash) that fires only when meaningful state changes occur — a new error pattern emerging (third occurrence of same error type), mastery crossing a threshold (up or down), a notable change in response speed, or a concept transition. Roughly 15–25 calls per session. The brief produces a short pedagogical interpretation: not just "mastery: 0.45" but "They keep falling into present tense — try rapid-fire drilling instead of re-explaining the rule." The latest brief persists in the orchestrator's state until the next trigger fires.
- Cross-session persistence: BKT posteriors, error history, explanation preferences, and the last few teaching briefs are saved to the student profile at session end and loaded at session start. The teaching briefs serve as cross-session memory ("last time you struggled with preterite").

**Dependencies:** T2 (needs persistence layer for cross-session state).

**Completion criteria:** Given a simulated sequence of 30 concept attempts with varying correctness, BKT posteriors move appropriately (mastery increases on correct streaks, decreases on errors, decays between sessions). Teaching briefs fire on state changes and produce actionable pedagogical guidance (verified by a human reviewer).

**Estimated effort:** 2–3 days.

---

#### T8. Curriculum engine

**Owner:** Backend developer.

**What:** Implement the DAG traversal engine that manages concept sequencing, mastery tracking, and spaced repetition.

**Output:**
- A Python class that loads the curriculum DAG from the persistence layer and provides operations: get current concept, advance to next scaffold step, mark concept attempt (correct/incorrect), get next concept (when current is mastered), get review candidates (decayed concepts).
- Mastery checks: uses BKT mastery posteriors from the student model (T7) to determine concept readiness.
- Unlock logic: a concept becomes available when all prerequisite concepts reach the unlock threshold (default mastery posterior ≥ 0.7).
- Review weaving: when the engine is asked for the next concept, it may return a review candidate instead of a new concept if BKT mastery has decayed below threshold.
- Session planning via simple rules: start with the most-decayed review concept, alternate between review and new material, end with a concept the student is strong on. Algorithmic, no LLM.

**Dependencies:** T1 (needs the DAG structure), T2 (needs persistence layer).

**Completion criteria:** Given a simulated sequence of mastery updates over 10 sessions with realistic timing gaps, the engine correctly identifies which concepts need review, which are unlocked, and which are next in sequence. Session-start planning produces a reasonable concept order.

**Estimated effort:** 2–3 days.

---

## Phase 1 Milestone

All components work independently in isolation. The tutor speaks naturally with hardcoded context (including AMBIGUOUS evaluation turns). The pattern matcher scores correctly against the test set. BKT mastery tracking updates correctly per concept attempt. The curriculum engine traverses the DAG. No components are wired together yet.

---

## Phase 2: Integration

All Phase 1 tasks must be complete before starting Phase 2. This phase is sequential — T9 must be complete before T10.

### T9. Session orchestrator

**Owner:** Senior developer (most complex component).

**What:** Build the central orchestrator that wires all components together within the Pipecat pipeline.

**Output:**
- A Pipecat `FrameProcessor` implementing a state machine with states: `WAITING_FOR_SPEECH`, `THINKING_PAUSE`, `EVALUATING`, `GENERATING`, `SPEAKING`, `PRE_COMPUTING`.
- Pre-computation logic: during `WAITING_FOR_SPEECH`, loads the latest teaching brief and curriculum position, pre-builds context for both correct and incorrect branches.
- Silence signaling: when the current scaffold step is a construction challenge (difficulty ≥ 2), transitions to `THINKING_PAUSE` instead of `WAITING_FOR_SPEECH` after the tutor's prompt. Sends the filler engine the step's difficulty rating so it can set the appropriate silence window. Tracks how many graduated hints have been delivered during the pause and includes this count (`thinking_pause_hints_given`) in the tutor's context when the student finally responds, so the tutor knows how much scaffolding was already provided.
- Routing logic: on STT completion, reads Tier 1 result, selects the appropriate branch. For `AMBIGUOUS`, includes the raw transcript and expected answer in the tutor's context so the tutor can evaluate and respond in one pass.
- Context assembly: merges the selected evaluation result, the latest teaching brief, curriculum position, scaffold step, correctness streak, and (when applicable) the `revelation_prompt` signal and `thinking_pause_hints_given` count into a directive string for the tutor agent.
- Revelation signaling: when the current scaffold step has a revelation annotation in the curriculum node and this is the student's first encounter with the pattern (not a review), includes the `revelation_prompt` in the tutor's context with the pattern description. On review encounters, includes only the short-form reference.
- Scaffold tracking: manages the current position within a concept's micro-prompt sequence. On scaffold completion, triggers BKT update and teaching brief check in the student model as a non-blocking async side-effect.
- Emotional calibration: uses the sliding window (streak length, error rate trend) from the student model and off-script detection to set the tutor's tone.
- Off-script handling: detects and routes meta-requests (repeat, slow down, confusion) without using the pre-computed branches.

**Dependencies:** T3, T4, T5, T6, T7, T8 (all Phase 1 components).

**Completion criteria:** A complete voice session works end-to-end: the user speaks, hears a filler, hears the tutor respond appropriately, and the system advances through scaffold steps correctly. The fast path completes within the 400–700ms latency target.

**Estimated effort:** 4–5 days.

---

### T10. End-to-end latency tuning

**Owner:** Backend developer with profiling experience.

**What:** Instrument every phase boundary in the pipeline and optimize until latency targets are met.

**Output:**
- Instrumentation: timestamps at STT end-of-speech, filler play, Tier 1 result, tutor LLM first token, TTS first audio chunk, and TTS playback start.
- A latency dashboard or log that shows per-turn timing breakdown.
- Optimizations as needed: prompt caching verification, model warmup, connection pooling, buffer tuning.

**Dependencies:** T9 (needs the integrated pipeline to measure).

**Completion criteria:** Over 50 test turns, p50 fast-path latency is under 600ms and p95 is under 900ms. p50 slow-path latency is under 1500ms.

**Estimated effort:** 2–3 days.

---

## Phase 2 Milestone

A single voice session works end-to-end. The user can have a full lesson that feels conversational. The tutor responds within latency targets on the fast path. Filler audio masks remaining latency. The student model adapts within the session via teaching briefs. No cross-session memory yet.

---

## Phase 3: Cross-Session Memory

Phase 2 must be complete. This phase is a single task.

### T11. Cross-session memory wiring

**Owner:** Backend developer.

**What:** Connect the session lifecycle: student model state persists at session end and loads at session start, enabling cross-session memory.

**Output:**
- End-of-session flow: orchestrator signals session end → student model writes BKT posteriors, error history, explanation preferences, and the last few teaching briefs to the student profile via persistence layer.
- Start-of-session flow: persistence layer loads student profile → BKT posteriors restore mastery state → curriculum engine runs session planning rules (review decayed concepts, select new material) → latest teaching briefs load into orchestrator context → tutor has full cross-session memory.
- Mastery decay verification: BKT forgetting works correctly across real time gaps between sessions.
- Tutor recall verification: the tutor can naturally reference previous session events ("Last time you had trouble with the preterite — let's revisit that") via the persisted teaching briefs.

**Dependencies:** T9 (needs the working integrated pipeline).

**Completion criteria:** A user completes two sessions 24 hours apart. In the second session, the tutor references specific struggles from the first session, reviews decayed concepts, and doesn't re-teach mastered material.

**Estimated effort:** 1–2 days.

---

## Phase 3 Milestone: MVP Complete

Multi-session learning journey works. The tutor remembers the student across sessions, adapts pacing and difficulty, follows the curriculum DAG with spaced repetition, and teaching briefs produce "this tutor knows me" moments.

---

## Dependency Graph Summary

```
T1 ──→ T2 ──→ T7, T8
 │              
 ├────→ T3 ───────────────→ T9 ──→ T10 ──→ T11
 ├────→ T4 ──→ T5 ────────→ T9
 │      └────→ T6 ────────→ T9
```

**Critical path:** T1 → T4 → T6 → T9 → T10 → T11

**Maximum parallelism:** With 2 people, assign:
- Person A: T1 → T4 → T5 → T6 (critical path, voice quality)
- Person B: T2 → T3 → T7 → T8 (data + evaluation + intelligence)

Both converge at T9 (orchestrator), which one senior person should own.

With 3 people:
- Person A: T1 → T4 → T5 → T6 (critical path, voice quality)
- Person B: T3 → T7 (pattern matcher + student model)
- Person C: T2 → T8 (persistence + curriculum engine)

**Total: 11 tasks, ~3.5 weeks, 3 milestones.**
