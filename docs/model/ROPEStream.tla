----------------------------- MODULE ROPEStream -----------------------------
(***************************************************************************)
(* One stream from a source to the hub (spec 8.2-8.4, 8.6, 9, 14.5,       *)
(* 14.10).                                                                 *)
(*                                                                         *)
(* The source file grows; the source sends segments within a window; the  *)
(* hub stores a segment only at its committed offset and acknowledges only *)
(* what it stores durably; after a disconnect or a crash of either side   *)
(* the greeting reports the hub's committed offset and the source resumes *)
(* there; the final check compares sizes and contents (spec 8.4).         *)
(*                                                                         *)
(* Offline media run at the same time (spec 8.6): the source writes the   *)
(* bytes from what the hub acknowledged to a stick, the hub imports a     *)
(* bundle at any time and any number of times, and its receipt (ACK)      *)
(* travels back by stick. So segments from the network arrive as          *)
(* duplicates or beyond a gap, as in practice.                            *)
(*                                                                         *)
(* Bytes are modelled by their position: byte i of the source file has    *)
(* the value i, and the hub's store is the sequence of values it wrote.   *)
(* A segment carries one byte. The hub's store is durable on every write  *)
(* (write, flush, then acknowledge: spec 14.10 rule 1), so a crash of the *)
(* hub loses only the connection. Not modelled here: block repair of      *)
(* bytes changed in place and new generations (spec 14.7), several        *)
(* streams.                                                                *)
(***************************************************************************)
EXTENDS Naturals, Sequences

CONSTANTS
    MaxLen,      \* the source file grows to at most this many bytes
    Window,      \* unacknowledged segments in flight (spec 8.2)
    MaxBreaks    \* disconnects and crashes in total (bounds the model)

VARIABLES
    srcLen,      \* bytes in the source file; it only grows
    complete,    \* the application declared the stream complete (spec 8.4)
    up,          \* a session is active
    sent,        \* source: offset of the next byte to send
    acked,       \* source: highest offset the hub acknowledged (network or stick)
    endSent,     \* source: STREAM_END sent in this session
    result,      \* source: result of the final check it was told
    toHub,       \* frames in flight to the hub (TCP: in order, lost when the session ends)
    toSrc,       \* frames in flight to the source
    store,       \* hub: the bytes stored durably, in order
    verified,    \* hub: result of its final check
    bundles,     \* sticks from the source: byte ranges [from, to) as written
    receipts,    \* sticks from the hub: committed offsets as written
    breaks       \* disconnects and crashes so far

vars == <<srcLen, complete, up, sent, acked, endSent, result, toHub, toSrc, store, verified, bundles, receipts,
          breaks>>

Max(a, b) == IF a > b THEN a ELSE b
Min(a, b) == IF a < b THEN a ELSE b

Results == {"none", "ok", "mismatch"}
Frames ==
    [type : {"SEGMENT"}, off : 0..MaxLen, byte : 1..MaxLen]
    \cup [type : {"STREAM_END"}, size : 0..MaxLen]
    \cup [type : {"ACK"}, committed : 0..MaxLen + 1]
    \cup [type : {"RESEND"}, off : 0..MaxLen]
    \cup [type : {"STREAM_CHECK"}, result : {"ok", "mismatch"}]

TypeOK ==
    /\ srcLen \in 0..MaxLen
    /\ complete \in BOOLEAN /\ up \in BOOLEAN /\ endSent \in BOOLEAN
    /\ sent \in 0..MaxLen /\ acked \in 0..MaxLen + 1
    /\ result \in Results /\ verified \in Results
    /\ toHub \in Seq(Frames) /\ toSrc \in Seq(Frames)
    /\ store \in Seq(1..MaxLen)
    /\ bundles \subseteq [from : 0..MaxLen, to : 0..MaxLen]
    /\ receipts \subseteq 0..MaxLen
    /\ breaks \in 0..MaxBreaks

Init ==
    /\ srcLen = 0 /\ complete = FALSE /\ up = FALSE
    /\ sent = 0 /\ acked = 0 /\ endSent = FALSE /\ result = "none"
    /\ toHub = <<>> /\ toSrc = <<>>
    /\ store = <<>> /\ verified = "none"
    /\ bundles = {} /\ receipts = {}
    /\ breaks = 0

media == <<bundles, receipts>>

\* The recording program appends a byte; a complete stream does not grow.
Grow ==
    /\ ~complete /\ srcLen < MaxLen
    /\ srcLen' = srcLen + 1
    /\ UNCHANGED <<complete, up, sent, acked, endSent, result, toHub, toSrc, store, verified, media, breaks>>

\* The application declares the stream complete (e.g. the file is unchanged for a while).
Complete ==
    /\ ~complete
    /\ complete' = TRUE
    /\ UNCHANGED <<srcLen, up, sent, acked, endSent, result, toHub, toSrc, store, verified, media, breaks>>

\* HELLO / WELCOME (spec 14.5): WELCOME.have reports the hub's committed offset, the source resumes there.
Connect ==
    /\ ~up
    /\ up' = TRUE
    /\ sent' = Len(store) /\ acked' = Len(store)
    /\ endSent' = FALSE
    /\ UNCHANGED <<srcLen, complete, result, toHub, toSrc, store, verified, media, breaks>>

\* A segment with the next byte, within the window (spec 8.2).
SendSegment ==
    /\ up /\ sent < srcLen /\ sent - acked < Window
    /\ toHub' = Append(toHub, [type |-> "SEGMENT", off |-> sent, byte |-> sent + 1])
    /\ sent' = sent + 1
    /\ UNCHANGED <<srcLen, complete, up, acked, endSent, result, toSrc, store, verified, media, breaks>>

\* STREAM_END only after everything up to the final size is acknowledged (spec 14.7, step 1).
SendEnd ==
    /\ up /\ complete /\ ~endSent /\ result /= "ok" /\ acked >= srcLen
    /\ toHub' = Append(toHub, [type |-> "STREAM_END", size |-> srcLen])
    /\ endSent' = TRUE
    /\ UNCHANGED <<srcLen, complete, up, sent, acked, result, toSrc, store, verified, media, breaks>>

\* The hub takes the next frame (spec 8.3, 8.4): stores a segment only at its committed offset and then
\* acknowledges; a duplicate is acknowledged without writing; a gap is answered with RESEND.
HubReceive ==
    /\ up /\ toHub /= <<>>
    /\ toHub' = Tail(toHub)
    /\ LET f == Head(toHub) IN
       IF f.type = "SEGMENT" THEN
           IF f.off = Len(store) THEN
               /\ store' = Append(store, f.byte)
               /\ toSrc' = Append(toSrc, [type |-> "ACK", committed |-> Len(store) + 1])
               /\ UNCHANGED verified
           ELSE IF f.off < Len(store) THEN
               /\ toSrc' = Append(toSrc, [type |-> "ACK", committed |-> Len(store)])
               /\ UNCHANGED <<store, verified>>
           ELSE
               /\ toSrc' = Append(toSrc, [type |-> "RESEND", off |-> Len(store)])
               /\ UNCHANGED <<store, verified>>
       ELSE
           \* STREAM_END: same size and same content (the SHA-256 of spec 14.7 compares the bytes)
           LET ok == f.size = Len(store) /\ \A i \in 1..Len(store) : store[i] = i
               r == IF ok THEN "ok" ELSE "mismatch"
           IN /\ verified' = r
              /\ toSrc' = Append(toSrc, [type |-> "STREAM_CHECK", result |-> r])
              /\ UNCHANGED store
    /\ UNCHANGED <<srcLen, complete, up, sent, acked, endSent, result, media, breaks>>

\* The source takes the next frame from the hub.
SourceReceive ==
    /\ up /\ toSrc /= <<>>
    /\ toSrc' = Tail(toSrc)
    /\ LET f == Head(toSrc) IN
       IF f.type = "ACK" THEN
           /\ acked' = Max(acked, f.committed)
           /\ UNCHANGED <<sent, result>>
       ELSE IF f.type = "RESEND" THEN
           /\ sent' = Min(sent, f.off)
           /\ UNCHANGED <<acked, result>>
       ELSE
           /\ result' = f.result
           /\ UNCHANGED <<sent, acked>>
    /\ UNCHANGED <<srcLen, complete, up, endSent, toHub, store, verified, media, breaks>>

---------------------------------------------------------------------------
(* Offline media (spec 8.6) *)

\* The source writes the bytes from what the hub acknowledged up to the file's size.
SourceExport ==
    /\ acked < srcLen
    /\ bundles' = bundles \cup {[from |-> acked, to |-> srcLen]}
    /\ UNCHANGED <<srcLen, complete, up, sent, acked, endSent, result, toHub, toSrc, store, verified, receipts,
                   breaks>>

\* The hub imports a bundle: as from the network, only at the committed offset (spec 8.6 "Import"); a bundle that
\* starts beyond it is a gap and is skipped, bytes already stored are not written again.
HubImport(b) ==
    /\ b \in bundles
    /\ b.from <= Len(store) /\ Len(store) < b.to
    /\ store' = store \o [i \in 1..(b.to - Len(store)) |-> Len(store) + i]
    /\ UNCHANGED <<srcLen, complete, up, sent, acked, endSent, result, toHub, toSrc, verified, media, breaks>>

\* The hub writes its committed offset to a stick for the source (spec 8.6: hub -> source carries ACK).
HubExport ==
    /\ receipts' = receipts \cup {Len(store)}
    /\ UNCHANGED <<srcLen, complete, up, sent, acked, endSent, result, toHub, toSrc, store, verified, bundles,
                   breaks>>

SourceImport(c) ==
    /\ c \in receipts /\ c > acked
    /\ acked' = c
    /\ UNCHANGED <<srcLen, complete, up, sent, endSent, result, toHub, toSrc, store, verified, media, breaks>>

---------------------------------------------------------------------------
(* Breaks *)

\* The connection breaks, or the hub crashes (its store is durable): frames in flight are lost.
Disconnect ==
    /\ up /\ breaks < MaxBreaks
    /\ up' = FALSE /\ toHub' = <<>> /\ toSrc' = <<>>
    /\ breaks' = breaks + 1
    /\ UNCHANGED <<srcLen, complete, sent, acked, endSent, result, store, verified, media>>

\* The source program crashes: what it knew in memory is gone; the file stays.
SourceCrash ==
    /\ breaks < MaxBreaks
    /\ up' = FALSE /\ toHub' = <<>> /\ toSrc' = <<>>
    /\ sent' = 0 /\ acked' = 0 /\ endSent' = FALSE /\ result' = "none"
    /\ breaks' = breaks + 1
    /\ UNCHANGED <<srcLen, complete, store, verified, media>>

\* Nothing left to do: the source knows the stream passed its final check.
Done ==
    /\ result = "ok"
    /\ UNCHANGED vars

Next ==
    \/ Grow \/ Complete \/ Connect \/ SendSegment \/ SendEnd
    \/ HubReceive \/ SourceReceive
    \/ SourceExport \/ (\E b \in bundles : HubImport(b)) \/ HubExport \/ (\E c \in receipts : SourceImport(c))
    \/ Disconnect \/ SourceCrash \/ Done

\* Progress is required of the network, not of the sticks: a stick may never travel.
Fairness ==
    /\ WF_vars(Grow) /\ WF_vars(Complete) /\ WF_vars(Connect)
    /\ WF_vars(SendSegment) /\ WF_vars(SendEnd)
    /\ WF_vars(HubReceive) /\ WF_vars(SourceReceive)

Spec == Init /\ [][Next]_vars /\ Fairness

---------------------------------------------------------------------------
(* Properties *)

\* Bit for bit: the hub stores every byte at its own position.
StoredCorrectly == \A i \in 1..Len(store) : store[i] = i

\* The hub never holds more than the source has.
NoInvention == Len(store) <= srcLen

\* The source is never told that more is stored than the hub holds (spec 14.10 rule 1).
AckedIsStored == acked <= Len(store)

\* A stream verified at the hub is the whole, completed file.
VerifiedIsWhole == verified = "ok" => (complete /\ Len(store) = srcLen)

\* When the source is told "ok", the hub holds the whole file.
ResultIsTrue == result = "ok" => (complete /\ Len(store) = srcLen /\ verified = "ok")

\* The final check never fails in this model: no byte changes in place (block repair is a separate model).
NeverMismatch == verified /= "mismatch"

\* Nothing stored is ever lost or changed.
StoreOnlyGrows == [][Len(store') >= Len(store) /\ \A i \in 1..Len(store) : store'[i] = store[i]]_vars

\* Despite disconnects, crashes and sticks, the source learns in the end that the whole file arrived.
EventuallyVerified == <>(result = "ok")
=============================================================================
