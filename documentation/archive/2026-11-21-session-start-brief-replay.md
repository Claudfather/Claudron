---
title: SessionStart brief replay for Claudron issue 178
type: audit
status: completed
owner: Claudron maintainers
created: 2026-11-21
updated: 2026-11-21
---

# SessionStart brief replay

Codex added identical copies of Claudron's brief to resumed and forked context. Claude also reran the hook and its pull path, but sent one copy of the unchanged brief to the model. Both hosts needed the hook on resume and fork when the parent session had never received the brief. Both delivered a changed reviewed brief. The event source cannot distinguish those cases. [Issue #178](https://github.com/Claudfather/Claudron/issues/178)

## Owner hook replay

Run from the checkout with `python -m claudron.tests.replay_session_start`. The [replay](../../claudron/tests/replay_session_start.py) runs the command emitted by each adapter's `hooks install` against a temporary vault and a local bare Git remote. It uses a private home and temporary directory, permits only Git's local file transport, and cleans up the vaults. The table uses Claudron 0.11.0 at `7c04f70`.

Claude payloads use the documented schema. Codex's startup, resume, PreCompact and compact payloads come from the [sanitized native fixtures](../../claudron/tests/fixtures/codex/README.md), with synthetic paths and IDs. Its clear and fork payloads use the documented schema. Source values were also observed on the current native Codex binary in the separate loopback experiment below. [Claude hooks reference](https://code.claude.com/docs/en/hooks#sessionstart) · [Codex hooks reference](https://learn.chatgpt.com/docs/hooks#matchers)

These stdout results were identical on both adapters. Byte counts are UTF-8 and include the trailing newline. A repeated section has the same heading and content as in the preceding SessionStart emission. This comparison measures emitted text at the hook boundary.

| Event | Brief bytes | Capture instruction bytes | Repeated sections |
| --- | ---: | ---: | --- |
| Fresh startup | 759 | 0 | 0 of 3 |
| Unchanged resume | 759 | 0 | 3 of 3 |
| PreCompact | 0 | 0 | 0 |
| First compact start | 759 | 413 | 3 of 3 |
| Second compact start | 759 | 0 | 3 of 3 |
| Clear | 759 | 0 | 3 of 3 |
| Fork | 759 | 0 | 3 of 3 |
| Resume after a reviewed update | 764 | 0 | 2 of 3 |
| Resume with an added authored draft | 847 | 0 | 2 of 3 |

The three sections are Vault conventions, Recalled context, and Unverified. The reviewed update changes Recalled context only. The update was committed upstream and verified absent from the clone before the hook. The resume fast-forwarded to the reviewed commit and printed the new summary. The two external drafts remained visible with title, type, path, and provenance. Neither body canary appeared at any event.

The authored-draft control adds an entry to Unverified and leaves the reviewed sections intact. Its body canary stays out on both adapters. The original replay on `9d9d409` printed that draft's first body line. Claudron 0.11.0 changed the brief to require review for authored notes as well as web and transcript notes, and the replay now asserts that boundary. [Claudron #257](https://github.com/Claudfather/Claudron/pull/257) · [Schema trust classes](../../SCHEMA.md#reads-maturity--origin) · [CLI trust contract](../specs/CLI_CONTRACT.md#command-specific-contracts)

## Native loopback requests

The native measurements below used Claudron 0.10.0 at `9d9d409`. Claude Code 2.1.330 and Codex CLI 0.171.0-alpha.13 ran with private settings, synthetic vaults, and fixed model replies from a loopback server. The recorded counts come from outgoing request content. No real model inference was used. The fork came from the thread after its unchanged resume. The changed resume reused that original thread, so it excluded the fork's additional copy.

| First main request after | Claude brief copies | Codex brief copies |
| --- | ---: | ---: |
| Startup | 1 | 1 |
| Unchanged resume | 1 | 2 |
| Unchanged fork of the resumed thread | 1 | 3 |
| Resume with changed reviewed content | 2, one old and one changed | 3, two old and one changed |
| Resume of a thread started without the hook | 1, supplied by resume | 1, supplied by resume |
| Fork of a thread started without the hook | 1, supplied by fork | 1, supplied by fork |
| Interactive `/compact` | 1, plus the capture instruction | 1, plus the capture instruction |
| Interactive `/clear` | 1 | 1 |

Each copy includes all three headings. Both hosts re-emitted 749 bytes on the unchanged resume and fork and 754 bytes on the changed resume. In a separate interactive run, each host emitted 1,162 bytes on compact and 749 bytes on clear. The canned compaction reply was just `ok`, so the original brief could not have arrived as part of the summary. The first main request after clearing used a new session ID and received the brief. The loopback requests contained zero web or transcript body canaries. Claude's unchanged and changed resume results also match the [prior native observation on issue #178](https://github.com/Claudfather/Claudron/issues/178#issuecomment-5874671847).

## Recommendation

Keep emitting the brief with the current hook inputs. For Codex, compare the newly rendered brief against the most recent brief from the same hook and vault that is still active in the request. Omit the new copy only on a byte-for-byte match. Do the comparison after pull and recall so reviewed updates remain visible, including a change from A to B and back to A. Fresh contexts, compacted or cleared contexts, and resumed or forked contexts with no active copy still need the brief. Preserve the separate compaction instruction.

The supported wire input identifies the event and session, and may name a transcript path. It does not report which prior hook blocks are still active. A prior emission or a matching session ID does not establish delivery or retention, and Codex documents its transcript format as unstable for hooks. The unbriefed resume and fork controls rule out suppressing either source categorically. For the measured Claude version, a second copy of unchanged output never reached the request, so there is no demonstrated prompt-byte savings from engine-side suppression there. [Codex hook inputs](https://learn.chatgpt.com/docs/hooks#common-input-fields)
