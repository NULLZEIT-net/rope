---------------------------- MODULE ROPEMessages ----------------------------
(***************************************************************************)
(* Messages with custody (spec 8.5, 8.6, 14.10): a sender S, the hub H and *)
(* a recipient R. Every holder stores a message durably before it         *)
(* acknowledges it; unacknowledged messages are sent again after every    *)
(* reconnect; duplicates are recognised by id; the recipient's            *)
(* application is told about each message, and the hub reports the       *)
(* delivery back to the sender.                                           *)
(*                                                                         *)
(* Two paths at the same time: the network (one session per link, frames  *)
(* in order, lost when the session ends) and offline media. A stick is    *)
(* modelled as a set of frames that only grows and can be imported any    *)
(* number of times, in any order relative to the network (spec 8.6).      *)
(*                                                                         *)
(* What the parties keep on disk survives a crash; what they keep in      *)
(* memory (messages in flight, "told in this run") does not.              *)
(***************************************************************************)
EXTENDS Naturals, Sequences, FiniteSets

CONSTANTS
    Msgs,        \* message ids
    MaxBreaks,   \* disconnects and crashes in total (bounds the model)
    Media        \* TRUE: offline media run at the same time as the network

VARIABLES
    \* sender S (durable)
    outbox,      \* messages the application gave to S
    atHub,       \* messages S knows the hub holds (MESSAGE_ACK received)
    report,      \* messages for which S holds the report "delivered to R"
    \* hub H (durable)
    hubHas,      \* messages in the hub's custody
    delivered,   \* messages R has taken (the hub received R's MESSAGE_ACK)
    reported,    \* messages whose delivery report S acknowledged (DELIVERY_ACK)
    \* recipient R
    inbox,       \* messages R holds (durable)
    toldFlag,    \* messages whose "told" flag R stored (durable)
    toldMem,     \* messages R told its application in this run (memory)
    told,        \* how often R's application was told about each message
    window,      \* crashes of R between telling and storing the flag, per message
    \* network: S-H and H-R, frames in order, lost when the link breaks
    upSH, sh, hs, inflightS, inflightReport,
    upHR, hr, rh, inflightH,
    \* offline media: frames written to a stick, by direction
    stickSH, stickHS, stickHR, stickRH,
    breaks

vars == <<outbox, atHub, report, hubHas, delivered, reported, inbox, toldFlag, toldMem, told, window,
          upSH, sh, hs, inflightS, inflightReport, upHR, hr, rh, inflightH,
          stickSH, stickHS, stickHR, stickRH, breaks>>

sender == <<outbox, atHub, report>>
hub == <<hubHas, delivered, reported>>
recipient == <<inbox, toldFlag, toldMem, told, window>>
linkSH == <<upSH, sh, hs, inflightS, inflightReport>>
linkHR == <<upHR, hr, rh, inflightH>>
sticks == <<stickSH, stickHS, stickHR, stickRH>>

Kinds == {"MESSAGE", "MESSAGE_ACK", "DELIVERY", "DELIVERY_ACK"}
Frame == [kind : Kinds, id : Msgs]
F(k, m) == [kind |-> k, id |-> m]

TypeOK ==
    /\ outbox \subseteq Msgs /\ atHub \subseteq Msgs /\ report \subseteq Msgs
    /\ hubHas \subseteq Msgs /\ delivered \subseteq Msgs /\ reported \subseteq Msgs
    /\ inbox \subseteq Msgs /\ toldFlag \subseteq Msgs /\ toldMem \subseteq Msgs
    /\ told \in [Msgs -> Nat] /\ window \in [Msgs -> Nat]
    /\ upSH \in BOOLEAN /\ upHR \in BOOLEAN
    /\ sh \in Seq(Frame) /\ hs \in Seq(Frame) /\ hr \in Seq(Frame) /\ rh \in Seq(Frame)
    /\ inflightS \subseteq Msgs /\ inflightReport \subseteq Msgs /\ inflightH \subseteq Msgs
    /\ stickSH \subseteq Frame /\ stickHS \subseteq Frame /\ stickHR \subseteq Frame /\ stickRH \subseteq Frame
    /\ breaks \in 0..MaxBreaks

Init ==
    /\ outbox = {} /\ atHub = {} /\ report = {}
    /\ hubHas = {} /\ delivered = {} /\ reported = {}
    /\ inbox = {} /\ toldFlag = {} /\ toldMem = {}
    /\ told = [m \in Msgs |-> 0] /\ window = [m \in Msgs |-> 0]
    /\ upSH = FALSE /\ sh = <<>> /\ hs = <<>> /\ inflightS = {} /\ inflightReport = {}
    /\ upHR = FALSE /\ hr = <<>> /\ rh = <<>> /\ inflightH = {}
    /\ stickSH = {} /\ stickHS = {} /\ stickHR = {} /\ stickRH = {}
    /\ breaks = 0

\* the hub owes S a report: R has the message and S has not acknowledged a report yet
Owed == delivered \ reported

---------------------------------------------------------------------------
(* The sender's application *)

AppSend(m) ==
    /\ m \notin outbox
    /\ outbox' = outbox \cup {m}
    /\ UNCHANGED <<atHub, report, hub, recipient, linkSH, linkHR, sticks, breaks>>

---------------------------------------------------------------------------
(* Network between S and H *)

ConnectSH ==
    /\ ~upSH
    /\ upSH' = TRUE /\ inflightS' = {} /\ inflightReport' = {}
    /\ UNCHANGED <<sh, hs, sender, hub, recipient, linkHR, sticks, breaks>>

\* S sends a message the hub does not hold yet (again after every reconnect)
SSend(m) ==
    /\ upSH /\ m \in outbox \ atHub /\ m \notin inflightS
    /\ sh' = Append(sh, F("MESSAGE", m)) /\ inflightS' = inflightS \cup {m}
    /\ UNCHANGED <<upSH, hs, inflightReport, sender, hub, recipient, linkHR, sticks, breaks>>

\* H sends S a report it owes
HReport(m) ==
    /\ upSH /\ m \in Owed /\ m \notin inflightReport
    /\ hs' = Append(hs, F("DELIVERY", m)) /\ inflightReport' = inflightReport \cup {m}
    /\ UNCHANGED <<upSH, sh, inflightS, sender, hub, recipient, linkHR, sticks, breaks>>

\* H takes custody (stores, then acknowledges) or records an acknowledged report
HReceiveFromS ==
    /\ upSH /\ sh /= <<>>
    /\ sh' = Tail(sh)
    /\ LET f == Head(sh) IN
       IF f.kind = "MESSAGE" THEN
           /\ hubHas' = hubHas \cup {f.id}
           /\ hs' = Append(hs, F("MESSAGE_ACK", f.id))
           /\ UNCHANGED <<delivered, reported>>
       ELSE \* DELIVERY_ACK
           /\ reported' = reported \cup {f.id}
           /\ UNCHANGED <<hubHas, delivered, hs>>
    /\ UNCHANGED <<upSH, inflightS, inflightReport, sender, recipient, linkHR, sticks, breaks>>

\* S learns that the hub holds a message, or stores a report and acknowledges it
SReceive ==
    /\ upSH /\ hs /= <<>>
    /\ hs' = Tail(hs)
    /\ LET f == Head(hs) IN
       IF f.kind = "MESSAGE_ACK" THEN
           /\ atHub' = atHub \cup {f.id} /\ inflightS' = inflightS \ {f.id}
           /\ UNCHANGED <<report, sh>>
       ELSE \* DELIVERY: stored durably, then acknowledged
           /\ report' = report \cup {f.id}
           /\ sh' = Append(sh, F("DELIVERY_ACK", f.id))
           /\ UNCHANGED <<atHub, inflightS>>
    /\ UNCHANGED <<outbox, upSH, inflightReport, hub, recipient, linkHR, sticks, breaks>>

---------------------------------------------------------------------------
(* Network between H and R *)

ConnectHR ==
    /\ ~upHR
    /\ upHR' = TRUE /\ inflightH' = {}
    /\ UNCHANGED <<hr, rh, sender, hub, recipient, linkSH, sticks, breaks>>

\* H delivers a message R has not taken yet (again after every reconnect)
HSend(m) ==
    /\ upHR /\ m \in hubHas \ delivered /\ m \notin inflightH
    /\ hr' = Append(hr, F("MESSAGE", m)) /\ inflightH' = inflightH \cup {m}
    /\ UNCHANGED <<upHR, rh, sender, hub, recipient, linkSH, sticks, breaks>>

\* R stores the message durably (a known id is not stored again), then acknowledges
RReceive ==
    /\ upHR /\ hr /= <<>>
    /\ hr' = Tail(hr)
    /\ inbox' = inbox \cup {Head(hr).id}
    /\ rh' = Append(rh, F("MESSAGE_ACK", Head(hr).id))
    /\ UNCHANGED <<toldFlag, toldMem, told, window, upHR, inflightH, sender, hub, linkSH, sticks, breaks>>

\* H marks the message delivered to R
HReceiveFromR ==
    /\ upHR /\ rh /= <<>>
    /\ rh' = Tail(rh)
    /\ delivered' = delivered \cup {Head(rh).id}
    /\ inflightH' = inflightH \ {Head(rh).id}
    /\ UNCHANGED <<hubHas, reported, upHR, hr, sender, recipient, linkSH, sticks, breaks>>

---------------------------------------------------------------------------
(* R tells its application (spec 8.5): every stored message whose flag is not set and that was not told in   *)
(* this run; then it stores the flag. A crash in between tells the message again in the next run.          *)

RTell(m) ==
    /\ m \in inbox /\ m \notin toldFlag /\ m \notin toldMem
    /\ told' = [told EXCEPT ![m] = @ + 1] /\ toldMem' = toldMem \cup {m}
    /\ UNCHANGED <<inbox, toldFlag, window, sender, hub, linkSH, linkHR, sticks, breaks>>

RFlag(m) ==
    /\ m \in toldMem /\ m \notin toldFlag
    /\ toldFlag' = toldFlag \cup {m}
    /\ UNCHANGED <<inbox, toldMem, told, window, sender, hub, linkSH, linkHR, sticks, breaks>>

---------------------------------------------------------------------------
(* Offline media (spec 8.6): an export adds frames to a stick; an import takes them as from the network.     *)
(* Every import may happen at any time and any number of times.                                              *)

\* S: messages the hub does not hold yet, and receipts for every report S holds
SExport ==
    /\ stickSH' = stickSH \cup {F("MESSAGE", m) : m \in outbox \ atHub} \cup {F("DELIVERY_ACK", m) : m \in report}
    /\ UNCHANGED <<stickHS, stickHR, stickRH, sender, hub, recipient, linkSH, linkHR, breaks>>

HImportFromS ==
    /\ hubHas' = hubHas \cup {f.id : f \in {g \in stickSH : g.kind = "MESSAGE"}}
    /\ reported' = reported \cup {f.id : f \in {g \in stickSH : g.kind = "DELIVERY_ACK"}}
    /\ UNCHANGED <<delivered, sender, recipient, linkSH, linkHR, sticks, breaks>>

\* H for S: receipts for S's messages, and the reports it owes
HExportToS ==
    /\ stickHS' = stickHS \cup {F("MESSAGE_ACK", m) : m \in hubHas} \cup {F("DELIVERY", m) : m \in Owed}
    /\ UNCHANGED <<stickSH, stickHR, stickRH, sender, hub, recipient, linkSH, linkHR, breaks>>

SImport ==
    /\ atHub' = atHub \cup {f.id : f \in {g \in stickHS : g.kind = "MESSAGE_ACK"}}
    /\ report' = report \cup {f.id : f \in {g \in stickHS : g.kind = "DELIVERY"}}
    /\ UNCHANGED <<outbox, hub, recipient, linkSH, linkHR, sticks, breaks>>

\* H for R: the messages R has not taken
HExportToR ==
    /\ stickHR' = stickHR \cup {F("MESSAGE", m) : m \in hubHas \ delivered}
    /\ UNCHANGED <<stickSH, stickHS, stickRH, sender, hub, recipient, linkSH, linkHR, breaks>>

RImport ==
    /\ inbox' = inbox \cup {f.id : f \in stickHR}
    /\ UNCHANGED <<toldFlag, toldMem, told, window, sender, hub, linkSH, linkHR, sticks, breaks>>

\* R: receipts for every message that came on a medium (here: every message R holds)
RExport ==
    /\ stickRH' = stickRH \cup {F("MESSAGE_ACK", m) : m \in inbox}
    /\ UNCHANGED <<stickSH, stickHS, stickHR, sender, hub, recipient, linkSH, linkHR, breaks>>

HImportFromR ==
    /\ delivered' = delivered \cup {f.id : f \in stickRH}
    /\ UNCHANGED <<hubHas, reported, sender, recipient, linkSH, linkHR, sticks, breaks>>

---------------------------------------------------------------------------
(* Breaks: a link drops (frames in flight lost), or a party crashes (its memory lost, its disk kept) *)

DropSH ==
    /\ upSH /\ breaks < MaxBreaks
    /\ upSH' = FALSE /\ sh' = <<>> /\ hs' = <<>> /\ breaks' = breaks + 1
    /\ UNCHANGED <<inflightS, inflightReport, sender, hub, recipient, linkHR, sticks>>

DropHR ==
    /\ upHR /\ breaks < MaxBreaks
    /\ upHR' = FALSE /\ hr' = <<>> /\ rh' = <<>> /\ breaks' = breaks + 1
    /\ UNCHANGED <<inflightH, sender, hub, recipient, linkSH, sticks>>

\* R crashes: the messages told but not yet flagged will be told again (counted in `window`)
CrashR ==
    /\ breaks < MaxBreaks
    /\ window' = [m \in Msgs |-> IF m \in toldMem \ toldFlag THEN window[m] + 1 ELSE window[m]]
    /\ toldMem' = {}
    /\ upHR' = FALSE /\ hr' = <<>> /\ rh' = <<>> /\ breaks' = breaks + 1
    /\ UNCHANGED <<inbox, toldFlag, told, inflightH, sender, hub, linkSH, sticks>>

\* The hub crashes: both links drop; its custody is on disk
CrashH ==
    /\ breaks < MaxBreaks
    /\ upSH' = FALSE /\ sh' = <<>> /\ hs' = <<>>
    /\ upHR' = FALSE /\ hr' = <<>> /\ rh' = <<>>
    /\ breaks' = breaks + 1
    /\ UNCHANGED <<inflightS, inflightReport, inflightH, sender, hub, recipient, sticks>>

\* Nothing left to do: every message told and flagged at R, every report acknowledged by S, nothing in flight.
Done ==
    /\ \A m \in Msgs : m \in toldFlag /\ m \in reported
    /\ sh = <<>> /\ hs = <<>> /\ hr = <<>> /\ rh = <<>>
    /\ UNCHANGED vars

---------------------------------------------------------------------------

Next ==
    \/ Done
    \/ \E m \in Msgs : AppSend(m) \/ SSend(m) \/ HReport(m) \/ HSend(m) \/ RTell(m) \/ RFlag(m)
    \/ ConnectSH \/ HReceiveFromS \/ SReceive
    \/ ConnectHR \/ RReceive \/ HReceiveFromR
    \/ Media /\ (SExport \/ HImportFromS \/ HExportToS \/ SImport \/ HExportToR \/ RImport \/ RExport \/ HImportFromR)
    \/ DropSH \/ DropHR \/ CrashR \/ CrashH

\* Progress is required of the network and of telling, not of the sticks: a stick may never travel.
Fairness ==
    /\ \A m \in Msgs : WF_vars(AppSend(m)) /\ WF_vars(SSend(m)) /\ WF_vars(HReport(m)) /\ WF_vars(HSend(m))
                       /\ WF_vars(RTell(m)) /\ WF_vars(RFlag(m))
    /\ WF_vars(ConnectSH) /\ WF_vars(HReceiveFromS) /\ WF_vars(SReceive)
    /\ WF_vars(ConnectHR) /\ WF_vars(RReceive) /\ WF_vars(HReceiveFromR)

Spec == Init /\ [][Next]_vars /\ Fairness

---------------------------------------------------------------------------
(* Properties *)

\* Custody: nobody holds or reports what the previous holder did not have.
CustodyChain ==
    /\ hubHas \subseteq outbox
    /\ atHub \subseteq hubHas
    /\ inbox \subseteq hubHas
    /\ delivered \subseteq inbox
    /\ report \subseteq delivered
    /\ reported \subseteq report

\* Exactly once: the application is told at most once per message, plus once per crash between telling and
\* storing the flag (the documented "at least once" case of spec 8.5).
ToldAtMostOnce == \A m \in Msgs : told[m] <= 1 + window[m]

\* Nothing in custody is ever lost.
CustodyKept ==
    [][/\ hubHas \subseteq hubHas' /\ inbox \subseteq inbox' /\ outbox \subseteq outbox'
       /\ delivered \subseteq delivered' /\ report \subseteq report']_vars

\* Every message sent is told to R's application, and S learns that R has it.
EventuallyToldAndReported == \A m \in Msgs : <>(told[m] >= 1 /\ m \in report)
=============================================================================
