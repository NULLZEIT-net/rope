"""Checks the TLA+ models of docs/model/ with TLC, the TLA+ model checker: every reachable state of each
configuration is explored and its invariants and properties are checked.

    python docs/model/check.py                    # every configuration
    python docs/model/check.py --mutations        # and the mutation checks (each must be found)
    python docs/model/check.py --mutations --record   # and write RESULTS.md

Run from time to time, in particular when the behaviour described in the spec changes; not part of every test run.

Mutation checks break one rule of the design on purpose (in a temporary copy of a model). TLC must report a
violation for each of them; a mutation that passes would mean the model is too weak to see that error.

Needs Java 11 or newer and tla2tools.jar of the TLA+ release named below, given in the environment variable TLA2TOOLS
or placed next to this file (it is not in the repository and not downloaded by this script; get it from
https://github.com/tlaplus/tlaplus/releases). Exit code 0 only if every configuration passes and, with
--mutations, every mutation is found.
"""

import argparse
import datetime
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TLA_RELEASE = "v1.7.4"
TLA_SHA256 = "936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88"

#: (model, configuration, what it covers)
CHECKS = [
    ("ROPEStream", "ROPEStream.cfg", "one stream, a file of up to 3 bytes, window 2, network and sticks, up to 2 breaks"),
    ("ROPEMessages", "ROPEMessages.cfg", "one message, network and sticks, up to 3 breaks"),
    ("ROPEMessages", "ROPEMessagesTwo.cfg", "two messages, network only, up to 2 breaks"),
]

#: (model, configuration, what the mutation breaks, text in the model, replacement)
MUTATIONS = [
    ("ROPEStream", "ROPEStream.cfg", "the hub writes a segment at the offset it names, without checking its committed offset",
     "IF f.off = Len(store) THEN", "IF TRUE THEN"),
    ("ROPEStream", "ROPEStream.cfg", "the hub acknowledges a duplicate segment as one byte more than it stores",
     '[type |-> "ACK", committed |-> Len(store)])', '[type |-> "ACK", committed |-> Len(store) + 1])'),
    ("ROPEStream", "ROPEStream.cfg", "the source resumes from what it sent, not from WELCOME.have",
     "/\\ sent' = Len(store) /\\ acked' = Len(store)", "/\\ sent' = sent /\\ acked' = acked"),
    ("ROPEStream", "ROPEStream.cfg", "the source sends STREAM_END before everything is acknowledged",
     '/\\ up /\\ complete /\\ ~endSent /\\ result /= "ok" /\\ acked >= srcLen',
     '/\\ up /\\ complete /\\ ~endSent /\\ result /= "ok"'),
]
for _cfg in ("ROPEMessages.cfg", "ROPEMessagesTwo.cfg"):
    MUTATIONS += [
        ("ROPEMessages", _cfg, "the recipient forgets which messages it told in this run",
         "/\\ m \\in inbox /\\ m \\notin toldFlag /\\ m \\notin toldMem", "/\\ m \\in inbox /\\ m \\notin toldFlag"),
        ("ROPEMessages", _cfg, "the hub acknowledges a message without taking custody",
         "/\\ hubHas' = hubHas \\cup {f.id}\n           /\\ hs' = Append(hs, F(\"MESSAGE_ACK\", f.id))",
         "/\\ hubHas' = hubHas\n           /\\ hs' = Append(hs, F(\"MESSAGE_ACK\", f.id))"),
        ("ROPEMessages", _cfg, "the sender does not send again after a reconnect",
         "/\\ upSH' = TRUE /\\ inflightS' = {} /\\ inflightReport' = {}",
         "/\\ upSH' = TRUE /\\ inflightS' = inflightS /\\ inflightReport' = {}"),
        ("ROPEMessages", _cfg, "the hub counts a message as delivered when it sends it, not on the recipient's receipt",
         "/\\ hr' = Append(hr, F(\"MESSAGE\", m)) /\\ inflightH' = inflightH \\cup {m}\n"
         "    /\\ UNCHANGED <<upHR, rh, sender, hub,",
         "/\\ hr' = Append(hr, F(\"MESSAGE\", m)) /\\ inflightH' = inflightH \\cup {m}\n"
         "    /\\ delivered' = delivered \\cup {m}\n    /\\ UNCHANGED <<hubHas, reported, upHR, rh, sender,"),
    ]


def jar():
    path = os.environ.get("TLA2TOOLS") or os.path.join(HERE, "tla2tools.jar")
    if not os.path.isfile(path):
        sys.exit("tla2tools.jar not found (set TLA2TOOLS or put it next to check.py); TLA+ release %s" % TLA_RELEASE)
    return os.path.abspath(path)


def tlc(tools, folder, model, cfg):
    """Runs TLC on model.tla with cfg in folder. Returns (passed, finding, numbers, seconds)."""
    t0 = time.monotonic()
    res = subprocess.run(["java", "-XX:+UseParallelGC", "-cp", tools, "tlc2.TLC", "-workers", "auto", "-cleanup",
                          "-metadir", os.path.join(folder, "states", cfg), "-config", cfg, model + ".tla"],
                         cwd=folder, capture_output=True, text=True)
    out = res.stdout + res.stderr
    secs = time.monotonic() - t0
    m = re.search(r"([\d,.]+) states generated, ([\d,.]+) distinct states found, 0 states left", out)
    d = re.search(r"depth of the complete state graph search is (\d+)", out)
    numbers = dict(generated=int(re.sub(r"\D", "", m.group(1))) if m else None,
                   distinct=int(re.sub(r"\D", "", m.group(2))) if m else None,
                   depth=int(d.group(1)) if d else None)
    passed = res.returncode == 0 and "No error has been found" in out
    finding = ""
    for ln in out.splitlines():
        if ln.startswith("Error:") and ("violated" in ln or "Deadlock" in ln):
            finding = ln[len("Error:"):].strip()
            break
    if not passed and not finding:
        finding = (out.strip().splitlines() or ["TLC failed"])[-1]
    return passed, finding, numbers, secs


def mutate(tools, model, cfg, old, new):
    src = open(os.path.join(HERE, model + ".tla"), encoding="utf-8").read()
    if src.count(old) != 1:
        return False, "the text to change was not found once in %s.tla" % model, {}, 0.0
    folder = tempfile.mkdtemp(prefix="rope-model-")
    try:
        with open(os.path.join(folder, model + ".tla"), "w", encoding="utf-8") as f:
            f.write(src.replace(old, new))
        shutil.copy(os.path.join(HERE, cfg), folder)
        passed, finding, numbers, secs = tlc(tools, folder, model, cfg)
        return not passed and bool(finding), finding or "not found", numbers, secs
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def java_version():
    r = subprocess.run(["java", "-version"], capture_output=True, text=True)
    return (r.stderr or r.stdout).splitlines()[0] if (r.stderr or r.stdout) else "unknown"


def record(checks, mutations):
    lines = ["# Results of the model checks", "",
             "Written by `python docs/model/check.py --mutations --record`. Run it yourself to reproduce; the numbers",
             "of states are the same on every machine, the times are not.", "",
             "| | |", "|---|---|",
             "| Date | %s |" % datetime.date.today().isoformat(),
             "| TLA+ tools | %s (`tla2tools.jar`, SHA-256 `%s`) |" % (TLA_RELEASE, TLA_SHA256),
             "| Java | %s |" % java_version(),
             "| Machine | %s %s, %d logical processors |" % (platform.system(), platform.version(), os.cpu_count() or 0),
             "",
             "## Model checks", "",
             "Every reachable state of each configuration was explored. **PASS** means TLC found no violation of any",
             "invariant or property listed in the configuration.", "",
             "| Model | Configuration | Covers | Distinct states | States generated | Depth | Time | Result |",
             "|---|---|---|---:|---:|---:|---:|---|"]
    for (model, cfg, what), (passed, finding, n, secs) in checks:
        lines.append("| `%s` | `%s` | %s | %s | %s | %s | %.0f s | %s |" % (
            model, cfg, what, "{:,}".format(n.get("distinct") or 0), "{:,}".format(n.get("generated") or 0),
            n.get("depth") or "–", secs, "PASS" if passed else "FAIL: " + finding))
    lines += ["", "## Mutation checks", "",
              "Each mutation breaks one rule of the design on purpose. **Found** means TLC reported the violation",
              "named; a mutation that is not found would show that the model is too weak to see that error.", "",
              "| Model | Configuration | Broken on purpose | Result | Reported by TLC |", "|---|---|---|---|---|"]
    for (model, cfg, what, _old, _new), (found, finding, _n, _secs) in mutations:
        lines.append("| `%s` | `%s` | %s | %s | %s |" % (model, cfg, what, "Found" if found else "**NOT FOUND**",
                                                         finding))
    with open(os.path.join(HERE, "RESULTS.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mutations", action="store_true", help="also run the mutation checks")
    ap.add_argument("--record", action="store_true", help="write RESULTS.md (needs --mutations)")
    args = ap.parse_args()
    tools = jar()
    checks = []
    for model, cfg, what in CHECKS:
        r = tlc(tools, HERE, model, cfg)
        print("%-13s %-22s %s  %s distinct states, %.0f s  %s" % (model, cfg, "PASS" if r[0] else "FAIL",
                                                                  r[2].get("distinct"), r[3], r[1]), flush=True)
        checks.append(((model, cfg, what), r))
    shutil.rmtree(os.path.join(HERE, "states"), ignore_errors=True)
    mutations = []
    if args.mutations:
        for m in MUTATIONS:
            r = mutate(tools, m[0], m[1], m[3], m[4])
            print("%-13s %-22s %-6s %s  (%s)" % (m[0], m[1], "found" if r[0] else "MISSED", m[2], r[1]), flush=True)
            mutations.append((m, r))
    if args.record:
        if not args.mutations:
            sys.exit("--record needs --mutations")
        record(checks, mutations)
    ok = all(r[0] for _c, r in checks) and all(r[0] for _m, r in mutations)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
