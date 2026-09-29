import os
import sys
import json
import argparse
import time
import jev_tracker
import jev_key_manager

TypeSafeClient = Choice = Noul = Score = None
TypeSafeAuthenticationError = TypeSafeRateLimitError = None


def _load_typesafe_sdk():
    """Load the provider SDK only for commands that make Jev API requests."""
    global TypeSafeClient, Choice, Noul, Score
    global TypeSafeAuthenticationError, TypeSafeRateLimitError
    if TypeSafeClient is None:
        from typesafe_sdk import Choice as choice_type
        from typesafe_sdk import Noul as noul_type
        from typesafe_sdk import Score as score_type
        from typesafe_sdk import TypeSafeAuthenticationError as authentication_error
        from typesafe_sdk import TypeSafeClient as client_type
        from typesafe_sdk import TypeSafeRateLimitError as rate_limit_error

        TypeSafeClient = client_type
        Choice = choice_type
        Noul = noul_type
        Score = score_type
        TypeSafeAuthenticationError = authentication_error
        TypeSafeRateLimitError = rate_limit_error


def execute_with_failover(api_call_func, max_attempts: int = 3):
    """
    Executes an API call using round-robin keys. If a key fails due to rate limit
    or authentication, marks it and falls over to the next key in the pool.
    """
    attempts = 0
    last_exc = None
    started_at = time.perf_counter()
    _load_typesafe_sdk()
    
    while attempts < max_attempts:
        try:
            api_key, key_alias = jev_key_manager.get_next_key()
        except Exception as e:
            raise e

        try:
            with TypeSafeClient(api_key=api_key) as client:
                res = api_call_func(client)
            # Record key tokens
            usage = getattr(res, "usage", None)
            input_tokens = getattr(usage, "input_tokens", None)
            output_tokens = getattr(usage, "output_tokens", None)
            total_tokens = sum(
                value for value in (input_tokens, output_tokens)
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0
            )
            jev_key_manager.record_key_usage(key_alias, total_tokens)
            duration_ms = (time.perf_counter() - started_at) * 1000
            return res, key_alias, duration_ms, attempts + 1
        except (TypeSafeAuthenticationError, TypeSafeRateLimitError) as exc:
            print(f"[Warning] Key '{key_alias}' encountered {type(exc).__name__}. Falling over to next key...", file=sys.stderr)
            status_tag = "auth_failed" if isinstance(exc, TypeSafeAuthenticationError) else "rate_limited"
            jev_key_manager.mark_key_status(key_alias, status_tag)
            last_exc = exc
            attempts += 1
        except Exception as exc:
            # Check for 429/401 status
            status = getattr(exc, "status_code", None)
            if status in (401, 403, 429):
                print(f"[Warning] Key '{key_alias}' returned HTTP {status}. Falling over to next key...", file=sys.stderr)
                jev_key_manager.mark_key_status(key_alias, "rate_limited" if status == 429 else "auth_failed")
                last_exc = exc
                attempts += 1
            else:
                raise exc
                
    if last_exc:
        raise last_exc
    raise RuntimeError("Failed to execute call across all available keys.")

def run_test():
    print("Testing Jev (System One) with Multi-Key Rotation...")
    
    def call_logic(client):
        return client.system_one(
            model="jev-latest",
            state="I need to build an interactive 3D product configurator",
            questions={
                "technology": Choice(
                    instructions="Which technology is the best fit for building an interactive 3D product configurator?",
                    criteria={"Blender": None, "Three.js": None, "Unity": None},
                )
            }
        )
        
    response, key_used, duration_ms, attempt_count = execute_with_failover(call_logic)
    ans = response.answers["technology"]
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    
    # Track usage in ledger
    jev_tracker.log_call(
        model=response.model,
        question_types=["choice"],
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        confidence=ans.confidence,
        summary=f"Choice: {ans.choice}",
        duration_ms=duration_ms,
        attempt_count=attempt_count,
        request_id=getattr(response, "request_id", None) or getattr(response, "id", None),
    )

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print(f"\nModel: {response.model} (Billed to Key: '{key_used}')")
    print(f"Selected: {ans.choice}")
    print(f"Confidence: {ans.confidence}")
    print("Probabilities:")
    for opt, prob in ans.probabilities.items():
        bar = "#" * int(prob * 20)
        print(f"  - {opt:10}: {prob:0.2f} [{bar:<20}]")
    input_label = input_tokens if input_tokens is not None else "unavailable"
    output_label = output_tokens if output_tokens is not None else "unavailable"
    print(f"Token usage: {input_label} in / {output_label} out\n")

def handle_key_command(args):
    sub = args.key_action
    
    if not sub or sub == "list":
        keys = jev_key_manager.list_keys()
        cfg = jev_key_manager.load_config()
        print("\n" + "=" * 65)
        print(f"       🔑 JEV API KEY POOL & ROTATION (Strategy: {cfg.get('strategy', 'round_robin').upper()})")
        print("=" * 65)
        if not keys:
            print(" No API keys configured in pool.")
        else:
            for k in keys:
                next_tag = " [NEXT ->]" if k["is_next"] else "          "
                target_tag = " (PRIMARY)" if k["is_active_target"] else ""
                stat_tag = f"[{k['status'].upper()}]"
                print(f"{next_tag} {k['name']:<12} {k['masked']:<24} {stat_tag:<12} | Calls: {k['calls']:>2} | Tokens: {k['tokens']:>5}{target_tag}")
        print("-" * 65)
        print(" Commands: jev key add <name> <key> | jev key remove <name>")
        print("           jev key edit <name> [--new-name N] [--key K] [--status S]")
        print("           jev key toggle <name> | jev key strategy <round_robin|single>")
        print("           jev key use <name>")
        print("=" * 65 + "\n")
        
    elif sub == "add":
        res = jev_key_manager.add_key(args.name, args.key)
        print(f"✓ Added API Key '{res['name']}' ({res['masked']}) into the active rotation pool.")
        
    elif sub == "remove":
        ok = jev_key_manager.remove_key(args.name)
        if ok:
            print(f"✓ Removed API Key '{args.name}' from the pool.")
        else:
            print(f"Error: API Key '{args.name}' not found.")

    elif sub == "edit":
        try:
            ok = jev_key_manager.edit_key(
                name=args.name,
                new_name=args.new_name,
                key_val=args.key,
                status=args.status,
            )
            if ok:
                print(f"✓ Key '{args.name}' successfully updated.")
            else:
                print(f"Error: Key '{args.name}' not found.")
        except Exception as exc:
            print(f"Error updating key: {exc}")

    elif sub == "toggle":
        try:
            new_st = jev_key_manager.toggle_key_status(args.name)
            print(f"✓ Key '{args.name}' status changed to: [{new_st.upper()}].")
        except Exception as exc:
            print(f"Error toggling key: {exc}")
            
    elif sub in ("strategy", "mode"):
        new_strat = jev_key_manager.set_strategy(args.strategy_type)
        print(f"✓ Set rotation strategy to: '{new_strat}'")
        
    elif sub in ("use", "set-active"):
        ok = jev_key_manager.set_active_key(args.name)
        if ok:
            print(f"✓ Set active target key to: '{args.name}'")
        else:
            print(f"Error: Key '{args.name}' not found.")

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Jev (TypeSafe System One Decision Model) CLI with Multi-Key Rotation")
    subparsers = parser.add_subparsers(dest="command")

    # test
    subparsers.add_parser("test", help="Run a quick Jev decision test with key rotation")

    # key / keys
    p_key = subparsers.add_parser("key", help="Manage multi-API keys and rotation strategy")
    key_sub = p_key.add_subparsers(dest="key_action")
    
    key_sub.add_parser("list", help="List all configured keys and current rotation status")
    
    p_add = key_sub.add_parser("add", help="Add a new API key to the rotation pool")
    p_add.add_argument("name", help="Alias/identifier for the key (e.g. key2, backup, team)")
    p_add.add_argument("key", help="The secret TypeSafe API Key")
    
    p_rm = key_sub.add_parser("remove", help="Remove an API key from the pool")
    p_rm.add_argument("name", help="Name of the key to remove")
    
    p_strat = key_sub.add_parser("strategy", help="Set rotation strategy")
    p_strat.add_argument("strategy_type", choices=["round_robin", "single", "round-robin"], help="Rotation mode")
    
    p_use = key_sub.add_parser("use", help="Set specific key as active target")
    p_use.add_argument("name", help="Name of the key to set active")

    p_edit = key_sub.add_parser("edit", help="Edit an existing API key's name, value, or status")
    p_edit.add_argument("name", help="Current name of the key to edit")
    p_edit.add_argument("--new-name", "-n", default=None, help="New alias/identifier for the key")
    p_edit.add_argument("--key", "-k", default=None, help="New secret TypeSafe API Key value")
    p_edit.add_argument("--status", "-s", choices=["active", "inactive"], default=None, help="New status")

    p_toggle = key_sub.add_parser("toggle", help="Toggle key status between active and inactive")
    p_toggle.add_argument("name", help="Name of the key to toggle")

    # alias "keys"
    subparsers.add_parser("keys", help="Alias for 'jev key list'")

    # panel / stats
    p_panel = subparsers.add_parser("panel", help="Display Jev usage, token burn and wallet dashboard")
    p_panel.add_argument("--web", "-w", action="store_true", help="Open visual graphical dashboard in browser")
    p_panel.add_argument("--client", "-c", default=None, help="Filter by client (antigravity, codex, claude-code, terminal)")
    p_panel.add_argument("--port", type=int, default=0, help="Loopback dashboard port (default: choose an available port)")

    p_stats = subparsers.add_parser("stats", help="Alias for panel")
    p_stats.add_argument("--web", "-w", action="store_true", help="Open visual graphical dashboard in browser")
    p_stats.add_argument("--client", "-c", default=None, help="Filter by client (antigravity, codex, claude-code, terminal)")
    p_stats.add_argument("--port", type=int, default=0, help="Loopback dashboard port (default: choose an available port)")

    # impact / roi
    p_impact = subparsers.add_parser("impact", help="Display token savings, speed, quality and quantity impact report")
    p_impact.add_argument("--client", "-c", default=None, help="Filter by client (antigravity, codex, claude-code, terminal)")
    p_impact.add_argument("--json", "-j", action="store_true", help="Output metrics in JSON format")

    p_roi = subparsers.add_parser("roi", help="Alias for 'jev impact'")
    p_roi.add_argument("--client", "-c", default=None, help="Filter by client (antigravity, codex, claude-code, terminal)")
    p_roi.add_argument("--json", "-j", action="store_true", help="Output metrics in JSON format")

    # choice
    p_choice = subparsers.add_parser("choice", help="Ask Jev a Choice decision question")
    p_choice.add_argument("--state", "-s", required=True, help="State / context")
    p_choice.add_argument("--options", "-o", nargs="+", required=True, help="List of candidate options")
    p_choice.add_argument("--instructions", "-i", default=None, help="Specific question instructions")
    p_choice.add_argument("--client", "-c", default=None, help="Client identifier (antigravity, codex, claude-code, terminal)")

    # noul
    p_noul = subparsers.add_parser("noul", help="Ask Jev a binary (yes/no) Noul question")
    p_noul.add_argument("--state", "-s", required=True, help="State / context")
    p_noul.add_argument("--question", "-q", required=True, help="Yes/No question proposition")
    p_noul.add_argument("--client", "-c", default=None, help="Client identifier (antigravity, codex, claude-code, terminal)")

    # score
    p_score = subparsers.add_parser("score", help="Ask Jev a continuous/graded Score question")
    p_score.add_argument("--state", "-s", required=True, help="State / context")
    p_score.add_argument("--levels", "-l", nargs="+", required=True, help="Ordered descriptions of score levels")
    p_score.add_argument("--client", "-c", default=None, help="Client identifier (antigravity, codex, claude-code, terminal)")

    # run json
    p_run = subparsers.add_parser("run", help="Run a full batched JSON request file")
    p_run.add_argument("file", help="Path to request JSON file")
    p_run.add_argument("--client", "-c", default=None, help="Client identifier (antigravity, codex, claude-code, terminal)")

    args = parser.parse_args()

    if not args.command:
        run_test()
        return

    if args.command == "keys":
        args.key_action = "list"
        handle_key_command(args)
        return

    if args.command == "key":
        handle_key_command(args)
        return

    if args.command in ("panel", "stats"):
        if args.web:
            jev_tracker.open_web_dashboard(port=args.port)
        else:
            jev_tracker.print_terminal_card(args.client)
        return

    if args.command in ("impact", "roi"):
        if getattr(args, "json", False):
            m = jev_tracker.get_metrics(args.client)
            out = {k: v for k, v in m.items() if k not in ("records", "all_records", "unverified_records")}
            print(json.dumps(out, indent=2))
        else:
            jev_tracker.print_impact_card(args.client)
        return

    if args.command == "test":
        run_test()
        return

    if args.command == "choice":
        inst = args.instructions or f"Select the best option among: {', '.join(args.options)}"
        criteria = {opt: None for opt in args.options}
        
        def call_logic(client):
            return client.system_one(
                model="jev-latest",
                state=args.state,
                questions={"decision": Choice(instructions=inst, criteria=criteria)}
            )
            
        res, key_used, duration_ms, attempt_count = execute_with_failover(call_logic)
        ans = res.answers["decision"]
        jev_tracker.log_call(
            model=res.model,
            question_types=["choice"],
            input_tokens=getattr(getattr(res, "usage", None), "input_tokens", None),
            output_tokens=getattr(getattr(res, "usage", None), "output_tokens", None),
            confidence=ans.confidence,
            summary=f"Choice: {ans.choice}",
            client=args.client,
            duration_ms=duration_ms,
            attempt_count=attempt_count,
            request_id=getattr(res, "request_id", None) or getattr(res, "id", None),
        )
        print(json.dumps({
            "model": res.model,
            "billed_to_key": key_used,
            "choice": ans.choice,
            "confidence": ans.confidence,
            "probabilities": ans.probabilities
        }, indent=2))

    elif args.command == "noul":
        def call_logic(client):
            return client.system_one(
                model="jev-latest",
                state=args.state,
                questions={"judgment": Noul(instructions=args.question)}
            )
            
        res, key_used, duration_ms, attempt_count = execute_with_failover(call_logic)
        ans = res.answers["judgment"]
        jev_tracker.log_call(
            model=res.model,
            question_types=["noul"],
            input_tokens=getattr(getattr(res, "usage", None), "input_tokens", None),
            output_tokens=getattr(getattr(res, "usage", None), "output_tokens", None),
            confidence=None,
            summary=f"Noul · probability yes: {ans.noul:.2f}",
            client=args.client,
            duration_ms=duration_ms,
            attempt_count=attempt_count,
            request_id=getattr(res, "request_id", None) or getattr(res, "id", None),
        )
        print(json.dumps({
            "model": res.model,
            "billed_to_key": key_used,
            "probability_yes": ans.noul
        }, indent=2))

    elif args.command == "score":
        def call_logic(client):
            return client.system_one(
                model="jev-latest",
                state=args.state,
                questions={"scoring": Score(criteria=args.levels)}
            )
            
        res, key_used, duration_ms, attempt_count = execute_with_failover(call_logic)
        ans = res.answers["scoring"]
        jev_tracker.log_call(
            model=res.model,
            question_types=["score"],
            input_tokens=getattr(getattr(res, "usage", None), "input_tokens", None),
            output_tokens=getattr(getattr(res, "usage", None), "output_tokens", None),
            confidence=ans.confidence,
            summary=f"Score: {ans.score}",
            client=args.client,
            duration_ms=duration_ms,
            attempt_count=attempt_count,
            request_id=getattr(res, "request_id", None) or getattr(res, "id", None),
        )
        print(json.dumps({
            "model": res.model,
            "billed_to_key": key_used,
            "score": ans.score,
            "confidence": ans.confidence,
            "probabilities": ans.probabilities
        }, indent=2))

    elif args.command == "run":
        with open(args.file, "r", encoding="utf-8") as f:
            data = json.load(f)
        constructors = {"choice": Choice, "noul": Noul, "score": Score}
        questions = {}
        types_used = []
        for q_id, spec in data["questions"].items():
            t = spec["type"].lower()
            types_used.append(t)
            questions[q_id] = constructors[t](**spec)
            
        def call_logic(client):
            return client.system_one(
                model=data.get("model", "jev-latest"),
                state=data["state"],
                questions=questions
            )
            
        res, key_used, duration_ms, attempt_count = execute_with_failover(call_logic)
        jev_tracker.log_call(
            model=res.model,
            question_types=types_used,
            input_tokens=getattr(getattr(res, "usage", None), "input_tokens", None),
            output_tokens=getattr(getattr(res, "usage", None), "output_tokens", None),
            confidence=None,
            summary=f"Batched request · {len(types_used)} questions",
            client=args.client,
            duration_ms=duration_ms,
            attempt_count=attempt_count,
            request_id=getattr(res, "request_id", None) or getattr(res, "id", None),
        )
        print(json.dumps(res.model_dump(mode="json"), indent=2))

if __name__ == "__main__":
    main()
