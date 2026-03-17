# Language Transfer AI Tutor

## Vision

A voice AI tutor that replicates the Language Transfer method for learning Spanish. The user has a real-time voice conversation with an AI tutor that guides them to *derive* Spanish from English through patterns and rules — not memorize vocabulary. The experience should feel like talking to a patient, warm human tutor who remembers everything about the student across sessions.

The original Language Transfer is a YouTube playlist where a listener passively overhears a tutor working with a student. This project makes the user the active participant, interacting with the tutor every few seconds in a rewarding, conversational flow.

## Core Design Principles

1. **The call must feel human.** Every architectural decision serves this. Latency, pacing, personality, and memory all contribute to the illusion. One bad turn breaks immersion.
2. **Guided construction, not drilling.** The tutor leads the student to *figure out* the answer through Socratic questioning, not state it and ask for repetition. This is what makes Language Transfer work and what distinguishes this from Duolingo.
3. **The system must remember.** Across sessions, the tutor recalls what the student has practiced, what they struggle with, and how they learn best. This is the difference between a product and a demo.
4. **Latency is the product.** A correct response delivered 500ms late feels worse than a slightly less perfect response delivered on time. Every component is designed around latency budgets.
5. **Silence is a pedagogical tool, not a bug.** The architecture is optimized to minimize dead air — but during construction challenges, silence is the moment where learning actually happens. The system must distinguish between productive silence (student constructing an answer) and confused silence (student needs help), and treat each differently. Filling every pause with audio interrupts the exact cognitive work the method depends on.
6. **Name the magic.** When a student derives a correct answer, the tutor should sometimes make the underlying pattern explicit: "Notice what you just did? You took an English word ending in '-tion' and turned it into '-ción.' You can do that with hundreds of words." This metacognitive "aha moment" is what hooks students and makes Language Transfer feel different from drilling. The curriculum must encode these revelation opportunities, and the tutor must know when to deploy them.

---

## Latency Targets

| Path | When it fires | Target | % of turns |
|------|--------------|--------|------------|
| Fast path | Student answer is clearly correct or clearly wrong | 400–700ms from end of speech to start of tutor audio | ~65% |
| Medium path | Student answer has a clear error but needs specific diagnosis | 700–1200ms | ~25% |
| Slow path | Ambiguous answer requiring the tutor LLM to evaluate and respond in one pass | 1200–2000ms | ~10% |

"Start of tutor audio" includes a filler sound (e.g., "Right..." or "Hmm...") that plays within 50ms of end-of-speech detection. The latency targets above are for the tutor's *substantive* response beginning.

---

## Architecture Overview

The system is built on **Pipecat**, an open-source Python framework for real-time voice AI. Pipecat handles audio streaming, WebRTC transport, VAD (voice activity detection), service integration (STT, LLM, TTS), interruption management, and pipeline orchestration. Custom application logic is implemented as Pipecat `FrameProcessor` classes that plug into the pipeline.

### Pipeline Structure

```
User audio → Daily WebRTC → Deepgram STT → Filler Engine
  → Pattern Matcher → Orchestrator → Tutor LLM → Streaming TTS
  → Daily WebRTC → User audio
```

This is a single linear pipeline. There are no parallel branches in the MVP — the pattern matcher, orchestrator, and tutor LLM run in sequence on the critical path. The student model (BKT + teaching briefs) runs as async side-effects triggered by the orchestrator at concept boundaries, never blocking the response.

### Key Architectural Decisions

- **STT + LLM + TTS (cascaded) instead of a single real-time voice model.** This gives full control over each stage: we can intercept the transcript, run evaluation, assemble custom context for the tutor, and stream TTS with sentence-boundary chunking. A real-time voice API would not allow the orchestration this design requires.
- **Speculative pre-computation.** While the student is thinking and speaking (2–5 seconds), the orchestrator pre-builds context for both "correct" and "incorrect" branches. When STT completes, only a lightweight match determines which branch to use. This is the single largest latency optimization.
- **Tiered evaluation without a separate evaluator.** A fast fuzzy string matcher (Tier 1, ~50ms, no LLM) handles ~90% of turns. For the ~10% of ambiguous cases, the tutor LLM itself evaluates and responds in a single pass — no separate evaluator agent. The tutor receives the raw student transcript and expected answer, assesses correctness, and generates an appropriate response. This eliminates an entire component and a round-trip while staying within the slow-path latency budget.
- **Student model updates at concept boundaries, not every turn.** BKT mastery tracking and teaching briefs fire per concept attempt (every 3–5 turns when a scaffold sequence completes), not on every turn. This eliminates per-turn async LLM calls while preserving all the "magical" adaptive moments.

---

## Components

### Layer 1: Voice I/O

**1. STT Engine**
Converts student speech to text in real-time. Must provide word-level timestamps and per-word confidence scores (not just a transcript). The confidence scores are used by the pattern matcher to bias toward "correct" on low-confidence distinctions (e.g., accent marks). Runs every turn, on the critical path.

**2. TTS Engine**
Converts tutor text to speech with streaming. Receives text in sentence-boundary chunks (not token-by-token) to preserve natural prosody. The first chunk begins processing while the LLM is still generating later chunks. This overlap is essential to hitting latency targets.

**3. Filler Engine**
Plays a cached audio clip immediately when STT detects end-of-speech. Clips are pre-generated at session start (or app install) using the same TTS voice and model as the tutor, then cached as audio files. This gives sub-10ms playback latency while maintaining voice consistency — the filler and the tutor sound like the same person because they are the same voice, just pre-rendered. Clips are selected by a state machine based on context: affirmative fillers after correct answers ("Right...", "Good..."), thoughtful fillers after errors ("Hmm...", "Okay, so..."). On the slow path, a second filler may play to bridge the gap before the tutor's substantive response. Non-lexical fillers ("hmm", "mhmm") should be generated with several prompt variations and hand-picked for natural prosody, since TTS models can sound flat on non-sentence utterances.

The filler engine also implements a `THINKING_PAUSE` state for pedagogically-aware silence. When the orchestrator signals that a construction challenge has been posed (the tutor just asked the student to build something, not recall a simple fact), the filler engine suppresses immediate playback and enters a configurable silence window — typically 5–7 seconds for simple constructions, 8–12 for complex ones, keyed to a difficulty rating on the scaffold step. During this window, the system continues listening via VAD for partial speech (false starts, mumbling, "um"), which are positive signals that the student is working — partial speech resets the silence timer. If the window expires with no speech, the system does not play a filler. Instead, it triggers a graduated hint sequence from the curriculum node: first a gentle nudge ("remember what we said about '-ar' verbs"), then a narrowing prompt ("you know 'to speak' is 'hablar' — what happens when we make it 'I speak'?"), then a partial construction ("it starts with 'habl-'..."). This silence communicates trust — it implicitly says "I believe you can figure this out" — and is a core part of the Language Transfer method. Normal filler behavior resumes for non-construction turns (simple recall, meta-questions, confirmations).

### Layer 2: Evaluation

**4. Pattern Matcher (Tier 1)**
Pure code, no LLM. Compares the STT transcript against expected answer(s) for the current scaffold step using fuzzy string matching: Levenshtein distance, token normalization, accent stripping. Each scaffold step in the curriculum defines multiple acceptable answer variants.

Returns one of three signals:
- `CLEAR_MATCH` — proceed to tutor with "correct" branch (~65% of turns)
- `CLEAR_MISS` — proceed to tutor with "incorrect" branch, include the diff (~25%)
- `AMBIGUOUS` — tutor LLM receives the raw transcript and expected answer, evaluates and responds in one pass (~10%)

Must complete in under 50ms. This is on the critical path.

### Layer 3: Orchestration and Generation

**5. Session Orchestrator**
The central brain. A custom Pipecat `FrameProcessor` that implements a state machine. It does not generate natural language — it assembles context and routes data.

Responsibilities:
- **Pre-computation:** During student think time, loads the latest teaching brief and curriculum position, pre-builds context for both correct and incorrect branches.
- **Routing:** On STT completion, reads Tier 1 result and selects the appropriate branch. For `AMBIGUOUS`, includes the raw transcript and expected answer in the tutor's context so the tutor can evaluate and respond in one pass.
- **Context assembly:** Merges the selected evaluation result, the latest teaching brief from the student model, curriculum position, and scaffold step into a directive for the tutor agent.
- **Scaffold tracking:** Knows which micro-step within a concept the student is on (e.g., step 3 of 5 in "preterite -ar verbs"). On scaffold completion (concept attempt), triggers the student model's BKT update and teaching brief check as an async side-effect.
- **Silence signaling:** When the current scaffold step is a construction challenge (flagged in the curriculum node), signals the filler engine to enter `THINKING_PAUSE` state instead of playing an immediate filler. Passes the step's difficulty rating so the filler engine can set the appropriate silence window duration.
- **Revelation framing:** When a student completes a scaffold sequence that has a revelation annotation in the curriculum node (a pattern they've just used that generalizes broadly), includes a `revelation_prompt` signal in the tutor's context directing it to name the pattern explicitly. This fires only on first encounter with a pattern, not on review.
- **Emotional calibration:** Uses correctness patterns (streak length, error rate trend, off-script detection) as the tutor's tone input. Three consecutive errors signals "ease off"; five consecutive correct signals "push harder."
- **Off-script handling:** Detects and routes meta-requests (repeat, slow down, confusion) without using the pre-computed branches.

The orchestrator is pure code — no LLM calls.

**6. Tutor Agent**
The only component the user hears. An LLM with a carefully crafted system prompt that defines the tutor's personality, pedagogical approach, and voice. It receives a fully assembled context prompt from the orchestrator (not raw data) and generates a natural language response.

The tutor handles multi-turn scaffolding within a single concept: "How do you say 'to speak'?" → "hablar" → "Now, 'I speak'?" → "hablo" → "Good. 'I speak Spanish'?" → "Hablo español."

On `AMBIGUOUS` turns, the tutor also acts as the evaluator — receiving the student's raw transcript and expected answer, assessing correctness, and responding appropriately, all in one generation pass.

When the orchestrator includes a `revelation_prompt` signal (indicating the student just used a generalizable pattern for the first time), the tutor names the pattern explicitly and frames it as the student's own discovery: "Notice what you just did? You took an English word ending in '-tion' and turned it into '-ción.' You can do that with hundreds of words." This revelation framing is what makes Language Transfer feel like insight rather than instruction. The tutor should vary the framing — sometimes a brief aside ("and that pattern works for any '-tion' word"), sometimes a fuller celebration depending on the pattern's scope and the student's emotional state. Revelation framing fires only on first encounter with a pattern; on review, the tutor can reference it briefly ("remember the '-tion' trick?") but doesn't re-explain.

The tutor's output streams directly to TTS with sentence-boundary chunking. Uses the best available model — output quality IS the product.

### Layer 4: Adaptive Intelligence

These components make the tutor feel like it knows the student. They run at concept boundaries (every 3–5 turns), not every turn, and never block the tutor's response.

**7. Student Model**
Maintains a model of the student's learning state using two mechanisms:

*Bayesian Knowledge Tracing (BKT):* Updates per concept attempt (once per scaffold completion, roughly every 3–5 turns). BKT models mastery as a hidden variable, updating based on observed correct/incorrect responses while accounting for guessing and slipping probabilities. The BKT posterior directly answers "does the student know this concept?" and "should we move on?" BKT's forgetting parameter handles mastery decay between sessions naturally.

*Teaching brief (LLM):* A short pedagogical interpretation generated by a fast, cheap LLM. Fires only when meaningful state changes occur — a new error pattern emerging (third occurrence of the same error type), mastery crossing a threshold, a notable change in response speed, or a concept transition. This amounts to roughly 15–25 LLM calls per session. The teaching brief tells the tutor not just what happened but what to do about it: "They keep falling into present tense when they mean preterite. Don't re-explain the rule — try rapid-fire drilling." The latest brief persists across turns until the next trigger fires. This is the component that produces the "this tutor *gets* me" feeling.

Additionally, a simple sliding window (pure code) tracks: recent streak length, error rate over the last N turns, and response latency trend. These feed into the orchestrator's emotional calibration logic.

Cross-session state (BKT posteriors, error history, explanation preferences, and the last few teaching briefs) is persisted and loaded at session start.

**8. Curriculum Engine**
Traverses the curriculum DAG. Uses BKT mastery posteriors (from the student model) to determine concept readiness. Checks unlock thresholds — a concept's prerequisites must reach the mastery threshold before it becomes available. Selects the next concept when the current one is mastered.

Also handles session planning via simple rules: start with the most-decayed review concept, alternate between review and new material, end with a concept the student is strong on. For an MVP with 15–20 episodes in a clear linear progression, algorithmic planning is sufficient.

No LLM. Pure graph algorithms and rules on structured data.

### Layer 5: Persistence

**9. Student Profile Store**
Cross-session state: BKT mastery posteriors per concept, error history, explanation preferences, and the last few teaching briefs from the most recent session. Read at session start, written at session end. The teaching briefs serve as the cross-session memory that enables moments like "last time you struggled with the preterite — let's revisit that." No LLM-based session summarization — the structured data and teaching briefs capture everything needed.

The curriculum DAG (~80–120 concept nodes) is also stored here. Each node contains: concept identifier, prerequisites (edges), BKT parameters (learn rate, guess rate, slip rate, forget rate), exposure count, last practiced timestamp, error patterns, acceptable answer variants per scaffold step, a teaching strategy (the Socratic questioning sequence that leads the student to derive the answer), a graduated hint sequence per construction-challenge step (gentle nudge → narrowing prompt → partial construction, used by the filler engine's `THINKING_PAUSE` when silence exceeds the thinking window), a difficulty rating per scaffold step (used to set the silence window duration), and an optional revelation annotation marking where the student has just used a generalizable pattern for the first time (e.g., "-tion → -ción", "-ly → -mente") with the pattern description the tutor should name.

---

## Technology Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Voice pipeline framework | Pipecat (Python, open source) | Real-time frame-based pipeline, built-in service integrations, Pipecat Flows for state management |
| Audio transport | Daily.co (WebRTC) | First-class Pipecat integration, handles NAT traversal, echo cancellation, noise suppression |
| STT | Deepgram Nova-3 | Streaming transcription with word-level timestamps and confidence scores |
| TTS | ElevenLabs Turbo v2.5 or Cartesia Sonic | Low-latency streaming TTS with natural prosody. Test both — voice quality is subjective |
| Tutor LLM | Claude Sonnet 4.6 (Anthropic) | Best instruction-following with personality consistency. Use prompt caching for the ~2K token system prefix |
| Teaching brief LLM | Gemini 3 Flash (Google) | Fastest structured output at lowest cost. Sub-300ms TTFT. Used only for teaching briefs (~15–25 calls/session) |
| Student mastery tracking | pyBKT (Bayesian Knowledge Tracing) | Statistically principled mastery modeling with built-in forgetting |
| Persistence | Postgres (Supabase or Neon) | Student profiles, curriculum state, teaching briefs. JSON columns for flexible schema |
| Deployment | Pipecat Cloud or Modal | Managed hosting for Pipecat agents |
| Client | Pipecat React SDK | Minimal web frontend. The voice experience IS the UI |

---

## Cost Estimate Per Session

Based on a 15-minute session (~150 turns, ~30 concept attempts):

| Component | Estimated cost |
|-----------|---------------|
| Tutor LLM (150 calls, Sonnet, cached prefix) | ~$0.35 |
| Teaching briefs (~20 calls, Gemini Flash) | ~$0.02 |
| STT (15 min, Deepgram) | ~$0.06 |
| TTS (7 min tutor speech, ElevenLabs) | ~$2.10 |
| **Total** | **~$2.53** |

TTS dominates cost (~83%). LLM costs are nearly negligible with prompt caching. The student model (BKT) and curriculum engine run locally with zero API cost.

---

## Risks

### Critical (experience-killers)

- **Uncanny valley of pacing.** Even 200ms too fast feels robotic; 300ms too slow feels laggy. Variance between turns is worse than consistent slowness. The filler system and intentional micro-delays on fast-path responses are the primary mitigations.
- **Tutor personality collapse under pressure.** The tutor persona survives easy turns and flattens into generic encouragement on hard ones (frustrated student + partial error + concept boundary). This is exactly when personality matters most. Mitigation: invest heavily in few-shot examples for hard cases. The teaching briefs help by giving the tutor specific pedagogical direction.
- **Curriculum doesn't capture the method.** If the DAG only encodes *what* to teach but not *how* (the Socratic questioning sequence), the product becomes Duolingo with a nice voice, not Language Transfer. Each concept node must include the teaching strategy — the micro-prompt sequence that leads the student to construct the answer.
- **TTS voice quality ceiling.** The voice IS the product. If it sounds synthetic, the experience fails regardless of architecture quality. Budget for premium TTS and consider voice cloning.

### High (technical blockers)

- **Speculative execution mispredicts.** If the student goes off-script (asks a meta-question, answers in English, responds to a different prompt), both pre-computed branches are useless. Need a third "off-script" branch and graceful fallback.
- **Pattern matcher threshold tuning.** Too strict → most turns fall to slow path (tutor evaluates). Too loose → wrong answers marked correct. This threshold is the most important single parameter and requires real user data to tune.
- **STT errors cascade.** If STT transcribes "hablé" as "hable" (missing stress distinction), the tutor sees a tense error that doesn't exist. Use confidence scores to bias toward "correct" on low-confidence distinctions.

### Medium (manageable)

- **Over-engineering before validation.** Ship the minimal version to 5 users before adding complexity.
- **Curriculum coverage vs. depth.** Author the first 15–20 episodes deeply. Users won't hit episode 30 for weeks.
- **BKT parameter tuning.** BKT's learn rate, guess rate, slip rate, and forget rate need calibration with real student data. Start with published defaults from educational research, then tune after collecting 10+ sessions.

---

## Post-MVP Roadmap

These features were deliberately cut from the MVP. Add them when the core experience is validated with real users.

- **Pronunciation assessment.** Azure Speech Pronunciation Assessment API, running async every turn. Gate feedback with a pronunciation threshold + cooldown + severity-weighted stochastic check. Surface feedback only at natural break points to keep it feeling organic.
- **Separate evaluator agent.** If the tutor's single-pass evaluation on AMBIGUOUS turns proves insufficient (wrong assessments, poor error diagnosis), break it out into a dedicated Gemini Flash evaluator with structured JSON output.
- **LLM session planner.** Replace algorithmic session planning with an LLM that produces creative, narrative session arcs. Becomes valuable when the curriculum grows beyond 20 episodes.
- **LLM session compressor.** Summarize session transcripts into rich narrative summaries for deeper cross-session context. Becomes valuable after 20+ sessions when structured data alone may not capture nuance.
- **Affect detection.** Speech emotion recognition for detecting confidence, hesitation, and frustration beyond what correctness patterns reveal.
